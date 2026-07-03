"""Style mirroring: analyze recent user utterances and cache a style description."""
import json
from pathlib import Path
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from config import LLM_MODEL

STYLE_FILE = Path("user_style.json")
llm_style = ChatGroq(model=LLM_MODEL)

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
    state = _load()
    state["utterances"].append(user_text)
    state["utterances"] = state["utterances"][-BUFFER_SIZE:]  # keep last N
    state["turns_since_analysis"] = state.get("turns_since_analysis", 0) + 1

    # Re-analyze periodically once we have enough data
    if (
        len(state["utterances"]) >= MIN_UTTERANCES
        and state["turns_since_analysis"] >= ANALYSIS_INTERVAL
    ):
        state["style_summary"] = _analyze_style(state["utterances"])
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
