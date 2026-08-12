"""Shorten a long reply into something worth listening to.

Jarvis spoke every reply in full, however long. Reading a 400-word answer aloud at
SPEECH_RATE takes over two minutes, and a participant cannot skim it, scroll back, or
skip ahead the way they can with the text on screen. So the screen keeps the full
answer and the speaker gets a summary of it.

Only the audio changes. The full reply is what the UI renders, what register_exchange()
stores, and what ends up in ratings.jsonl — a participant rates the answer they can
read, and analysis sees what the model actually said. eval/run_eval.py scores
ask_jarvis() output directly and never reaches this module at all.

Three properties this has to hold for the study:

  * It sees the reply and nothing else. No profile, no style, no preference examples —
    this is a bare llm_raw call, the same pattern verify_search_result uses. A
    summarizer that could read the profile would be a second personalization channel,
    and an Arch 2 result could no longer be attributed to the cold-start profile alone.
  * It is arm-blind. Same code, same threshold, same prompt under arch1 and arch2. The
    condition is never passed in and never consulted.
  * It never costs a turn. Any failure — timeout, API error, empty or nonsense output —
    falls back to speaking the reply in full, which is exactly the old behavior. Silence
    would be worse than a long answer.
"""
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from config import (
    LLM_MODEL,
    SPOKEN_SUMMARY_MAX_CHARS,
    SPOKEN_SUMMARY_MAX_WORDS,
    SPOKEN_SUMMARY_SENTENCES,
    SPOKEN_SUMMARY_TIMEOUT_S,
)

# Deliberately NOT the agent's llm: no tools bound, no system prompt, no conversation
# history. Its own client so the shorter timeout below can't affect the answer path.
llm_raw = ChatGroq(model=LLM_MODEL, timeout=SPOKEN_SUMMARY_TIMEOUT_S)

SUMMARY_SYSTEM_PROMPT = (
    f"You condense an assistant's written answer into what it should say out loud. "
    f"Write about {SPOKEN_SUMMARY_SENTENCES} sentences, and no more than "
    f"{SPOKEN_SUMMARY_MAX_WORDS} words in total.\n\n"
    "Rules:\n"
    f"- The word limit is the real constraint. {SPOKEN_SUMMARY_SENTENCES} sentences of "
    "60 words each is not a summary; keep the sentences short enough to say in one "
    "breath.\n"
    "- Cover the WHOLE answer, including how it ends. Do not just compress the opening "
    "paragraph and stop.\n"
    "- Speak as the assistant, to the user, in the same voice as the original. Say "
    "'you', not 'the user'. Never refer to 'the answer', 'the text' or 'the response'.\n"
    "- No preamble. Do not open with 'Here's a summary' or 'In short'. Your output is "
    "spoken directly as the reply.\n"
    "- Plain prose only. No markdown, no bullet points, no headings, no numbered lists, "
    "no asterisks. It is read aloud by a speech engine.\n"
    "- Drop anything that does not survive being spoken: URLs, code, file paths, long "
    "numbers. Describe them instead if they matter.\n"
    "- Add nothing. Do not answer the question yourself, do not correct it, and do not "
    "introduce facts, caveats or recommendations that are not already there.\n"
    "- Keep any uncertainty the original expressed. If it hedged or said it wasn't sure, "
    "so do you — dropping the hedge would overstate what it knows.\n"
    "- If it ends by asking the user something or naming a next step, keep that. It is "
    "the part they have to respond to."
)


def _log(message: str):
    """Operator-facing note. Every fallback here is silent to the participant by design —
    they just hear the full reply — so it has to be visible in the console, or a summarizer
    that has been failing all session looks exactly like one that never triggers."""
    print(f"[speech_summary] {message}", flush=True)


def needs_summary(text: str) -> bool:
    """Whether this reply is long enough to be worth summarizing.

    Short replies are spoken verbatim. Below the threshold a summary saves the listener
    little and costs an LLM call and its latency — and a "summary" of three sentences is
    mostly a paraphrase, which risks changing the answer for no benefit.
    """
    return len(text.strip()) > SPOKEN_SUMMARY_MAX_CHARS


def summarize_for_speech(text: str) -> str:
    """Return what should be SPOKEN for this reply — a summary, or the reply itself.

    Never raises and never returns empty: every failure path returns `text` unchanged,
    so the worst case is the pre-existing behavior of speaking the whole thing.
    """
    text = (text or "").strip()
    if not text or not needs_summary(text):
        return text

    try:
        summary = llm_raw.invoke([
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=text),
        ]).content
    except Exception as e:
        # Timeout, rate limit, transport error. The caller is about to speak; it gets the
        # full reply rather than an apology or silence.
        _log(f"summarizer call failed, speaking the full {len(text)}-char reply: {e}")
        return text

    summary = (summary or "").strip()

    # A summary that is empty, or no shorter than what it summarized, means the call went
    # wrong (a refusal, an echo of the input, a model that padded rather than condensed).
    # Speaking it would be strictly worse than speaking the original.
    if not summary or len(summary) >= len(text):
        _log(f"summary was empty or no shorter ({len(summary)} vs {len(text)} chars), "
             "speaking the full reply")
        return text
    return summary
