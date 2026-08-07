"""User profile learning: fetch a URL, summarize the user, and store remembered facts."""
import json
import requests
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from config import LLM_MODEL, LLM_TIMEOUT_S, PROJECT_ROOT

# Project-root-anchored, not CWD-relative — see the Paths note in config.py.
PROFILE_FILE = PROJECT_ROOT / "user_profile.json"
llm_profile = ChatGroq(model=LLM_MODEL, timeout=LLM_TIMEOUT_S)


def fetch_page_text(url: str) -> str:
    """Fetch a public web page and extract readable text. Returns empty string on failure."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        return f"FETCH_ERROR: {e}"

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text[:8000]


def load_profile() -> dict:
    """Return current stored profile, or empty dict if none."""
    if PROFILE_FILE.exists():
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    return {}


def save_profile(profile: dict):
    PROFILE_FILE.write_text(json.dumps(profile, indent=2), encoding="utf-8")


# Below this, a source has too little content to summarize — a blocked page, a login wall,
# or a one-line bio. Better to say so than to store a summary the model largely invented.
MIN_SOURCE_CHARS = 100

# Deliberately source-neutral ("text", not "webpage") so a scraped page and a self-written
# bio go through the IDENTICAL prompt. A participant without a public URL would otherwise
# get a summary of a different shape than everyone else's, which is a per-participant
# difference in the one layer Arch 2 is built on.
PROFILE_SYSTEM_PROMPT = (
    "You will be given text that belongs to or describes a person. "
    "Write a concise profile of this person — their likely interests, profession, communication "
    "style, personality, and anything else useful for a personal assistant to know. "
    "Keep it under 200 words. Be specific. Do not invent facts not supported by the text. "
    # Plain prose, not markdown: this text is injected verbatim into the system prompt, and
    # only under arch2. A bulleted profile visibly pulls replies toward bulleted output —
    # which would be a style difference perfectly confounded with the arm, in an interface
    # whose base instructions specifically forbid lists (it is spoken aloud).
    "Write it as a short plain-prose paragraph. Do not use bullet points, numbered lists, "
    "headings, bold text, or any other markdown formatting."
)


def _summarize_person(source_line: str, text: str) -> str:
    return llm_profile.invoke([
        SystemMessage(content=PROFILE_SYSTEM_PROMPT),
        HumanMessage(content=f"{source_line}\n\nText:\n{text}")
    ]).content


def _store_summary(summary: str, source: str, source_type: str):
    """Overwrite the cold-start summary and record where it came from.

    `source_type` ("url" or "text") is kept so analysis can tell which participants had a
    scraped profile and which wrote their own — the two are not equivalent inputs, and a
    result that hinges on the difference should be visible rather than buried.
    """
    profile = load_profile()
    profile["sources"] = profile.get("sources", [])
    profile["sources"].append(source)
    profile["summary"] = summary
    profile["source_type"] = source_type
    save_profile(profile)


def learn_from_url(url: str) -> str:
    """Fetch the URL, summarize the person, and save it. Returns a status message."""
    page_text = fetch_page_text(url)
    if page_text.startswith("FETCH_ERROR"):
        return f"Couldn't fetch {url}. Error: {page_text}"
    if len(page_text) < MIN_SOURCE_CHARS:
        return f"Page at {url} returned almost no text — likely blocked or requires login."

    summary = _summarize_person(f"URL: {url}", page_text)
    _store_summary(summary, url, "url")
    return f"Learned about user from {url}. Summary: {summary}"


def learn_from_text(text: str, label: str = "self-reported") -> str:
    """Build the cold-start profile from text the participant wrote about themselves.

    The fallback for a participant with no public URL. Runs the SAME summarizer as
    learn_from_url so the stored summary has the same shape — this is the one
    personalization layer Arch 2 has, and it should not vary in form by participant.

    Note this is still not equivalent to a scraped profile: self-written text is what
    someone chooses to disclose, a public page is what is already visible. `source_type`
    records which was used.
    """
    text = text.strip()
    if len(text) < MIN_SOURCE_CHARS:
        return (f"Only {len(text)} characters of text — too little to build a profile from "
                f"(need at least {MIN_SOURCE_CHARS}). Ask for a fuller description.")

    summary = _summarize_person(f"Source: {label}", text)
    _store_summary(summary, f"{label}:{len(text)}chars", "text")
    return f"Learned about user from {label}. Summary: {summary}"


def remember_fact(fact: str) -> str:
    """Append a fact to the user's remembered_facts list."""
    fact = fact.strip()
    if not fact:
        return "Nothing to remember — fact was empty."
    profile = load_profile()
    facts = profile.get("remembered_facts", [])
    # Avoid exact duplicates
    if fact in facts:
        return f"Already remembered: {fact}"
    facts.append(fact)
    profile["remembered_facts"] = facts
    save_profile(profile)
    return f"Got it — I'll remember: {fact}"


def forget_fact(fact_substring: str) -> str:
    """Remove any remembered fact containing the given substring (case-insensitive)."""
    profile = load_profile()
    facts = profile.get("remembered_facts", [])
    if not facts:
        return "Nothing to forget — no facts stored yet."
    sub = fact_substring.lower().strip()
    kept = [f for f in facts if sub not in f.lower()]
    removed = [f for f in facts if sub in f.lower()]
    if not removed:
        return f"No facts matched '{fact_substring}'."
    profile["remembered_facts"] = kept
    save_profile(profile)
    return f"Forgot: {'; '.join(removed)}"


def get_profile_summary() -> str:
    """Return URL-derived summary for prompt injection. Empty string if no summary."""
    profile = load_profile()
    return profile.get("summary", "")


def get_remembered_facts() -> list:
    """Return the list of remembered facts."""
    profile = load_profile()
    return profile.get("remembered_facts", [])