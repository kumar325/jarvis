"""Append-only CSV log of the post-task evaluation survey.

One row per completed task, written under study_data/ (already gitignored) next to
ratings.jsonl. CSV rather than JSONL because this file is meant to be opened directly in
Excel/Sheets for analysis — it is small (3 rows per participant per arch) and every field
is a scalar, so there is nothing JSONL would buy.

Kept deliberately separate from ratings.py: a thumbs up/down is per-response and there are
many per task, while this is one considered judgement per task. Mixing them into one file
would mean every analysis query had to filter by kind first.

This file is never wiped between participants — reset_user_state.py only clears the three
personalization JSON files and archives *into* study_data/, so the survey log accumulates
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
SURVEY_DIR = PROJECT_ROOT / "study_data"
SURVEY_PATH = SURVEY_DIR / "survey_responses.csv"

# How many tasks each participant does per architecture arm. Reaching this count is what
# flips the UI to "arch complete" instead of returning to the input box.
TASKS_PER_ARCH = 3

# Column order is the file's contract — analysis scripts and a human opening this in Excel
# both depend on it. Append new columns at the end; never reorder.
FIELDNAMES = [
    "participant_id",
    "arch",
    "task_number",
    "personalized_rating",
    "accuracy_rating",
    "trust_rating",
    "timestamp",
    # Not required by the analysis, but it is the only way to tie a survey row back to the
    # exact conversation in ratings.jsonl — those rows carry the same session id.
    "session_id",
]

# Guards the read-modify-write in record_survey(): the task number is derived from the row
# count, so two writers (a second tab, a fast double-click) could otherwise both read N and
# both write task N+1.
_write_lock = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _count_unlocked(participant_id: str, arch: str) -> int:
    """How many tasks this participant has already completed in this arm."""
    if not SURVEY_PATH.exists():
        return 0
    try:
        with SURVEY_PATH.open("r", encoding="utf-8", newline="") as f:
            return sum(
                1
                for row in csv.DictReader(f)
                if row.get("participant_id") == participant_id and row.get("arch") == arch
            )
    except OSError:
        # An unreadable log must not take the session down — the caller falls back to
        # treating this as the first task and the operator sees the row land with an
        # obviously wrong task number rather than losing the response entirely.
        return 0


def _append_unlocked(record: dict) -> None:
    SURVEY_DIR.mkdir(parents=True, exist_ok=True)
    # Header written only when the file is being created, so appends never repeat it.
    write_header = not SURVEY_PATH.exists() or SURVEY_PATH.stat().st_size == 0
    # newline="" is required on Windows — without it csv's own \r\n becomes \r\r\n and
    # every other row reads as blank.
    with SURVEY_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(record)


def count_completed_tasks(participant_id: str, arch: str) -> int:
    with _write_lock:
        return _count_unlocked(participant_id, arch)


def record_survey(
    session_id: str,
    participant_id: str,
    arch: str,
    personalized_rating: int,
    accuracy_rating: str,
    trust_rating: int,
) -> int:
    """Append one survey response and return the task number it was recorded as.

    The task number is assigned here rather than sent by the client so a refreshed browser
    (which resets all frontend state) can't restart the count at 1 and overwrite task 1's
    row with task 2's answers.
    """
    with _write_lock:
        task_number = _count_unlocked(participant_id, arch) + 1
        _append_unlocked(
            {
                "participant_id": participant_id,
                "arch": arch,
                "task_number": task_number,
                "personalized_rating": personalized_rating,
                "accuracy_rating": accuracy_rating,
                "trust_rating": trust_rating,
                "timestamp": utc_now_iso(),
                "session_id": session_id,
            }
        )
        return task_number
