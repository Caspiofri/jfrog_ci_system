"""Vendor feeds collector: RSS and Atom parsing, keyword filter, window, and per-feed failure isolation (offline)."""
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from ci.collectors import feedutil, vendor_feeds
from ci.config import CIConfig

FIXTURES = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 10, 23, tzinfo=UTC)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.content, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")


def fake_get(routes: dict):
    """requests.get stand-in: url -> fixture file name, or an int HTTP status."""
    def get(url, headers=None, timeout=None):
        assert timeout and "Mozilla" in headers["User-Agent"]
        route = routes[url]
        if isinstance(route, int):
            return FakeResponse(b"<html>nope</html>", route)
        return FakeResponse((FIXTURES / route).read_bytes())
    return get


def cfg(feeds: list[dict]) -> CIConfig:
    return CIConfig(competitors=[{"key": "acme", "name": "Acme", "news_queries": ["Acme"], "feeds": feeds}])


def test_rss_entries_become_packets(monkeypatch):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://a/rss": "vendor_rss.xml"}))
    result = vendor_feeds.collect(cfg([{"url": "https://a/rss"}]), SINCE)
    assert result.source == "vendor_feed" and result.errors == []
    # the old and the undated entries are dropped
    assert [p.title for p in result.packets] == ["Acme launches package firewall", "Office party recap"]
    p = result.packets[0]
    assert p.source == "vendor_feed" and p.competitor == "acme" and p.publisher == "Acme"
    assert p.origin == "https://a/rss"
    assert p.url == p.original_url == "https://acme.example/blog/firewall"
    assert p.published_at == datetime(2026, 10, 28, 10, 0, tzinfo=UTC)  # +0200 normalised to UTC
    assert p.text == "Blocks malicious packages & more." and p.text_status == "snippet"


def test_atom_feed_uses_updated_date(monkeypatch):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://a/atom": "vendor_atom.xml"}))
    [p] = vendor_feeds.collect(cfg([{"url": "https://a/atom"}]), SINCE).packets
    assert p.title == "Supply chain policies GA"
    assert p.published_at == datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
    assert p.text == "Policies are now generally available."


@pytest.mark.parametrize("keywords,titles", [
    (["FIREWALL"], ["Acme launches package firewall"]),  # case-insensitive, title
    (["cake"], ["Office party recap"]),  # summary
    (["sbom"], []),  # the matching entry is outside the window
])
def test_keyword_filter(monkeypatch, keywords, titles):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://a/rss": "vendor_rss.xml"}))
    result = vendor_feeds.collect(cfg([{"url": "https://a/rss", "keywords": keywords}]), SINCE)
    assert [p.title for p in result.packets] == titles


def test_failing_feeds_are_isolated(monkeypatch):
    def get(url, headers=None, timeout=None):
        if url == "https://a/timeout":
            raise requests.Timeout("read timed out")
        return fake_get({"https://a/404": 404, "https://a/html": "not_a_feed.html",
                         "https://a/atom": "vendor_atom.xml"})(url, headers, timeout)

    monkeypatch.setattr(feedutil.requests, "get", get)
    urls = ["https://a/timeout", "https://a/404", "https://a/html", "https://a/atom"]
    result = vendor_feeds.collect(cfg([{"url": u} for u in urls]), SINCE)
    assert [p.title for p in result.packets] == ["Supply chain policies GA"]
    assert len(result.errors) == 3
    assert result.errors[0].startswith("https://a/timeout: Timeout")
    assert result.errors[1].startswith("https://a/404: HTTPError")
    assert result.errors[2].startswith("https://a/html: ValueError: not a feed")


def test_wellformed_html_page_is_an_error(monkeypatch):
    # a well-formed XHTML login page is not bozo, yet carries no feed: it must not pass as an empty feed
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://a/login": "login_page.xhtml"}))
    result = vendor_feeds.collect(cfg([{"url": "https://a/login"}]), SINCE)
    assert result.packets == [] and len(result.errors) == 1
    assert result.errors[0].startswith("https://a/login: ValueError: not a feed")


@pytest.mark.parametrize("keywords,kept", [
    (["code"], False),  # only in the <code> tag name, not in the text
    (["AT&T"], True),  # the title carries it as AT&amp;T
    (["acme scan"], True),  # text inside the markup still matches
])
def test_keywords_match_text_not_markup(monkeypatch, keywords, kept):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://acme.example/feed": "vendor_markup.xml"}))
    result = vendor_feeds.collect(cfg([{"url": "https://acme.example/feed", "keywords": keywords}]), SINCE)
    assert bool(result.packets) is kept


def test_relative_links_resolve_against_feed_url(monkeypatch):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://acme.example/feed": "vendor_markup.xml"}))
    [p] = vendor_feeds.collect(cfg([{"url": "https://acme.example/feed"}]), SINCE).packets
    assert p.url == p.original_url == "https://acme.example/news/att"


def test_dates_are_utc_under_a_non_utc_local_timezone(monkeypatch):
    monkeypatch.setattr(feedutil.requests, "get", fake_get({"https://a/rss": "vendor_rss.xml"}))
    monkeypatch.setenv("TZ", "Asia/Jerusalem")
    time.tzset()
    try:
        result = vendor_feeds.collect(cfg([{"url": "https://a/rss"}]), SINCE)
    finally:
        monkeypatch.undo()
        time.tzset()
    assert result.packets[0].published_at == datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
    assert all(p.published_at.utcoffset().total_seconds() == 0 for p in result.packets)


@pytest.mark.parametrize("html,text", [
    ("AT&T", "AT&T"),  # bare ampersand at the end of input survives
    ("AT&amp;T", "AT&T"),
    ("<p>Run <code>x</code>\n now</p>", "Run x now"),
    ("", ""),
])
def test_html_to_text(html, text):
    assert feedutil.html_to_text(html) == text
