"""Builds the SYSTEM VITALS payload from the real personalization files, reusing the
same load functions the agent itself uses for prompt injection (preferences.py,
user_profile.py, style_tracker.py) rather than re-reading the JSON independently."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from preferences import load_prefs
from user_profile import get_remembered_facts, get_profile_summary
from style_tracker import get_style_summary

BUCKETS = 12

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
