"""Read back what a session recorded: exchanges, ratings, task durations.

Everything here is reconstructed from files the backend already writes during a session —
nothing extra needs to be captured at the desk. Task boundaries come from task_events.csv:
a task is the run of rated exchanges between one boundary and the next.

The three evaluation questions (personalized / accurate / trust) are answered on a paper
worksheet now, so they aren't reported here for current sessions. Pilot arms logged before
that change kept their answers in survey_responses.csv, which is frozen but still read as a
fallback so those reports don't go blank — they're matched by session id and printed when
present. See backend/tasks.py for why the two files were never merged.

Usage:
    python summarize_session.py                  # every participant
    python summarize_session.py PILOT            # one participant
    python summarize_session.py PILOT --verbose  # plus each exchange's text

Stdlib only, same as reset_user_state.py — it reads study data and never imports the
model stack, so it runs without the venv and can be pointed at a copied study_data/.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RATINGS_PATH = ROOT / "study_data" / "ratings.jsonl"
TASK_EVENTS_PATH = ROOT / "study_data" / "task_events.csv"
# Frozen pilot data — nothing appends to it. Read only so pilot arms still report.
SURVEY_PATH = ROOT / "study_data" / "survey_responses.csv"


def parse_ts(value: str):
    """ISO timestamps as written by ratings.utc_now_iso() / tasks.utc_now_iso()."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def console_safe(text: str) -> str:
    """Transcripts are model output and participant speech — a cp1252 console cannot
    encode all of it, and a UnicodeEncodeError here would kill the whole report."""
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def load_ratings(participant=None):
    if not RATINGS_PATH.exists():
        return []
    rows = []
    for line in RATINGS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if participant is None or row.get("participant_id") == participant:
            rows.append(row)
    return rows


def _load_csv(path, participant=None):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if participant is not None:
        rows = [r for r in rows if r.get("participant_id") == participant]
    return rows


def load_task_rows(participant=None):
    """One row per completed task, newest schema first.

    An arm is served by exactly one of the two files: task_events.csv for anything logged
    since the survey moved to paper, survey_responses.csv for the pilot arms before it.
    Falling back per (participant, arch) rather than concatenating both matters — the two
    files number their tasks independently, so an arm present in both would report two
    task 1s and split its exchanges across them.
    """
    rows = _load_csv(TASK_EVENTS_PATH, participant)
    covered = {(r.get("participant_id"), r.get("arch")) for r in rows}
    rows += [
        r for r in _load_csv(SURVEY_PATH, participant)
        if (r.get("participant_id"), r.get("arch")) not in covered
    ]
    return rows


def fmt_duration(seconds):
    if seconds is None:
        return "  ?  "
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


def report(participant, verbose):
    ratings = load_ratings(participant)
    task_rows = load_task_rows(participant)

    if not ratings and not task_rows:
        print(f"No data for {participant or 'any participant'}.")
        print(f"  looked in {RATINGS_PATH.relative_to(ROOT)} and {TASK_EVENTS_PATH.relative_to(ROOT)}")
        return 1

    # Group by (participant, arch). Ratings carry `condition`, task rows carry `arch`.
    arms = defaultdict(lambda: {"ratings": [], "tasks": []})
    for r in ratings:
        arms[(r.get("participant_id"), r.get("condition"))]["ratings"].append(r)
    for s in task_rows:
        arms[(s.get("participant_id"), s.get("arch"))]["tasks"].append(s)

    for (pid, arch), data in sorted(arms.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        rated = sorted(data["ratings"], key=lambda r: r.get("rated_at") or "")
        done = sorted(data["tasks"], key=lambda s: int(s.get("task_number") or 0))
        position = (rated[0].get("arch_position") if rated
                    else done[0].get("arch_position") if done else "?")

        print(f"\n{'=' * 70}")
        print(f"{pid}   {arch}   (arm {position} of 2)")
        print("=" * 70)

        # A task is the run of rated exchanges up to the moment its boundary was recorded.
        # Reconstructed rather than recorded, so it stays correct for sessions logged
        # before this script existed.
        cursor = None
        for s in done:
            end = parse_ts(s.get("timestamp"))
            in_task = [
                r for r in rated
                if (t := parse_ts(r.get("rated_at"))) is not None
                and (cursor is None or t > cursor)
                and (end is None or t <= end)
            ]
            first = parse_ts(in_task[0].get("responded_at")) if in_task else None
            duration = (end - first).total_seconds() if (first and end) else None
            ups = sum(1 for r in in_task if r.get("rating") == "up")

            print(f"\n  Task {s.get('task_number')}  "
                  f"{len(in_task)} exchanges  {fmt_duration(duration)}  "
                  f"({ups} up / {len(in_task) - ups} down)")
            # Only pilot rows carry these. Current sessions answer them on paper, and a
            # line of "personalized None/5" would read as a lost answer rather than one
            # that was never asked for here.
            if s.get("personalized_rating"):
                print(f"    personalized {s.get('personalized_rating')}/5   "
                      f"accurate {s.get('accuracy_rating')}   "
                      f"trust {s.get('trust_rating')}/5")

            if verbose:
                for i, r in enumerate(in_task, 1):
                    mark = "+" if r.get("rating") == "up" else "-"
                    print(f"      {mark} [{i}] {console_safe(r.get('user_text', ''))[:100]}")
                    print(f"          -> {console_safe(r.get('assistant_text', ''))[:160]}")
            cursor = end

        # Exchanges after the last boundary never got a Finish Task — worth surfacing
        # rather than dropping, since it usually means a task was abandoned mid-way.
        last_end = parse_ts(done[-1].get("timestamp")) if done else None
        trailing = [r for r in rated
                    if last_end is None or (parse_ts(r.get("rated_at")) or last_end) > last_end]
        if trailing:
            print(f"\n  {len(trailing)} rated exchange(s) after the last task boundary "
                  f"(unfinished task, or Finish Task never clicked)")

        if done:
            counts = []
            cursor = None
            for s in done:
                end = parse_ts(s.get("timestamp"))
                n = sum(1 for r in rated
                        if (t := parse_ts(r.get("rated_at"))) is not None
                        and (cursor is None or t > cursor) and (end is None or t <= end))
                counts.append(n)
                cursor = end
            print(f"\n  Exchanges per task: {counts}   "
                  f"(mean {sum(counts) / len(counts):.1f}, max {max(counts)})")

    print(f"\n{'=' * 70}")
    print("Exchanges per task is the number to set the cap from — a cap below the max\n"
          "means at least one task would have been cut off mid-conversation.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("participant", nargs="?", help="e.g. PILOT, P01 (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show each exchange")
    args = parser.parse_args()
    return report(args.participant, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
