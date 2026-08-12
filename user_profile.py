"""User profile learning: fetch a URL, summarize the user, and store remembered facts."""
import json
import re
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


# Everything from one of these headings onward in a LinkedIn "Save to PDF" export is about
# OTHER people or about the page itself: suggested connections and their job titles, who
# else viewers looked at, promoted company pages, the site footer. Extracted verbatim it
# reads as one continuous document about the participant, so the summarizer has no way to
# tell the participant's own history from the four strangers listed under "People you may
# know" — and unlike a wrong URL, nothing looks wrong at the command line.
#
# Matched against whole lines, case-insensitively. Deliberately conservative: LinkedIn
# changes its layout, and a marker that stops matching leaves chrome in (annoying, and the
# summarizer prompt is the second line of defence) rather than truncating real content.
_PDF_CHROME_MARKERS = (
    "people you may know",
    "who your viewers also viewed",
    "you might like",
    "pages for you",
    "more profiles for you",
    "interests",
)

# Page furniture that appears *above* the cut and can't be handled by truncation. These are
# whole-line matches too, so a line that merely contains one of these words survives.
_PDF_CHROME_LINES = re.compile(
    r"^\s*(?:"
    r"homepage|open to|add section|enhance profile|get started|show all(?: \d+ \w+)?|"
    r"suggested for you|private to you|analytics|activity|create a post|"
    r"posts comments images|view analytics|show credential|connect|follow|following|view|"
    r"profile language|safety center|questions\?|select language|"
    r"\d+(?:,\d+)*\+? (?:connections|followers|profile views|post impressions|"
    r"search appearances|impressions|endorsements)|"
    r"linkedin corporation.*"
    r")\s*$",
    re.IGNORECASE,
)


def _strip_export_chrome(text: str) -> str:
    """Drop the parts of a social-profile PDF export that aren't about the participant.

    Applied to PDF sources only. A scraped URL goes through BeautifulSoup, which already
    drops nav/footer, and self-written text has no chrome to strip — running this over
    either would risk deleting real content to solve a problem they don't have.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower() in _PDF_CHROME_MARKERS:
            lines = lines[:i]
            break
    kept = [ln for ln in lines if ln.strip() and not _PDF_CHROME_LINES.match(ln)]
    return "\n".join(kept)


def extract_pdf_text(path) -> str:
    """Text of a PDF, with export chrome removed. Returns "" for a scanned/image-only file.

    An empty return is left to the caller's MIN_SOURCE_CHARS check rather than raised: a
    scanned PDF is a bad *source*, not a crash, and it should land in `failed` alongside a
    dead URL so the operator sees one consistent report.
    """
    from pypdf import PdfReader  # local: only the profile-seeding path needs it

    reader = PdfReader(str(path))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    # Ligatures and smart punctuation survive extraction and end up in the system prompt.
    for bad, good in (("ﬁ", "fi"), ("ﬂ", "fl"), ("’", "'"), ("‘", "'"),
                      ("“", '"'), ("”", '"'), ("–", "-"), ("—", "-")):
        raw = raw.replace(bad, good)
    return _strip_export_chrome(raw).strip()


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
    "You will be given text that belongs to or describes a person, possibly gathered from "
    "more than one source. Write ONE unified profile of this person — their likely interests, "
    "profession, communication "
    "style, personality, and anything else useful for a personal assistant to know. "
    "Do not summarize the sources separately or mention them; merge them into a single "
    "description, and if they disagree prefer the more specific detail. "
    # The stored text is injected under "WHAT YOU KNOW ABOUT THE USER", so person matters.
    # A bio written ABOUT the participant by someone else ("My dad is 54...") otherwise
    # produces "Your dad is a 54-year-old...", and the assistant then believes its user is
    # the author rather than the subject — quietly personalizing for the wrong person.
    "The person described IS the assistant's user. Always write about them in the third "
    "person as 'this person' or 'they', whoever the source text is addressed to and "
    "whatever person it is written in. Never write 'your dad', 'my friend', or similar. "
    # Second line of defence behind _strip_export_chrome(). A profile export lists other
    # people — suggested connections, who-else-viewed, endorsers — and a marker the stripper
    # no longer matches would otherwise merge a stranger's job title into the participant.
    "The text describes exactly ONE person. Other people's names may appear in it as "
    "connections, suggestions, endorsements, colleagues, or followers — they are incidental. "
    "Ignore them completely and never merge their details into the profile. "
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


def _store_summary(summary: str, sources: list, source_type: str):
    """Overwrite the cold-start summary and record where it came from.

    `source_type` ("url", "text", "pdf", or a "+"-joined mix) is kept so analysis can tell
    which participants had a scraped profile, which wrote their own, which supplied an
    exported document, and which had several — these are not equivalent inputs, and a
    result that hinges on the difference should be visible rather than buried.
    """
    profile = load_profile()
    profile["sources"] = profile.get("sources", [])
    profile["sources"].extend(sources)
    profile["summary"] = summary
    profile["source_type"] = source_type
    save_profile(profile)


# Budget for the combined source text sent to the summarizer. Split evenly across sources
# rather than truncating the concatenation, so a long first source can't crowd a later one
# out entirely — a profile silently built from one of two sources is worse than a short one.
MAX_TOTAL_SOURCE_CHARS = 20000


def learn_from_sources(urls=(), texts=(), pdfs=()) -> tuple[str, list[str]]:
    """Build ONE cold-start profile from any mix of public URLs, written text, and PDFs.

    `texts` is a list of (label, content) pairs. `pdfs` is a list of paths. Returns
    (status_message, failed_sources).

    PDFs are a separate parameter rather than pre-extracted into `texts` so `source_type`
    can tell them apart. An exported profile page is the same kind of disclosure as a
    scraped URL — already public — whereas `texts` is what a participant chose to write
    about themselves. Folding one into the other would record every PDF as self-written.

    Every source goes into a single summarization call rather than one call each, because
    the stored profile has exactly one `summary` field — summarizing per source would mean
    the last one silently overwrote the rest. That was why --profile-url and
    --profile-text-file used to be mutually exclusive.

    Partial failure is reported, not fatal: if one of two sources is unreachable, a profile
    built from the other is still usable, but the caller must surface which one was lost so
    the operator can decide whether to re-run.
    """
    blocks, failed = [], []
    pdf_labels = set()

    for url in urls:
        page = fetch_page_text(url)
        if page.startswith("FETCH_ERROR"):
            failed.append(f"{url} — {page}")
        elif len(page) < MIN_SOURCE_CHARS:
            failed.append(f"{url} — almost no text (blocked, or requires login)")
        else:
            blocks.append((url, page))

    for label, content in texts:
        content = (content or "").strip()
        if len(content) < MIN_SOURCE_CHARS:
            failed.append(f"{label} — only {len(content)} chars, need {MIN_SOURCE_CHARS}")
        else:
            blocks.append((label, content))

    for path in pdfs:
        label = getattr(path, "name", str(path))
        try:
            content = extract_pdf_text(path)
        except Exception as e:
            failed.append(f"{label} — could not read PDF: {e}")
            continue
        # A scanned or image-only export extracts to nothing. Reported like any other bad
        # source rather than raised, so one dead PDF alongside a working URL still seeds.
        if len(content) < MIN_SOURCE_CHARS:
            failed.append(
                f"{label} — only {len(content)} chars of extractable text "
                f"(scanned or image-only PDF?), need {MIN_SOURCE_CHARS}"
            )
        else:
            pdf_labels.add(label)
            blocks.append((label, content))

    if not blocks:
        return ("No usable source: " + "; ".join(failed)), failed

    per_source = MAX_TOTAL_SOURCE_CHARS // len(blocks)
    combined = "\n\n".join(
        f"--- Source: {label} ---\n{text[:per_source]}" for label, text in blocks
    )
    summary = _summarize_person(f"{len(blocks)} source(s) about one person", combined)

    labels = [label for label, _ in blocks]
    kinds = {
        "url" if label in urls else "pdf" if label in pdf_labels else "text"
        for label, _ in blocks
    }
    _store_summary(summary, labels, "+".join(sorted(kinds)))
    return f"Built profile from {len(blocks)} source(s): {', '.join(labels)}", failed


def learn_from_url(url: str) -> str:
    """Fetch the URL, summarize the person, and save it. Returns a status message.

    Kept as the single-source entry point for tools/web.py, the jarvis.py CLI and the eval
    harness. New callers wanting more than one source should use learn_from_sources.
    """
    status, _ = learn_from_sources(urls=[url])
    return status


def learn_from_text(text: str, label: str = "self-reported") -> str:
    """Build the cold-start profile from text the participant wrote about themselves.

    The fallback for a participant with no public URL. Runs the SAME summarizer as
    learn_from_url so the stored summary has the same shape — this is the one
    personalization layer Arch 2 has, and it should not vary in form by participant.

    Note this is still not equivalent to a scraped profile: self-written text is what
    someone chooses to disclose, a public page is what is already visible. `source_type`
    records which kinds were used.
    """
    status, _ = learn_from_sources(texts=[(label, text)])
    return status


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