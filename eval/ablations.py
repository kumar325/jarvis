"""Instrumentation for evaluating Jarvis: tool-call tracing + feature ablations.

Each ablation turns off one personalization/retrieval component by patching the
functions `system_prompt.build_system_message` reads from, so we can measure
how much each component actually contributes to answer quality.
"""
import re
import shutil
from contextlib import contextmanager, ExitStack
from unittest.mock import patch

import agent_loop
import system_prompt
from preferences import retrieve_examples
from style_tracker import get_style_summary
from user_profile import PROFILE_FILE, get_remembered_facts


class _StubTool:
    """Drop-in replacement for a langchain tool that refuses to run."""
    name = "web_search"

    def invoke(self, args):
        return "[web_search disabled for this ablation config]"


# Which functions build_system_message() calls, keyed by ablation name.
# Empty list ("full") means no patches — the unmodified baseline.
#
# The old no_style and no_prefs configs are gone, and no_memory now covers only the
# profile: as of the Arch 2 change, system_prompt.py injects the URL-derived profile and
# nothing else, so there is no style/facts/preference text left in the prompt for those
# configs to ablate. Patching functions system_prompt no longer imports would raise
# AttributeError, and reporting a ~0 delta for a layer that isn't there would be worse.
# Restore them alongside the corresponding injection blocks if a layer comes back.
ABLATION_PATCHES = {
    "full": [],
    "no_memory": [
        ("system_prompt.get_profile_summary", {"return_value": ""}),
    ],
    "no_web_search": [],  # handled separately via TOOLS_BY_NAME stub below
}


def reset_conversation():
    """Clear Jarvis's in-memory conversation so each test query starts fresh."""
    agent_loop.conversation.clear()


@contextmanager
def apply_ablation(name: str):
    """Patch out one personalization/retrieval component for the duration of the block."""
    if name not in ABLATION_PATCHES:
        raise ValueError(f"Unknown ablation config: {name}")
    with ExitStack() as stack:
        for target, kwargs in ABLATION_PATCHES[name]:
            stack.enter_context(patch(target, **kwargs))
        if name == "no_web_search":
            stack.enter_context(patch.dict(agent_loop.TOOLS_BY_NAME, {"web_search": _StubTool()}))
        yield


@contextmanager
def capture_tool_trace():
    """Wrap every tool so its (name, args, result) is recorded — this is our 'retrieved context'."""
    trace = []
    originals = dict(agent_loop.TOOLS_BY_NAME)

    def make_wrapper(tool_name, real_tool):
        class _Wrapper:
            def invoke(self, args):
                result = real_tool.invoke(args)
                trace.append({"tool": tool_name, "args": args, "result": str(result)})
                return result
        return _Wrapper()

    wrapped = {name: make_wrapper(name, t) for name, t in originals.items()}
    with patch.dict(agent_loop.TOOLS_BY_NAME, wrapped):
        yield trace


def snapshot_system_state(query: str) -> dict:
    """Record which personalization signals were actually available for this query,
    under whatever ablation patches are currently active. Raw signal text is included
    under underscore-prefixed keys so callers can check whether the signal actually
    surfaced in the response (see check_personalization_used); pop them before
    writing a row to the CSV.

    Only `profile_summary` is read through system_prompt, because it's the only signal
    system_prompt still injects — and therefore the only one an ablation patch can affect.
    Facts, style, and preferences are read from their own modules: they report what is
    sitting on disk, NOT what reached the prompt. Non-zero values in those columns mean
    leftover state from a previous participant, not active personalization.
    """
    profile_summary = system_prompt.get_profile_summary()
    facts = get_remembered_facts()
    style_summary = get_style_summary()
    good, bad = retrieve_examples(query)
    return {
        "facts_count": len(facts),
        "has_profile": bool(profile_summary),
        "has_style": bool(style_summary),
        "good_examples": len(good),
        "bad_examples": len(bad),
        "_facts": facts,
        "_profile_summary": profile_summary,
        "_style_summary": style_summary,
        "_good_examples": good,
        "_bad_examples": bad,
    }


@contextmanager
def preserve_file(path):
    """Snapshot a file before the eval run mutates it (e.g. the remember tool writing
    to user_profile.json for real) and restore it afterward, even if the run fails."""
    existed = path.exists()
    backup = path.with_suffix(path.suffix + ".eval_backup")
    if existed:
        shutil.copy2(path, backup)
    try:
        yield
    finally:
        if existed:
            shutil.copy2(backup, path)
            backup.unlink()
        elif path.exists():
            path.unlink()


_STOPWORDS = {
    "the", "user", "and", "that", "this", "with", "from", "have", "their",
    "been", "were", "for", "are", "was", "you", "your", "would", "should",
    "could", "about", "when", "what", "they", "them", "then", "some", "just",
}


def _keywords(text: str) -> set:
    """Extract lowercase content words (len > 3, minus stopwords) for overlap checks."""
    return {w for w in re.findall(r"[a-zA-Z']+", (text or "").lower()) if len(w) > 3 and w not in _STOPWORDS}


# Generic tone words ("short", "casual") are useless as markers here: Jarvis's baseline
# system prompt ALREADY mandates short, casual replies regardless of style mirroring, so
# almost every response would match and the check would never say False. Two exceptions
# that are NOT confounded with the baseline persona (which is casual/short by default):
# a response actually being technical or formal is only explained by the style guide
# asking for it. For everything else, match on the literal quoted phrases the style
# analysis calls out (e.g. "sorry", "what's...") — those are specific to this user's
# style, not to Jarvis's default persona, so a literal match is real evidence of mirroring.
_STYLE_TONE_MARKERS = {
    "technical": lambda r: bool(re.search(r"\b(implementation|architecture|algorithm|protocol)\b", r.lower())),
    "formal": lambda r: r[:1].isupper() and r.rstrip().endswith("."),
}


def _quoted_snippets(text: str) -> list:
    """Pull short quoted phrases out of style-analysis prose, e.g. “what's...”, “sorry”."""
    return re.findall(r'["“]([^"”]{2,30})["”]', text or "")


def check_personalization_used(response: str, facts: list, profile_summary: str,
                                style_summary: str, good_examples: list, bad_examples: list) -> bool:
    """Whether a personalization signal that was LOADED into the prompt actually left a
    detectable trace in the response — distinguishes 'feature fired' from 'feature sat idle'.
    Facts/profile/examples: keyword overlap with the response. Style: literal quoted-phrase
    match plus a couple of tone markers that aren't already true of Jarvis's default persona.
    """
    resp_kw = _keywords(response)
    if resp_kw:
        for fact in facts:
            if _keywords(fact) & resp_kw:
                return True
        if profile_summary and _keywords(profile_summary) & resp_kw:
            return True
        for ex in list(good_examples) + list(bad_examples):
            if _keywords(ex.get("reply", "")) & resp_kw:
                return True
    if style_summary:
        for snippet in _quoted_snippets(style_summary):
            if _keywords(snippet) & resp_kw:
                return True
        style_lower = style_summary.lower()
        for marker, exhibits in _STYLE_TONE_MARKERS.items():
            if marker in style_lower and exhibits(response):
                return True
    return False
