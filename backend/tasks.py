"""Append-only CSV log of task boundaries.

One row per completed task, written under study_data/ (already gitignored) next to
ratings.jsonl. It records *that* a task ended — never how it went. The three evaluation
questions (personalized / accurate / trust) are answered on a paper worksheet now, so the
only thing the app still owns is the boundary itself.

WHY A NEW FILE, NOT survey_responses.csv
----------------------------------------
That file holds pilot rows carrying the three answers. These rows never will. Appending
answer-less rows to it would leave one file whose name no longer describes its contents
and whose rating columns are empty for every row after a certain date — so every analysis
query would have to start by filtering blanks, and a reader a year from now would have to
work out which era a row came from. survey_responses.csv is frozen as historical pilot
data; nothing appends to it again. Do not merge the two.

Kept deliberately separate from ratings.py: a thumbs up/down is per-response and there are
many per task, while this is one row per task. Mixing them into one file would mean every
analysis query had to filter by kind first.

This file is never wiped between participants — reset_user_state.py only clears the three
personalization JSON files and archives *into* study_data/, so the task log accumulates
across the whole study. That is what makes count_completed_tasks() below work: the task
number is derived from what has already been logged for this (participant, arch), so it
survives a browser refresh or a backend restart mid-session.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASK_DIR = PROJECT_ROOT / "study_data"
TASK_EVENTS_PATH = TASK_DIR / "task_events.csv"

# How many tasks each participant does per architecture arm. Reaching this count is what
# flips the UI to "arch complete" instead of returning to the input box.
TASKS_PER_ARCH = 3

# Column order is the file's contract — analysis scripts and a human opening this in Excel
# both depend on it. Append new columns at the end; never reorder.
FIELDNAMES = [
    "participant_id",
    "arch",
    "task_number",
    "timestamp",
    # The only way to tie a task boundary back to the exact conversation in ratings.jsonl —
    # those rows carry the same session id. With the survey answers now on paper, this is
    # also what lets a worksheet be matched to its digital transcript after the fact.
    "session_id",
    # 1 if this was the participant's first arm, 2 if their second. Without it, "arch2
    # scored higher" cannot be separated from "the second arm always scores higher" — the
    # design is within-subjects, so order is confounded with architecture unless it is
    # both counterbalanced at the desk and recorded here.
    "arch_position",
]

# Guards the read-modify-write in record_task_complete(): the task number is derived from
# the row count, so two writers (a second tab, a fast double-click) could otherwise both
# read N and both write task N+1.
_write_lock = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _count_unlocked(participant_id: str, arch: str) -> int:
    """How many tasks this participant has already completed in this arm."""
    if not TASK_EVENTS_PATH.exists():
        return 0
    try:
        with TASK_EVENTS_PATH.open("r", encoding="utf-8", newline="") as f:
            return sum(
                1
                for row in csv.DictReader(f)
                if row.get("participant_id") == participant_id and row.get("arch") == arch
            )
    except OSError:
        # An unreadable log must not take the session down — the caller falls back to
        # treating this as the first task and the operator sees the row land with an
        # obviously wrong task number rather than losing the boundary entirely.
        return 0


def _append_unlocked(record: dict) -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)
    # Header written only when the file is being created, so appends never repeat it.
    write_header = not TASK_EVENTS_PATH.exists() or TASK_EVENTS_PATH.stat().st_size == 0
    # newline="" is required on Windows — without it csv's own \r\n becomes \r\r\n and
    # every other row reads as blank.
    with TASK_EVENTS_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(record)


def _other_arch_rows_unlocked(participant_id: str, arch: str) -> int:
    """How many tasks this participant has completed in the *other* arm."""
    if not TASK_EVENTS_PATH.exists():
        return 0
    try:
        with TASK_EVENTS_PATH.open("r", encoding="utf-8", newline="") as f:
            return sum(
                1
                for row in csv.DictReader(f)
                if row.get("participant_id") == participant_id
                and row.get("arch") not in (arch, None, "")
            )
    except OSError:
        return 0


def count_completed_tasks(participant_id: str, arch: str) -> int:
    with _write_lock:
        return _count_unlocked(participant_id, arch)


def arch_position(participant_id: str, arch: str) -> int:
    """Whether this arm is the participant's 1st or 2nd.

    Derived from the log rather than taken from a third env var: the moderator already has
    two labels to get right, and this one is recoverable from data they can't get wrong.
    If the other arm has any task rows for this participant, that arm ran first.

    Caveat worth knowing: an arm abandoned before its first "Finish Task" leaves no rows,
    so the following arm would also read as position 1. The startup line prints this, so
    a wrong value is visible before the participant sits down rather than at analysis.

    Reads only task_events.csv, not the frozen survey_responses.csv. A participant whose
    first arm ran under the old on-screen survey and whose second runs under this build
    would read as position 1 — that straddle can't happen for real participants (the
    change landed before collection), and reading both files would make the task numbering
    below ambiguous for no gain.
    """
    with _write_lock:
        return 2 if _other_arch_rows_unlocked(participant_id, arch) else 1


def record_task_complete(
    session_id: str,
    participant_id: str,
    arch: str,
    arch_position_value: int,
) -> int:
    """Append one task boundary and return the task number it was recorded as.

    The task number is assigned here rather than sent by the client so a refreshed browser
    (which resets all frontend state) can't restart the count at 1 and log two different
    tasks as task 1.
    """
    with _write_lock:
        task_number = _count_unlocked(participant_id, arch) + 1
        _append_unlocked(
            {
                "participant_id": participant_id,
                "arch": arch,
                "task_number": task_number,
                "timestamp": utc_now_iso(),
                "session_id": session_id,
                "arch_position": arch_position_value,
            }
        )
        return task_number
