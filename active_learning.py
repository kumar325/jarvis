"""Active learning: proactively ask the user questions to fill gaps in their profile."""
import json
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_MODEL
from user_profile import load_profile, save_profile

llm = ChatGroq(model=LLM_MODEL)

CORE_DIMENSIONS = {
    "occupation": "What kind of work or study are you involved in?",
    "location": "What city or region do you live in? Helps me with weather, local info, and time zones.",
    "schedule": "Are you more of a morning person or night owl? What does your typical day look like?",
    "interests": "What topics, hobbies, or subjects do you keep coming back to?",
    "diet": "Any dietary preferences or restrictions I should know about?",
    "tech_comfort": "How technical are you — do you work with code, data, or systems?",
    "goals": "What's the main thing you're trying to accomplish or improve right now?",
    "communication_style": "Do you prefer short direct answers, or more detail and context?",
}

# Session state — resets each process run
_asked_this_session = False
_pending_dimension = None  # dim name we're waiting for an answer on
_turn_count = 0


def record_turn():
    global _turn_count
    _turn_count += 1


def get_pending_dimension():
    return _pending_dimension


def set_pending_dimension(dim):
    global _pending_dimension
    _pending_dimension = dim


def mark_asked():
    global _asked_this_session
    _asked_this_session = True


def should_ask_this_turn() -> bool:
    """True only after turn 2+ and only once per session."""
    return not _asked_this_session and _turn_count >= 2


def _shallow_dims(profile: dict) -> list:
    """Return dim names that are missing or too short to be useful."""
    stored = profile.get("profile_dimensions", {})
    all_dims = {**CORE_DIMENSIONS, **profile.get("suggested_dimensions", {})}
    return [k for k in all_dims if len(stored.get(k, "").strip()) < 20]


def get_next_question():
    """Return (dim_name, question_text) for the next gap, or None if all filled."""
    profile = load_profile()
    shallow = _shallow_dims(profile)
    if not shallow:
        _maybe_suggest_new_dimensions(profile)
        return None
    dim = shallow[0]
    all_questions = {**CORE_DIMENSIONS, **profile.get("suggested_dimensions", {})}
    return dim, all_questions.get(dim, f"Can you tell me about your {dim.replace('_', ' ')}?")


def save_dimension_answer(dimension_name: str, answer: str) -> str:
    """Save a profile dimension answer into user_profile.json."""
    answer = answer.strip()
    if not answer:
        return "Nothing to save — answer was empty."
    profile = load_profile()
    dims = profile.get("profile_dimensions", {})
    dims[dimension_name] = answer
    profile["profile_dimensions"] = dims
    save_profile(profile)
    return f"Saved profile[{dimension_name}]."


def get_profile_dimensions_summary() -> str:
    """Return filled profile dimensions for system prompt injection."""
    profile = load_profile()
    dims = profile.get("profile_dimensions", {})
    if not dims:
        return ""
    return "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in dims.items())


def _maybe_suggest_new_dimensions(profile: dict) -> None:
    """Ask the LLM to suggest new dimensions. Runs once, when all core dims are filled."""
    if profile.get("suggested_dimensions"):
        return  # already have suggestions
    known = set(CORE_DIMENSIONS) | set(profile.get("profile_dimensions", {}))
    try:
        response = llm.invoke([
            SystemMessage(content=(
                "You help a personal AI assistant know its user better. "
                "Suggest 2-3 NEW profile dimensions not already tracked that would make "
                "the assistant significantly more useful. "
                "Return ONLY valid JSON: {\"dim_name\": \"question to ask the user\", ...}. "
                "Keys must be snake_case, 1-3 words. No markdown, no explanation."
            )),
            HumanMessage(content=f"Already tracked dimensions: {', '.join(sorted(known))}")
        ])
        raw = response.content.strip()
        # Strip markdown code fences if the LLM wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        suggestions = json.loads(raw)
        if isinstance(suggestions, dict):
            profile["suggested_dimensions"] = {
                k: v for k, v in suggestions.items() if k not in known
            }
            save_profile(profile)
    except Exception:
        pass  # silently skip bad LLM output — will retry next time
