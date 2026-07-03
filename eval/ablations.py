"""Instrumentation for evaluating Jarvis: tool-call tracing + feature ablations.

Each ablation turns off one personalization/retrieval component by patching the
functions `system_prompt.build_system_message` reads from, so we can measure
how much each component actually contributes to answer quality.
"""
from contextlib import contextmanager, ExitStack
from unittest.mock import patch

import agent_loop
import system_prompt


class _StubTool:
    """Drop-in replacement for a langchain tool that refuses to run."""
    name = "web_search"

    def invoke(self, args):
        return "[web_search disabled for this ablation config]"


# Which functions build_system_message() calls, keyed by ablation name.
# Empty list ("full") means no patches — the unmodified baseline.
ABLATION_PATCHES = {
    "full": [],
    "no_memory": [
        ("system_prompt.get_profile_summary", {"return_value": ""}),
        ("system_prompt.get_remembered_facts", {"return_value": []}),
    ],
    "no_style": [
        ("system_prompt.get_style_summary", {"return_value": ""}),
    ],
    "no_prefs": [
        ("system_prompt.retrieve_examples", {"return_value": ([], [])}),
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
    under whatever ablation patches are currently active."""
    good, bad = system_prompt.retrieve_examples(query)
    return {
        "facts_count": len(system_prompt.get_remembered_facts()),
        "has_profile": bool(system_prompt.get_profile_summary()),
        "has_style": bool(system_prompt.get_style_summary()),
        "good_examples": len(good),
        "bad_examples": len(bad),
    }
