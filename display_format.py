"""Strip markdown from a reply before it is displayed, logged and spoken.

The web UI renders replies as plain text, so any markup the model writes despite the
prompt's RESPONSE FORMAT rules shows up as literal asterisks and pound signs. This is the
guarantee: structure is kept as line breaks and blank lines, the symbols are dropped.

Applied in backend/server.py straight after ask_jarvis(), *before* register_exchange(),
so what the participant reads, what ratings.jsonl stores and what they rate are the same
text. Deterministic, offline and arm-blind (no LLM, no profile, no condition), so it can't
become a second personalization channel. Never raises: on any failure the raw reply is
returned unchanged, which is the old behavior.
"""

import re

_FENCE = re.compile(r"^\s*```.*$")
_TABLE_RULE = re.compile(r"^\s*\|?[\s:|+-]{3,}\|?\s*$")
_HRULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_QUOTE = re.compile(r"^\s*>+\s?")
_BULLET = re.compile(r"^\s*[-*+•]\s+")


def _is_rule(line: str) -> bool:
    """Table divider (|---|---|) or horizontal rule (---): pure decoration, dropped."""
    return bool(_TABLE_RULE.fullmatch(line) and "|" in line or _HRULE.fullmatch(line))


def _clean_line(line: str) -> str:
    line = _HEADING.sub("", line)
    line = _QUOTE.sub("", line)
    line = _BULLET.sub("", line)
    if line.count("|") >= 2:
        # Table row: outer pipes go, inner ones become commas.
        line = re.sub(r"^\s*\|\s*|\s*\|\s*$", "", line)
        line = re.sub(r"\s*\|\s*", ", ", line)
    line = line.strip()

    line = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1 (\2)", line)   # [text](url)
    line = re.sub(r"`+([^`]*)`+", r"\1", line)                        # inline code
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)                      # bold
    line = re.sub(r"__(.+?)__", r"\1", line)
    line = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", line)   # italics
    line = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", line)   # not snake_case
    line = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", " times ", line)          # 5 * 3
    line = line.replace("*", "")
    return re.sub(r" {2,}", " ", line).strip()


def clean_for_display(text: str) -> str:
    """Markdown-free version of `text`, with structure kept as line breaks."""
    try:
        lines = [_clean_line(l) for l in text.splitlines()
                 if not _FENCE.match(l) and not _is_rule(l)]
        cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
        return cleaned or text
    except Exception as e:
        print(f"[display_format] cleanup failed, showing raw reply: {e}")
        return text
