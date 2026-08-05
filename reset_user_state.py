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

Also not covered (browser-side): the TTS-enabled and accent-color localStorage
keys. Use a fresh browser profile per participant.

By default the outgoing participant's files are archived under study_data/
before being cleared, so their data isn't destroyed. input.wav is deleted rather
than archived — it's a transient recording buffer, not study data.

Usage:
    python reset_user_state.py                          # confirm, archive, wipe
    python reset_user_state.py --participant P03 -y     # archive as P03, no prompt
    python reset_user_state.py --status                 # inspect, change nothing
    python reset_user_state.py --keep-sandbox -y        # leave jarvis_sandbox/ alone
    python reset_user_state.py --no-backup -y           # wipe without archiving

Stdlib only and no imports from the Jarvis modules, so it runs without the venv
active and without loading the embedder or hitting the Groq API.
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
BACKEND_HOST, BACKEND_PORT = "127.0.0.1", 8001


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


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--participant", help="label for the archive dir (default: reset_<timestamp>)")
    parser.add_argument("--keep-sandbox", action="store_true", help="leave jarvis_sandbox/ contents in place")
    parser.add_argument("--no-backup", action="store_true", help="don't archive current state before wiping")
    parser.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--status", action="store_true", help="show current state and exit without changing anything")
    args = parser.parse_args()

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

    print("Reset complete. Jarvis now has:")
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
    print(f"\nBlank slate - no profile, no facts, no style, {trailing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
