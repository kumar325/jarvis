"""Show exactly which personalization layers are live in the built system prompt.

Usage:  python inspect_prompt.py "some query"
No API calls unless preferences.json is non-empty (then one local embedding).
"""
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

# Same cp1252 guard agent_loop.py uses — the base prompt contains non-ASCII.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from config import STUDY_CONDITION, profile_injection_enabled
from system_prompt import build_system_message
from user_profile import get_profile_summary, get_remembered_facts
from style_tracker import get_style_summary
from preferences import retrieve_examples

args = [a for a in sys.argv[1:] if a != "--demo"]
DEMO = "--demo" in sys.argv
query = args[0] if args else "what should I eat tonight?"

DEMO_SUMMARY = (
    "This person is a computer science student focused on machine learning and "
    "conversational AI. They write tersely, prefer concrete detail over hedging"
)

# --demo patches the cold-start layer in memory only. Nothing is written to disk,
# so user_profile.json is never touched (see CLAUDE.md).
ctx = (patch("system_prompt.get_profile_summary", return_value=DEMO_SUMMARY)
       if DEMO else nullcontext())

profile = DEMO_SUMMARY if DEMO else get_profile_summary()
facts = get_remembered_facts()
style = get_style_summary()
good, bad = retrieve_examples(query)

# LIVE means "actually reaches the model", not "exists on disk". Under arch1 there is
# normally a perfectly good profile in user_profile.json that is deliberately not injected,
# and reporting that as LIVE would make this tool agree with the file instead of with the
# prompt — exactly the check it exists to provide.
profile_live = bool(profile) and profile_injection_enabled()
profile_detail = f"{len(profile)} chars"
if profile and not profile_injection_enabled():
    profile_detail += f"  (on disk, suppressed by condition={STUDY_CONDITION})"

rows = [
    ("2  URL profile (COLD START)", profile_live, profile_detail),
    ("3  Remembered facts", bool(facts), f"{len(facts)} facts"),
    ("4  Style summary", bool(style), f"{len(style)} chars"),
    ("5  Preference examples", bool(good or bad), f"{len(good)} good / {len(bad)} bad"),
]

print(f"\nQuery: {query!r}")
print(f"Condition: {STUDY_CONDITION}  (profile injection "
      f"{'ON' if profile_injection_enabled() else 'OFF'})\n")
print(f"{'LAYER':<32} {'LIVE':<6} DETAIL")
print("-" * 62)
for name, live, detail in rows:
    print(f"{name:<32} {'YES' if live else 'no':<6} {detail}")

with ctx:
    msg = build_system_message(query)

print(f"\nTotal system prompt: {len(msg.content)} chars"
      + ("   [--demo: cold-start layer faked in memory]" if DEMO else ""))
print("=" * 62)
print(msg.content)
