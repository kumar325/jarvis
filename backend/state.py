"""Builds the SYSTEM VITALS payload from the real personalization files, reusing the
same load functions the agent itself uses for prompt injection (preferences.py,
user_profile.py, style_tracker.py) rather than re-reading the JSON independently."""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from preferences import load_prefs
from user_profile import get_remembered_facts, get_profile_summary
from style_tracker import get_style_summary

BUCKETS = 12
CLAUDE_MD = PROJECT_ROOT / "CLAUDE.md"
EXCLUDED_DIRS = {".venv", "__pycache__", "node_modules", ".git", ".claude", "jarvis_sandbox", "dist"}
DOCUMENT_EXTENSIONS = {".py", ".json", ".md", ".ts", ".tsx", ".css"}

_session_turns = 0


def record_turn():
    global _session_turns
    _session_turns += 1


def _bucketed_cumulative_count(n: int, buckets: int = BUCKETS) -> list[int]:
    """Cumulative count ramping from 0 to n over `buckets` steps, for sparklines."""
    if n <= 0:
        return [0] * buckets
    step = n / buckets
    return [round(min(n, step * b)) for b in range(1, buckets + 1)]


def _stat(id_: str, label: str, value: int, unit: str | None = None) -> dict:
    sparkline = _bucketed_cumulative_count(value)
    delta = sparkline[-1] - sparkline[-2] if len(sparkline) >= 2 else value
    stat = {"id": id_, "label": label, "value": value, "delta": delta, "sparkline": sparkline}
    if unit:
        stat["unit"] = unit
    return stat


def get_vitals() -> list[dict]:
    prefs = load_prefs()
    facts = get_remembered_facts()
    profile_summary = get_profile_summary()
    style_summary = get_style_summary()

    active_layers = sum([
        True,  # base instructions are always injected
        bool(profile_summary),
        bool(facts),
        bool(style_summary),
        bool(prefs),
    ])

    return [
        _stat("prefs", "PREFERENCE EXAMPLES", len(prefs)),
        _stat("facts", "REMEMBERED FACTS", len(facts)),
        {
            "id": "layers",
            "label": "PERSONALIZATION LAYERS",
            "value": active_layers,
            "unit": "/5",
            "delta": 0,
            "sparkline": [active_layers] * BUCKETS,
        },
        _stat("turns", "AGENT TURNS (SESSION)", _session_turns),
    ]


def get_directives() -> list[dict]:
    """Live directives sourced from CLAUDE.md's 'Paper todos' checklist."""
    if not CLAUDE_MD.exists():
        return []
    text = CLAUDE_MD.read_text(encoding="utf-8")
    parts = text.split("## Paper todos", 1)
    if len(parts) < 2:
        return []
    body = parts[1].split("\n## ", 1)[0]

    directives = []
    for i, (done_flag, label) in enumerate(re.findall(r"^- \[( |x)\] (.+)$", body, flags=re.MULTILINE)):
        directives.append({"id": f"d{i}", "label": label.strip(), "done": done_flag == "x"})
    return directives


def get_documents(limit: int = 6) -> list[dict]:
    """Most-recently-modified project files, as a live stand-in for 'recently accessed'."""
    candidates = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in filenames:
            if Path(filename).suffix in DOCUMENT_EXTENSIONS:
                candidates.append(Path(dirpath) / filename)

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    documents = []
    for i, path in enumerate(candidates[:limit]):
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        documents.append({
            "id": f"doc{i}",
            "name": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "accessedAt": mtime.strftime("%H:%M"),
        })
    return documents
