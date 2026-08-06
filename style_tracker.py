"""Style mirroring: analyze recent user utterances and cache a style description."""
import json
import threading
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from config import LLM_MODEL, LLM_TIMEOUT_S, PROJECT_ROOT

# Project-root-anchored, not CWD-relative — see the Paths note in config.py.
STYLE_FILE = PROJECT_ROOT / "user_style.json"
llm_style = ChatGroq(model=LLM_MODEL, timeout=LLM_TIMEOUT_S)

# record_utterance is a read-modify-write of the whole file. It is now called from the
# backend's threadpool (backend/server.py) as well as the jarvis.py CLI, and a second
# browser tab is a second writer — without this, concurrent turns can lose utterances.
# Mirrors backend/ratings.py's _write_lock.
_write_lock = threading.Lock()

# How many recent user turns we keep to analyze style
BUFFER_SIZE = 20
# How often to re-run style analysis (every Nth turn)
ANALYSIS_INTERVAL = 5
# Minimum utterances before we bother analyzing
MIN_UTTERANCES = 3


def _load() -> dict:
    if STYLE_FILE.exists():
        return json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    return {"utterances": [], "style_summary": "", "turns_since_analysis": 0}


def _save(state: dict):
    STYLE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def record_utterance(user_text: str):
    """Save a new user utterance to the rolling buffer and maybe re-analyze."""
    user_text = user_text.strip()
    if not user_text:
        return

    with _write_lock:
        state = _load()
        state["utterances"].append(user_text)
        state["utterances"] = state["utterances"][-BUFFER_SIZE:]  # keep last N
        state["turns_since_analysis"] = state.get("turns_since_analysis", 0) + 1
        # Re-analyze periodically once we have enough data
        due = (
            len(state["utterances"]) >= MIN_UTTERANCES
            and state["turns_since_analysis"] >= ANALYSIS_INTERVAL
        )
        utterances = list(state["utterances"])
        # Persisted before the analysis rather than after it, so a Groq failure costs
        # only the summary refresh — previously it raised past _save() and dropped the
        # utterance entirely. turns_since_analysis is reset only on success below, so a
        # failed analysis is simply retried on the next turn.
        _save(state)

    if not due:
        return

    # Deliberately outside the lock: _analyze_style is a network call that can block for
    # LLM_TIMEOUT_S, and holding the lock across it would stall every other writer for
    # that long.
    summary = _analyze_style(utterances)

    with _write_lock:
        state = _load()
        state["style_summary"] = summary
        state["turns_since_analysis"] = 0
        _save(state)


def _analyze_style(utterances: list) -> str:
    sample = "\n".join(f"- {u}" for u in utterances)
    response = llm_style.invoke([
        SystemMessage(content=(
            "You are analyzing a user's speech style from recent things they've said. "
            "Write a SHORT style guide (2-4 short bullets) describing: sentence length, "
            "tone (casual/formal/technical), common phrases or filler words, energy level, "
            "and any quirks. This will be injected into another AI's prompt so it matches "
            "the user's style. Be specific and actionable, not generic."
        )),
        HumanMessage(content=f"Recent user utterances:\n{sample}")
    ])
    return response.content


def get_style_summary() -> str:
    """Return the cached style summary for prompt injection."""
    return _load().get("style_summary", "")
