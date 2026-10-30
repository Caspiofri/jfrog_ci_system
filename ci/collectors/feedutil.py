"""Shared helpers for the RSS/Atom collectors (vendor feeds, GitHub releases): fetch, entry date, HTML to text."""
import re
import time
import warnings
from datetime import UTC, datetime

import feedparser
import requests
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning

from ci.packet import FEED_FULL_MIN_CHARS

TIMEOUT = 20
TEXT_MAX_CHARS = 4000  # a teaser; the pipeline replaces it with the page text when it can fetch one
# some vendor sites (Cloudflare-fronted) answer 403 to non-browser agents
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
}


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    """Fetch and parse a feed. Raises on HTTP errors and on a body that is not a feed (an HTML 404 or login page,
    which may even be well-formed and so not flagged bozo)."""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    # bytes, so feedparser honours the XML encoding declaration; the URL lets it resolve relative links
    feed = feedparser.parse(resp.content, response_headers={"content-location": url})
    if not feed.version or (feed.bozo and not feed.entries):
        raise ValueError(f"not a feed ({feed.get('bozo_exception') or 'no RSS/Atom root'})")
    return feed


def entry_date(entry) -> datetime | None:
    """Published, else updated, as tz-aware UTC (feedparser normalises both to UTC struct_time)."""
    parsed: time.struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*parsed[:6], tzinfo=UTC) if parsed else None


FEED_BODY_MAX_CHARS = 50_000  # a complete feed body is kept whole; the pipeline counts mentions, then caps it


def html_to_text(html: str, max_chars: int = TEXT_MAX_CHARS) -> str:
    with warnings.catch_warnings():  # bs4 warns when a short snippet looks like a URL or a file name
        warnings.simplefilter("ignore", MarkupResemblesLocatorWarning)
        # wrapped: bs4's html.parser drops a bare "&T" at the very end of input ("AT&T" -> "ATT")
        text = BeautifulSoup(f"<div>{html or ''}</div>", "html.parser").get_text(" ", strip=True)
    return " ".join(text.split())[:max_chars]


def entry_html(entry) -> str:
    """The richest body the entry carries: Atom content, else the summary."""
    content = entry.get("content")
    return content[0].get("value", "") if content else entry.get("summary", "")


# how a truncated feed body ends: an explicit "Read more", "Continue reading →", "[…]" or "[...]" at any length;
# a bare trailing "…" or "..." only on a short body (a long complete post may end on an ellipsis or a code sample)
EXPLICIT_TEASER_END_RE = re.compile(r"(?:read\s+more|continue\s+reading|read\s+the\s+(?:full|rest)(?:\s+\w+)?|"
                                    r"\[\s*(?:…|\.\.\.)\s*\])[\s\W]*$", re.IGNORECASE)
ELLIPSIS_END_RE = re.compile(r"(?:…|\.\.\.)[\s\W]*$")
ELLIPSIS_MAX_CHARS = 2 * FEED_FULL_MIN_CHARS


def looks_truncated(text: str) -> bool:
    tail = text[-120:]
    if EXPLICIT_TEASER_END_RE.search(tail):
        return True
    return len(text) < ELLIPSIS_MAX_CHARS and bool(ELLIPSIS_END_RE.search(tail))


def feed_body(entry) -> tuple[str, bool]:
    """(text, complete): the entry's text, and whether it is a full body (content, not just a summary) long enough
    to stand for the item (FEED_FULL_MIN_CHARS) and not cut off ("Read more", "[…]"). A complete body is kept
    whole; a teaser is capped as before, and the pipeline fetches its page."""
    if entry.get("content"):
        text = html_to_text(entry_html(entry), max_chars=FEED_BODY_MAX_CHARS)
        if len(text) >= FEED_FULL_MIN_CHARS and not looks_truncated(text):
            return text, True
        return text[:TEXT_MAX_CHARS], False
    return html_to_text(entry.get("summary", "")), False


def short_error(origin: str, e: Exception) -> str:
    return f"{origin}: {type(e).__name__}: {e}"[:300]
