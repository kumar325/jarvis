"""Append-only JSONL log of participant thumbs up/down ratings.

One line per rating, written under study_data/ (already gitignored) so participant data
never lands in the repo. Each record carries the session id, a pseudonymous participant
code, the per-response message id, and the text of the exchange being rated — the inputs
and outputs the study protocol says are recorded for analysis. It deliberately carries no
identifying fields: the protocol keeps name and email separate from task and survey
responses, so the code-to-person mapping is kept outside this repo.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RATINGS_DIR = PROJECT_ROOT / "study_data"
RATINGS_PATH = RATINGS_DIR / "ratings.jsonl"

SCHEMA_VERSION = 1

# Appends happen from a threadpool worker, and a second browser tab would be a second
# writer into the same file — one lock keeps lines from interleaving.
_write_lock = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def append_rating(record: dict) -> None:
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"schema_version": SCHEMA_VERSION, **record}, ensure_ascii=False)
    with _write_lock:
        with RATINGS_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
