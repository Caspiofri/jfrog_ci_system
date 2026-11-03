"""Where JFrog is mentioned (D77): a read-only snippet around the first JFrog match in an item's stored text.

The match uses the mentions_jfrog flag's own pattern and text, imported from ci.classify and not changed: JFROG_RE over
the title and content_text, with URLs and bare domains not counted. No model call. The snippet is at most
SNIPPET_CHARS characters, never the article (D36).

status, only for an item whose flag is true (None otherwise):
- found: the match is in the stored characters; snippet holds it
- not_in_stored_text: the flag is true but no match is in the stored title or text. The flag also reads the whole
  fetched page while only the first 6,000 characters are stored (the D57 flag issue, deliberately not fixed)
"""
import re

from ci.classify import JFROG_RE, URL_RE, content_text

SNIPPET_CHARS = 280
BEFORE_CHARS = 100  # context kept before the match; the rest of the budget goes after it
ELLIPSIS = "…"
RAW_KEY = "jfrog_mention_match"  # a demo snapshot stores the match here, computed from the full text before the cut


def _squash(text: str) -> str:
    return " ".join((text or "").split())


def _first(text: str) -> re.Match | None:
    """The first JFROG_RE match that is not inside a URL or bare domain (the flag blanks those before searching)."""
    urls = [m.span() for m in URL_RE.finditer(text)]
    return next((m for m in JFROG_RE.finditer(text)
                 if not any(a <= m.start() < b or a < m.end() <= b for a, b in urls)), None)


def _window(text: str, m: re.Match) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    start = max(0, m.start() - BEFORE_CHARS)
    end = min(len(text), start + SNIPPET_CHARS)
    start = max(0, end - SNIPPET_CHARS)
    head, tail = start > 0, end < len(text)
    start += head  # make room for the ellipses inside the budget
    end -= tail
    return (ELLIPSIS if head else "") + text[start:end].strip() + (ELLIPSIS if tail else "")


def find(raw: dict) -> dict | None:
    """{"snippet", "found_in": "text" | "title"} around the first match in the stored text, or in the title when the
    text has none (the flag reads both); None if neither has one."""
    for where, text in (("text", content_text(raw)), ("title", raw.get("title"))):
        text = _squash(text)
        m = _first(text)
        if m:
            return {"snippet": _window(text, m), "found_in": where}
    return None


def mention(raw: dict, flagged: bool) -> dict | None:
    """The API field: None when the flag is false, else {status, snippet, found_in}."""
    if not flagged:
        return None
    match = raw[RAW_KEY] if RAW_KEY in raw else find(raw)
    if match is None:
        return {"status": "not_in_stored_text", "snippet": None, "found_in": None}
    return {"status": "found", "snippet": match["snippet"], "found_in": match["found_in"]}
