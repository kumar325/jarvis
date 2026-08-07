"""Reset all personalization state so Jarvis is a blank slate for a new participant.

Clears every piece of on-disk state that carries between sessions:
  preferences.json  — rated preference pairs + cached query embeddings
  user_profile.json — URL-derived summary + remembered facts
  user_style.json   — utterance buffer + cached style summary
  jarvis_sandbox/   — files the previous participant had Jarvis create
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

Usage:
    python reset_user_state.py                          # confirm, archive, wipe
    python reset_user_state.py --participant P03 -y     # archive as P03, no prompt
    python reset_user_state.py --status                 # inspect, change nothing
    python reset_user_state.py --keep-sandbox -y        # leave jarvis_sandbox/ alone
    python reset_user_state.py --no-backup -y           # wipe without archiving

    # arch2: wipe, then seed the incoming participant's cold-start profile
    python reset_user_state.py --participant P03 --profile-url https://... -y

Stdlib only and no imports from the Jarvis modules, so it runs without the venv
active and without loading the embedder or hitting the Groq API.

--profile-url is the ONE exception. It imports user_profile (and therefore
langchain_groq), needs the venv active, and makes a network call plus a Groq
call. The import is local to seed_profile() so every other path keeps the
property above. Everything else in this file stays stdlib-only — don't hoist
that import to the top.
"""
import argparse
import json
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

# Where the FastAPI backend listens (frontend/src/hooks/useJarvisSocket.ts).
BACKEND_HOST, BACKEND_PORT = "127.0.0.1", 8000


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


def backup(label: str, include_sandbox: bool) -> Path | None:
    """Copy state files (and sandbox contents) into study_data/<label>/.

    Returns the archive dir, or None if there was nothing worth archiving.
    """
    present = [p for p in STATE_FILES if p.exists()]
    entries = sandbox_entries() if include_sandbox else []
    if not present and not entries:
        return None

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
    return dest


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


def seed_profile(url: str) -> bool:
    """Fetch the incoming participant's public URL and store the cold-start summary.

    Must run AFTER wipe() — wipe writes {} over user_profile.json, so seeding first would
    erase itself. Returns False on any failure, and the caller must treat that as fatal:
    at that point state is already wiped, so continuing leaves an empty profile, which is
    the exact condition that makes an arch2 session behave like arch1.
    """
    print(f"\nSeeding cold-start profile from {url}")
    try:
        # Local import on purpose — see the module docstring. This is the only path here
        # that needs the venv.
        from user_profile import get_profile_summary, learn_from_url
    except Exception as e:
        print(f"  FAILED to import user_profile: {e}")
        print(r"  Is the venv active? .venv\Scripts\Activate.ps1")
        return False

    try:
        result = learn_from_url(url)
    except Exception as e:
        print(f"  FAILED: {e}")
        return False

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
    parser.add_argument("--participant", help="label for the archive dir (default: reset_<timestamp>)")
    parser.add_argument(
        "--profile-url",
        action="append",
        metavar="URL",
        help="arch2 only: after wiping, seed the cold-start profile from this public URL "
             "(needs the venv active). Omit for arch1, which has no personalization layer.",
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
    if args.profile_url and len(args.profile_url) > 1:
        parser.error(
            "--profile-url takes a single URL; user_profile.learn_from_url() cannot merge "
            "several sources into one summary yet (it would keep only the last)."
        )
    profile_url = args.profile_url[0] if args.profile_url else None

    include_sandbox = not args.keep_sandbox

    print("Current participant state:")
    print_state(include_sandbox)

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
        label = args.participant or f"reset_{datetime.now():%Y%m%d_%H%M%S}"
        dest = backup(label, include_sandbox)
        if dest:
            print(f"\nArchived previous state to {dest.relative_to(ROOT)}")
        else:
            print("\nNothing to archive - no state files present.")

    wipe(include_sandbox)

    # Strictly after the wipe (which blanks user_profile.json) and after the backup above
    # (which archived the outgoing participant's profile).
    if profile_url and not seed_profile(profile_url):
        print(
            "\n!! STATE IS WIPED AND NO PROFILE WAS STORED.\n"
            "   Arch 2's only personalization layer is empty, so a session started now\n"
            "   would be labeled arch2 while behaving like arch1 — and every rating and\n"
            "   survey row would carry the wrong condition.\n"
            "   Fix the URL (or the network, or GROQ_API_KEY) and re-run with --profile-url.\n"
            f"   The backend refuses to start in this state when JARVIS_STUDY_CONDITION=arch2."
        )
        return 2

    print("\nReset complete. Jarvis now has:")
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
    if profile_url:
        print(f"\nArch 2 ready - cold-start profile seeded, no facts, no style, {trailing}")
    else:
        print(f"\nBlank slate - no profile, no facts, no style, {trailing}")
        # Correct for arch1, fatal for arch2, and the two are told apart only by an env
        # var set in another terminal — so say it here rather than assume the right one.
        print(
            "\n  No --profile-url given. That is correct for arch1 and WRONG for arch2:\n"
            "  the cold-start profile is arch2's only personalization layer. The backend\n"
            "  refuses to start with JARVIS_STUDY_CONDITION=arch2 and an empty profile."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
