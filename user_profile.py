"""User profile learning: fetch a URL, summarize the user, and store remembered facts."""
import json
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from config import LLM_MODEL

PROFILE_FILE = Path("user_profile.json")
llm_profile = ChatGroq(model=LLM_MODEL)


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


def learn_from_url(url: str) -> str:
    """Fetch the URL, summarize the person, and save it. Returns a status message."""
    page_text = fetch_page_text(url)
    if page_text.startswith("FETCH_ERROR"):
        return f"Couldn't fetch {url}. Error: {page_text}"
    if len(page_text) < 100:
        return f"Page at {url} returned almost no text — likely blocked or requires login."

    summary = llm_profile.invoke([
        SystemMessage(content=(
            "You will be given the text content of a webpage that belongs to or describes a person. "
            "Write a concise profile of this person — their likely interests, profession, communication "
            "style, personality, and anything else useful for a personal assistant to know. "
            "Keep it under 200 words. Be specific. Do not invent facts not supported by the text."
        )),
        HumanMessage(content=f"URL: {url}\n\nPage text:\n{page_text}")
    ]).content

    profile = load_profile()
    profile["sources"] = profile.get("sources", [])
    profile["sources"].append(url)
    profile["summary"] = summary
    save_profile(profile)

    return f"Learned about user from {url}. Summary: {summary}"


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