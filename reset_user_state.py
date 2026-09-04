"""Reset all personalization state so Himavat is a blank slate for a new participant.

Clears every piece of on-disk state that carries between sessions:
  preferences.json  — rated preference pairs + cached query embeddings
  user_profile.json — URL-derived summary + remembered facts
  user_style.json   — utterance buffer + cached style summary
  jarvis_sandbox/   — files the previous participant had Himavat create
  input.wav         — last recorded utterance

The three JSON files cover personalization layers 2-5 of the system prompt
(layer 1 is the static base instructions in system_prompt.py, which is not user
state). The sandbox matters because the file tools let one participant read what
the previous one wrote.

NOT covered, because it lives in another process's memory rather than on disk:
agent_loop.py's module-level `conversation` list. backend/server.py now calls
clear_conversation() on every WebSocket connect, so it resets when the next
participant's browser connects — but a tab left open from the previous session
never reconnects, so this script checks for a running backend and reminds you to
reload the page.

Also not covered (browser-side): the jarvis-tts-enabled localStorage key, which
carries the mute toggle across reloads. Use a fresh browser profile per participant.

By default the outgoing participant's files are archived under study_data/
before being cleared, so their data isn't destroyed. input.wav is deleted rather
than archived — it's a transient recording buffer, not study data.

The archive also collects the documents that participant's profile was built from
(their PDF export, their written bio) into study_data/<label>/sources/, matched
via user_profile.json's `sources` list and MOVED out of the staging dirs. Left
loose, they accumulate at the study_data root across participants with nothing
recording whose was whose — which is exactly what happened over the pilots.

The archive is named for the participant going OUT, which is *not* --participant
(that names the one coming in, and is what the seeding flags apply to). Naming it
for the incoming participant is how every pilot archive ended up holding the
previous person's session. The outgoing label comes from
study_data/.current_participant, written by the previous reset, falling back to
the last row of ratings.jsonl and then to a timestamp. --archive-as overrides it.

Usage:
    python reset_user_state.py                          # confirm, archive, wipe
    python reset_user_state.py --participant P04 -y     # P04 is next; archive is named
                                                        # for whoever just finished
    python reset_user_state.py --status                 # inspect, change nothing
    python reset_user_state.py --archive-as P03 -y      # override the outgoing label
    python reset_user_state.py --keep-sandbox -y        # leave jarvis_sandbox/ alone
    python reset_user_state.py --no-backup -y           # wipe without archiving

    # wipe, then seed the incoming participant's cold-start profile. All three flags are
    # repeatable and combinable; every source is summarized together into one profile.
    python reset_user_state.py --participant P03 --profile-url https://... -y
    python reset_user_state.py --participant P03 --profile-text-file bio.txt -y
    python reset_user_state.py --participant P03 --profile-pdf linkedin.pdf -y
    python reset_user_state.py --participant P03 --profile-url https://... \
                               --profile-text-file bio.txt -y

Stdlib only and no imports from the Himavat modules, so it runs without the venv
active and without loading the embedder or hitting the Groq API.

The three --profile-* flags are the ONE exception. They import user_profile (and
therefore langchain_groq, and pypdf for --profile-pdf), need the venv active, and
make a Groq call — plus a network call for --profile-url. The import is local to
seed_profile() so every other path keeps the property above. Everything else in
this file stays stdlib-only — don't hoist that import to the top.
"""
import argparse
import csv
import json
import re
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / "study_data"

# Paths and empty shapes mirror the owning modules — keep in sync with
# config.PREFS_FILE, user_profile.PROFILE_FILE, style_tracker.STYLE_FILE.
STATE_FILES = {
    ROOT / "preferences.json": [],
    ROOT / "user_profile.json": {},
    ROOT / "user_style.json": {"utterances": [], "style_summary": "", "turns_since_analysis": 0},
}

SANDBOX = ROOT / "jarvis_sandbox"          # config.SANDBOX
RECORDING = ROOT / "input.wav"             # voice.py's scratch recording

# Where a participant's source documents (a LinkedIn PDF export, a written bio) sit before
# they are seeded, and where a bare --profile-pdf / --profile-text-file name is looked up.
# The sandbox is where the file tools write; the study_data root is the staging tray the
# moderator drops documents into. Searched in this order.
DOC_STAGING_DIRS = (SANDBOX, BACKUP_ROOT, ROOT)

# Of those, the ones a document may be MOVED out of. The repo root is searched (a moderator
# may well pass a path relative to it) but never emptied: it holds tracked files, and a
# --profile-text-file pointed at one by mistake would turn into a git deletion.
DOC_MOVE_DIRS = (SANDBOX, BACKUP_ROOT)

# Subdirectory of the archive that holds the documents a participant's profile was built
# from, kept apart from the three state JSONs so an archive says at a glance what went in
# as well as what came out.
SOURCES_DIRNAME = "sources"

# Written at the end of every labeled reset, naming the participant whose session is about
# to start. The NEXT reset reads it back to name that participant's archive — see
# outgoing_label(). Without it the archive dir was named for the incoming participant while
# holding the outgoing one's data, so every folder was attributed to the wrong person.
CURRENT_PARTICIPANT_FILE = BACKUP_ROOT / ".current_participant"

# Written by backend/ratings.py and backend/tasks.py. Read here only to recover who the
# state on disk belongs to when the marker above is missing. survey_responses.csv is frozen
# pilot data — nothing appends to it any more, but it is still read so a reset run against
# an old study_data/ can still name its archive.
RATINGS_FILE = BACKUP_ROOT / "ratings.jsonl"
TASK_EVENTS_FILE = BACKUP_ROOT / "task_events.csv"
SURVEY_FILE = BACKUP_ROOT / "survey_responses.csv"

# Where the FastAPI backend listens (frontend/src/hooks/useJarvisSocket.ts).
BACKEND_HOST, BACKEND_PORT = "127.0.0.1", 8000


def rel(path: Path) -> str:
    """Repo-relative display path, falling back to the absolute one for anything outside."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def find_document(name: str) -> Path | None:
    """Locate a source document by bare filename.

    Staging dirs first, then anywhere under study_data/ (most recently modified first) so a
    document already archived with an earlier participant is still found. That matters
    because seeding now MOVES documents into the archive: without this, re-running a
    PDF-based seed for the same person would fail on a file that is sitting safely one
    folder deeper.
    """
    for directory in DOC_STAGING_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return candidate

    # Matched by name rather than rglob(name) — an export filename is arbitrary text and can
    # contain glob metacharacters, which rglob would interpret rather than match.
    if BACKUP_ROOT.is_dir():
        matches = [p for p in BACKUP_ROOT.rglob("*") if p.is_file() and p.name == name]
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def resolve_pdf(raw: str) -> Path | None:
    """Find a --profile-pdf argument. Returns None if it doesn't exist anywhere sensible.

    A bare filename is looked up by find_document(), so the moderator can pass what they see
    in the folder rather than a path. An argument containing a separator is taken literally
    — resolving `study_data/x.pdf` against the search dirs too would make
    `study_data/study_data/x.pdf` a silent hit.
    """
    candidate = Path(raw)
    if candidate.is_file():
        return candidate
    if candidate.parent == Path("."):
        return find_document(candidate.name)
    return None


def profile_source_documents() -> list[str]:
    """Filenames of the documents the CURRENT on-disk profile was seeded from.

    Read from user_profile.json's `sources`, which learn_from_sources() writes as a URL
    verbatim, a PDF as its bare filename, and a text file as "self-reported (bio.txt)".
    URLs are skipped — there is no local file to archive.

    This is the attribution link between a loose document and the participant it describes.
    Matching on a filename prefix instead (PILOT3*) would miss the common case: an export is
    named after the person, not the participant ID, and "Kaylea Champion, PhD _ LinkedIn.pdf"
    carries nothing to match on.
    """
    path = ROOT / "user_profile.json"
    if not path.exists():
        return []
    try:
        sources = json.loads(path.read_text(encoding="utf-8")).get("sources", [])
    except Exception:
        return []

    names = []
    for source in sources:
        if not isinstance(source, str):
            continue
        source = source.strip()
        if source.startswith(("http://", "https://")):
            continue
        match = re.fullmatch(r"self-reported \((.+)\)", source)
        name = match.group(1) if match else source
        # learn_from_text()'s default label is a bare "self-reported" with no filename —
        # reachable from the CLI and the eval harness, though not from this script.
        if name and name != "self-reported" and name not in names:
            names.append(name)
    return names


def describe(path: Path) -> str:
    """One-line summary of what a state file currently holds."""
    if not path.exists():
        return "absent"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"unreadable ({e})"

    if path.name == "preferences.json":
        up = sum(1 for p in data if p.get("rating") == "up")
        down = sum(1 for p in data if p.get("rating") == "down")
        return f"{len(data)} preference pairs ({up} up / {down} down)"
    if path.name == "user_profile.json":
        facts = len(data.get("remembered_facts", []))
        sources = len(data.get("sources", []))
        summary = "summary" if data.get("summary") else "no summary"
        return f"{facts} facts, {sources} sources, {summary}"
    if path.name == "user_style.json":
        utterances = len(data.get("utterances", []))
        summary = "summary" if data.get("style_summary") else "no summary"
        return f"{utterances} utterances, {summary}"
    return "unknown"


def sandbox_entries() -> list[Path]:
    """Everything currently sitting in the sandbox. Empty list if the dir is absent."""
    if not SANDBOX.is_dir():
        return []
    return sorted(SANDBOX.iterdir())


def describe_sandbox() -> str:
    entries = sandbox_entries()
    if not SANDBOX.is_dir():
        return "absent"
    if not entries:
        return "empty"
    names = ", ".join(p.name for p in entries[:3])
    more = f", +{len(entries) - 3} more" if len(entries) > 3 else ""
    return f"{len(entries)} items ({names}{more})"


def backend_running() -> bool:
    """True if something is listening on the backend's WebSocket port."""
    try:
        with socket.create_connection((BACKEND_HOST, BACKEND_PORT), timeout=0.3):
            return True
    except OSError:
        return False


def print_state(include_sandbox: bool):
    for path in STATE_FILES:
        print(f"  {path.name:<20} {describe(path)}")
    if include_sandbox:
        print(f"  {'jarvis_sandbox/':<20} {describe_sandbox()}")
    print(f"  {'input.wav':<20} {'present' if RECORDING.exists() else 'absent'}")
    docs = profile_source_documents()
    if docs:
        print(f"  {'profile sources':<20} {', '.join(docs)}")


def archive_source_documents(dest: Path, keep_in_place: set) -> list[str]:
    """File the outgoing participant's source documents under their archive dir.

    MOVED, not copied, when the document is loose in DOC_MOVE_DIRS. Leaving it is what let
    four participants' bios and a LinkedIn export pile up in the study_data root with
    nothing recording whose was whose. Three cases are copied instead:

      * a document already filed under some participant — never rob an existing archive.
        The same person can legitimately be seeded twice (a bio for one arm, a PDF for a
        later one), and the earlier archive should stay complete;
      * a document the INCOMING seed is about to read. --profile-pdf paths are resolved
        before the wipe, so moving one out from under an already-resolved path would fail
        during seeding — i.e. after state is wiped, the one moment a failure is expensive;
      * a document sitting in the repo root, which is searched but never emptied.

    Returns one report line per document. Never raises on a missing file: the profile
    records what it was built from, but the moderator may have moved or renamed it since,
    and a stale entry there must not take down a reset.
    """
    names = profile_source_documents()
    if not names:
        return []

    staging = {d.resolve() for d in DOC_MOVE_DIRS}
    sources_dir = dest / SOURCES_DIRNAME
    lines = []

    for name in names:
        found = find_document(name)
        if found is None:
            lines.append(f"{name} - not found on disk, nothing archived")
            continue

        target = sources_dir / found.name
        if found.resolve() == target.resolve():
            lines.append(f"{found.name} - already in {SOURCES_DIRNAME}/")
            continue
        if target.exists():
            lines.append(f"{found.name} - already archived; original left at {rel(found.parent)}")
            continue

        sources_dir.mkdir(parents=True, exist_ok=True)
        loose = found.parent.resolve() in staging
        wanted_by_seed = found.resolve() in keep_in_place
        if loose and not wanted_by_seed:
            shutil.move(str(found), target)
            lines.append(f"{found.name} - moved from {rel(found.parent)}")
        else:
            shutil.copy2(found, target)
            why = "needed by the incoming seed" if wanted_by_seed else f"kept in {rel(found.parent)}"
            lines.append(f"{found.name} - copied ({why})")
    return lines


def backup(label: str, include_sandbox: bool, keep_in_place: set = frozenset()) -> tuple[Path | None, list[str]]:
    """Copy state files (and sandbox contents) into study_data/<label>/, and file the
    profile's source documents into study_data/<label>/sources/.

    Returns (archive dir, source-document report lines), or (None, []) if there was
    nothing worth archiving.
    """
    present = [p for p in STATE_FILES if p.exists()]
    entries = sandbox_entries() if include_sandbox else []
    if not present and not entries and not profile_source_documents():
        return None, []

    dest = BACKUP_ROOT / label
    if dest.exists():
        dest = BACKUP_ROOT / f"{label}_{datetime.now():%H%M%S}"
    dest.mkdir(parents=True)

    for path in present:
        shutil.copy2(path, dest / path.name)
    if entries:
        sandbox_dest = dest / "jarvis_sandbox"
        sandbox_dest.mkdir()
        for entry in entries:
            if entry.is_dir():
                shutil.copytree(entry, sandbox_dest / entry.name)
            else:
                shutil.copy2(entry, sandbox_dest / entry.name)

    # After the state files, so a failure while shuffling documents can't cost the JSONs.
    return dest, archive_source_documents(dest, set(keep_in_place))


def _mtime(path: Path) -> float:
    """Modification time, or 0.0 for a file that isn't there."""
    return path.stat().st_mtime if path.exists() else 0.0


def logged_participant() -> tuple[str | None, str]:
    """Who the study's own logs say ran most recently, and which log said so.

    ratings.jsonl first: it gets a row on every thumbs up/down, so it exists even for an
    arm abandoned before the first "Finish Task". task_events.csv is the fallback for a
    session that was rated by nobody, and survey_responses.csv behind it for a pilot
    session logged before the on-screen survey moved to paper.
    """
    if RATINGS_FILE.is_file():
        try:
            for line in reversed(RATINGS_FILE.read_text(encoding="utf-8").splitlines()):
                if line.strip():
                    pid = json.loads(line).get("participant_id")
                    if pid:
                        return pid, RATINGS_FILE.name
        except Exception:
            pass
    for csv_file in (TASK_EVENTS_FILE, SURVEY_FILE):
        if not csv_file.is_file():
            continue
        try:
            rows = list(csv.DictReader(csv_file.read_text(encoding="utf-8").splitlines()))
            for row in reversed(rows):
                pid = (row.get("participant_id") or "").strip()
                if pid:
                    return pid, csv_file.name
        except Exception:
            pass
    return None, ""


def outgoing_label(explicit: str | None) -> tuple[str, str, str | None]:
    """Name the archive dir after the participant whose state is being archived.

    Returns (label, where it came from, warning or None).

    NOT --participant: that names the participant about to start, which is what the seeding
    flags apply to. Naming the archive after them too is how study_data/PILOT4/ ended up
    holding PILOT3's session — every folder off by one, discoverable only by reading the
    profile inside it.

    The marker file wins over the logs because it is written by the reset that created the
    state being archived. When the logs disagree it is worth saying so: the rows carry the
    condition and arch_position an analysis will join on, so an archive that disagrees with
    them is the copy that's wrong.
    """
    if explicit:
        return explicit, "--archive-as", None

    marker = ""
    if CURRENT_PARTICIPANT_FILE.is_file():
        # utf-8-sig: the moderator may well have written this file by hand, and both
        # Notepad and PowerShell's Set-Content -Encoding utf8 prepend a BOM, which would
        # otherwise ride along into the directory name as an invisible leading character.
        marker = CURRENT_PARTICIPANT_FILE.read_text(encoding="utf-8-sig").strip()

    logged, log_name = logged_participant()
    if marker:
        # Only a disagreement about a session that has actually run is worth flagging. A
        # participant who has just been reset in has no rows yet, so the last row naming
        # someone else is the normal state of affairs — comparing IDs alone would warn on
        # every single reset, which trains the moderator to skip the warning that matters.
        ran_since_marker = bool(log_name) and _mtime(BACKUP_ROOT / log_name) > _mtime(CURRENT_PARTICIPANT_FILE)
        warning = None
        if logged and logged != marker and ran_since_marker:
            warning = (
                f"{CURRENT_PARTICIPANT_FILE.name} says {marker}, but {log_name} has rows "
                f"for {logged} written since that reset.\n"
                f"     Archiving as {marker}. If the logged rows are right (the backend was "
                f"labeled {logged}), re-run with --archive-as {logged}."
            )
        return marker, CURRENT_PARTICIPANT_FILE.name, warning
    if logged:
        return logged, f"last row of {log_name}", None
    return (
        f"reset_{datetime.now():%Y%m%d_%H%M%S}",
        "no record of who ran",
        "No .current_participant marker and no rated sessions - archiving under a timestamp.",
    )


def wipe(include_sandbox: bool):
    """Clear every on-disk trace of the previous participant."""
    for path, empty in STATE_FILES.items():
        path.write_text(json.dumps(empty, indent=2), encoding="utf-8")

    if include_sandbox:
        # Empty the sandbox but keep the directory — config.py expects it to exist.
        for entry in sandbox_entries():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
        SANDBOX.mkdir(exist_ok=True)

    RECORDING.unlink(missing_ok=True)


def console_safe(text: str) -> str:
    """Make LLM/scraped text printable on whatever encoding this console uses.

    The profile summary is model output built from a scraped page, so it routinely carries
    non-breaking hyphens, curly quotes and en dashes that a cp1252 Windows console cannot
    encode. Printing it raw raises UnicodeEncodeError *after* the profile has already been
    saved — which turns a successful seed into a traceback and a non-zero exit, exactly
    when the operator is trying to confirm the seed worked.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def seed_profile(urls: list, text_files: list, pdf_files: list = ()) -> bool:
    """Store the cold-start profile from any mix of URLs, written text, and PDF exports.

    Must run AFTER wipe() — wipe writes {} over user_profile.json, so seeding first would
    erase itself. Returns False on any failure, and the caller must treat that as fatal:
    at that point state is already wiped, so continuing leaves an empty profile, which is
    the exact condition that makes an arch2 session behave like arch1.

    All sources are summarized together in one call (learn_from_sources), not one call
    each — the profile has a single `summary` field, so per-source calls would leave only
    the last one standing.
    """
    described = (
        [str(u) for u in urls]
        + [f"{p.name} (self-written)" for p in text_files]
        + [f"{p.name} (PDF export)" for p in pdf_files]
    )
    print(f"\nSeeding cold-start profile from {len(described)} source(s):")
    for d in described:
        print(f"    {d}")
    try:
        # Local import on purpose — see the module docstring. This is the only path here
        # that needs the venv.
        from user_profile import get_profile_summary, learn_from_sources
    except Exception as e:
        print(f"  FAILED to import user_profile: {e}")
        print(r"  Is the venv active? .venv\Scripts\Activate.ps1")
        return False

    try:
        texts = [(f"self-reported ({p.name})", p.read_text(encoding="utf-8"))
                 for p in text_files]
        result, failed = learn_from_sources(urls=urls, texts=texts, pdfs=list(pdf_files))
    except Exception as e:
        print(f"  FAILED: {e}")
        if "pypdf" in str(e):
            print("  --profile-pdf needs pypdf: .venv\\Scripts\\python.exe -m pip install pypdf")
        return False

    # Partial failure is not fatal — a profile built from the surviving sources is still
    # usable — but it must be impossible to miss, or a participant runs with half the
    # profile you intended and nothing downstream records that.
    if failed:
        print(f"\n  !! {len(failed)} of {len(described)} source(s) FAILED:")
        for f in failed:
            print(f"       {console_safe(f)}")
        if len(failed) < len(described):
            print("     Profile was built from the remaining source(s). Re-run if that's not what you want.")

    # learn_from_url reports a bad fetch or a login-walled page by *returning* a message
    # rather than raising, so its return value alone can't distinguish success from
    # failure. Read back what the system prompt will actually inject instead.
    try:
        summary = get_profile_summary().strip()
    except Exception as e:
        print(f"  FAILED to read back the stored profile: {e}")
        return False

    if not summary:
        print(f"  FAILED - nothing was stored. {console_safe(result)}")
        return False

    print(f"  Stored {len(summary)} chars.")
    print(f"  {console_safe(summary[:400])}{'...' if len(summary) > 400 else ''}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--participant",
        help="the INCOMING participant, the one whose session starts after this reset. The "
             "seeding flags below apply to them. Recorded in study_data/.current_participant "
             "so the NEXT reset can name their archive; it does NOT name the archive written "
             "now, which belongs to the participant going out (see --archive-as).",
    )
    parser.add_argument(
        "--archive-as",
        metavar="LABEL",
        help="name the archive dir written now, overriding the participant recorded by the "
             "previous reset. Needed only when that record is missing or wrong.",
    )
    parser.add_argument(
        "--profile-url",
        action="append",
        metavar="URL",
        default=[],
        help="seed the cold-start profile from this public URL after wiping (needs the "
             "venv active). Repeatable, and combinable with --profile-text-file. Seed once "
             "per participant — arch1 simply never reads it.",
    )
    parser.add_argument(
        "--profile-text-file",
        action="append",
        metavar="PATH",
        default=[],
        help="seed the profile from a text file the participant wrote about themselves — "
             "the fallback when they have no public URL, or an extra source alongside one. "
             "A file rather than an inline string because a pasted multi-line bio does not "
             "survive shell quoting. Repeatable.",
    )
    parser.add_argument(
        "--profile-pdf",
        action="append",
        metavar="PATH",
        default=[],
        help="seed the profile from a PDF (e.g. a LinkedIn 'Save to PDF' export). A bare "
             "filename is looked up in jarvis_sandbox/, then study_data/, then inside any "
             "participant archive (so a document filed with an earlier arm still resolves). "
             "Repeatable, and "
             "combinable with the other two. Export chrome — suggested connections, "
             "who-else-viewed, the footer — is stripped before summarizing.",
    )
    parser.add_argument("--keep-sandbox", action="store_true", help="leave jarvis_sandbox/ contents in place")
    parser.add_argument("--no-backup", action="store_true", help="don't archive current state before wiping")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--status", action="store_true", help="show current state and exit without changing anything")
    args = parser.parse_args()

    # learn_from_url appends to profile["sources"] but OVERWRITES profile["summary"], so a
    # second URL would silently discard the first one's summary while leaving its source
    # listed — a profile that looks like it covers two pages but doesn't. Refuse rather
    # than pick one. Supporting several sources properly means summarizing them together
    # in one call, which user_profile.py does not do yet.
    # Any mix of URLs and text files is allowed: learn_from_sources() summarizes them all
    # in one call, so no source can silently overwrite another.
    profile_urls = list(args.profile_url)
    profile_text_files = [Path(p) for p in args.profile_text_file]

    # Checked before the wipe: failing afterwards would leave state cleared with no
    # profile, which is the one outcome these flags exist to prevent.
    for path in profile_text_files:
        if not path.is_file():
            parser.error(f"--profile-text-file: no such file: {path}")

    profile_pdf_files = []
    for raw in args.profile_pdf:
        found = resolve_pdf(raw)
        if found is None:
            searched = ", ".join(rel(d) if d != ROOT else "the repo root" for d in DOC_STAGING_DIRS)
            parser.error(
                f"--profile-pdf: no such file: {raw} "
                f"(searched {searched}, then every archive under {rel(BACKUP_ROOT)})"
            )
        profile_pdf_files.append(found)

    seeding = bool(profile_urls or profile_text_files or profile_pdf_files)

    include_sandbox = not args.keep_sandbox

    # Documents the incoming seed still has to read. archive_source_documents() copies these
    # rather than moving them — see its docstring.
    keep_in_place = {p.resolve() for p in profile_pdf_files + profile_text_files}

    label, label_source, label_warning = outgoing_label(args.archive_as)

    print("Current participant state:")
    print_state(include_sandbox)

    if not args.no_backup:
        print(f"\nThis state will be archived as {label} (from {label_source}).")
        if label_warning:
            print(f"  !! {label_warning}")

    if args.status:
        if backend_running():
            print(f"\nBackend is running on port {BACKEND_PORT} - it still holds the conversation history.")
        return 0

    if not args.yes:
        target = "all three JSON files, the sandbox, and input.wav" if include_sandbox else "the JSON files and input.wav"
        answer = input(f"\nWipe {target}? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted - nothing changed.")
            return 1

    if args.no_backup:
        print("\nSkipping backup (--no-backup).")
    else:
        dest, doc_lines = backup(label, include_sandbox, keep_in_place)
        if dest:
            print(f"\nArchived previous state to {dest.relative_to(ROOT)}")
            for line in doc_lines:
                print(f"  {SOURCES_DIRNAME}/  {line}")
        else:
            print("\nNothing to archive - no state files present.")

    # Seeding runs after the wipe (it has to — the wipe blanks user_profile.json), but the
    # wipe also empties the sandbox. A --profile-pdf living there would be deleted before
    # it was ever read. Copy it into study_data/ first and seed from the copy: the
    # participant's source document belongs with the rest of their material anyway, and
    # under --no-backup the sandbox copy is the only one.
    if include_sandbox and profile_pdf_files:
        preserved = []
        for path in profile_pdf_files:
            if SANDBOX in path.resolve().parents:
                BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
                kept = BACKUP_ROOT / path.name
                shutil.copy2(path, kept)
                print(f"\nPreserved {path.name} -> {kept.relative_to(ROOT)} (sandbox is about to be wiped)")
                preserved.append(kept)
            else:
                preserved.append(path)
        profile_pdf_files = preserved

    wipe(include_sandbox)

    # From here on the state on disk belongs to the incoming participant, so record who that
    # is — the next reset names their archive from it. Written before seeding so it survives
    # the exit-2 path below: a failed seed doesn't change whose session is starting.
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    if args.participant:
        CURRENT_PARTICIPANT_FILE.write_text(args.participant, encoding="utf-8")
        print(f"\nNext session's state belongs to {args.participant} "
              f"(recorded in {rel(CURRENT_PARTICIPANT_FILE)}).")
    else:
        # A stale marker is worse than none: it would name the next archive after the
        # participant before last. Cleared, so the fallback reads the rating rows instead.
        CURRENT_PARTICIPANT_FILE.unlink(missing_ok=True)
        print(f"\nNo --participant given, so {CURRENT_PARTICIPANT_FILE.name} was cleared - the "
              f"next reset will name its archive from {RATINGS_FILE.name}.")

    # Strictly after the wipe (which blanks user_profile.json) and after the backup above
    # (which archived the outgoing participant's profile).
    if seeding and not seed_profile(profile_urls, profile_text_files, profile_pdf_files):
        print(
            "\n!! STATE IS WIPED AND NO PROFILE WAS STORED.\n"
            "   Arch 2's only personalization layer is empty, so a session started now\n"
            "   would be labeled arch2 while behaving like arch1 — and every rating and\n"
            "   task row would carry the wrong condition.\n"
            "   Fix the source (or the network, or GROQ_API_KEY) and re-run with one of\n"
            "   --profile-url / --profile-text-file / --profile-pdf.\n"
            f"   The backend refuses to start in this state when JARVIS_STUDY_CONDITION=arch2."
        )
        return 2

    print("\nReset complete. Himavat now has:")
    print_state(include_sandbox)
    if args.keep_sandbox:
        print("\nSandbox left untouched (--keep-sandbox) - the next participant can read those files.")

    if backend_running():
        print(
            f"\nNote: the backend is running on port {BACKEND_PORT} and still holds the previous\n"
            "  participant's transcript in memory. It clears on the next WebSocket connect, so\n"
            "  RELOAD THE PAGE before the next session - don't reuse an already-open tab."
        )
    else:
        print("\nBackend is not running - start it fresh and the conversation history starts empty.")

    trailing = "no preference examples." if args.keep_sandbox else "no preference examples, no files."
    if seeding:
        print(f"\nArch 2 ready - cold-start profile seeded, no facts, no style, {trailing}")
    else:
        print(f"\nBlank slate - no profile, no facts, no style, {trailing}")
        # Correct for arch1, fatal for arch2, and the two are told apart only by an env
        # var set in another terminal — so say it here rather than assume the right one.
        print(
            "\n  No profile seeded (--profile-url / --profile-text-file / --profile-pdf).\n"
            "  The backend\n"
            "  refuses to start with JARVIS_STUDY_CONDITION=arch2 and an empty profile,\n"
            "  since the cold-start profile is arch2's only personalization layer.\n"
            "  Seed once per participant - arch1 runs fine either way, it never reads it."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
