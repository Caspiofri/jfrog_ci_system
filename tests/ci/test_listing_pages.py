"""Listing pages (GitHub changelog index): parsing, pagination window and cap, robots, failure isolation, and the
merge with feed entries in the vendor feeds collector (offline, fixtures modelled on github.blog/changelog)."""
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from ci.classify import own_sources
from ci.collectors import feedutil, listing_pages, vendor_feeds
from ci.collectors.listing_pages import parse_github_changelog, read_listing
from ci.config import CIConfig, ListingPage

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = "https://github.blog/changelog/"
PAGE = "https://github.blog/changelog/page/{n}/"
FEED = "https://github.blog/changelog/feed/"
ROBOTS = "https://github.blog/robots.txt"
PAGES = {LISTING: "github_changelog_p1.html", PAGE.format(n=2): "github_changelog_p2.html",
         PAGE.format(n=3): "github_changelog_p3.html"}


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.content, self.status_code = body, status
        self.text = body.decode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")


@pytest.fixture
def web(monkeypatch):
    """Patch HTTP for both the listing reader and the feed fetcher; routes: url -> fixture name, int status or
    text. Records every URL requested and every pause."""
    routes = {ROBOTS: 404, **PAGES}
    calls: list[str] = []
    sleeps: list[float] = []

    def get(url, headers=None, timeout=None):
        assert timeout and "Mozilla" in headers["User-Agent"]
        calls.append(url)
        route = routes.get(url, 404)
        if isinstance(route, int):
            return FakeResponse(b"<html>nope</html>", route)
        if isinstance(route, Exception):
            raise route
        if route.endswith((".html", ".xml")):
            return FakeResponse((FIXTURES / route).read_bytes())
        return FakeResponse(route.encode())

    monkeypatch.setattr(listing_pages.requests, "get", get)
    monkeypatch.setattr(feedutil.requests, "get", get)
    monkeypatch.setattr(listing_pages.time, "sleep", sleeps.append)
    return routes, calls, sleeps


def since(day: int) -> datetime:
    return datetime(2026, 10, day, 9, 30, tzinfo=UTC)


def titles(entries) -> list[str]:
    return [e.title for e in entries]


def test_parse_reads_title_link_and_day_and_skips_malformed_entries():
    entries = parse_github_changelog((FIXTURES / "github_changelog_p1.html").read_text(), LISTING)
    # no date, no link and an unreadable date are skipped
    assert titles(entries) == ["Webhook IP ranges added to the Meta API", "AI Scan for repositories in public preview",
                               "GitHub Actions workflow lockfiles are generally available", "Relative link entry"]
    ai_scan = entries[1]
    assert ai_scan.url == "https://github.blog/changelog/2026-10-28-ai-scan-for-repositories-in-public-preview"
    assert ai_scan.day == date(2026, 10, 28) and ai_scan.teaser == ""
    assert entries[3].url == "https://github.blog/changelog/2026-10-27-relative-link-entry"  # resolved


def test_pagination_stops_once_entries_are_older_than_since(web):
    _, calls, sleeps = web
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(21))
    assert errors == []
    assert calls == [ROBOTS, LISTING, PAGE.format(n=2)]  # page 2 reaches 10 Oct, so page 3 is never requested
    assert sleeps == [listing_pages.PAGE_DELAY_S]  # a pause before page 2
    assert titles(entries)[-2:] == ["Dependabot grouped security updates for npm",
                                    "Secret scanning push protection for gists"]
    assert all(e.day >= date(2026, 10, 21) for e in entries)


def test_window_includes_the_whole_day_of_since(web):
    entries, _ = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(20))  # 09:30 on 20 Oct
    assert "GitHub package firewall in public preview" in titles(entries)


def test_page_cap(web):
    _, calls, _ = web
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE, max_pages=2), since(1))
    assert PAGE.format(n=3) not in calls
    assert "Older entry on page two" in titles(entries)
    assert errors == [f"{LISTING}: stopped at the 2-page cap"]


def test_first_page_only_without_page_url(web):
    _, calls, _ = web
    entries, errors = read_listing(ListingPage(url=LISTING), since(1))
    assert calls == [ROBOTS, LISTING] and errors == [] and len(entries) == 4


def test_failed_second_page_keeps_the_first(web):
    routes, _, _ = web
    routes[PAGE.format(n=2)] = 429
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(1))
    assert len(entries) == 4
    assert len(errors) == 1 and errors[0].startswith(f"{PAGE.format(n=2)}: HTTPError: 429")


def test_timeout_on_first_page_is_an_error(web):
    routes, _, _ = web
    routes[LISTING] = requests.Timeout("read timed out")
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(1))
    assert entries == [] and errors == [f"{LISTING}: Timeout: read timed out"]


def test_unparseable_first_page_is_an_error(web):
    routes, _, _ = web
    routes[LISTING] = "<html><body>redesigned</body></html>"
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(1))
    assert entries == [] and errors == [f"{LISTING}: no entries parsed"]


def test_robots_disallow_is_respected(web):
    routes, calls, _ = web
    routes[ROBOTS] = "User-agent: *\nDisallow: /changelog/\n"
    entries, errors = read_listing(ListingPage(url=LISTING, page_url=PAGE), since(1))
    assert entries == [] and errors == [f"{LISTING}: disallowed by robots.txt"]
    assert calls == [ROBOTS]


def cfg(feeds: list[dict]) -> CIConfig:
    return CIConfig(competitors=[{"key": "github", "name": "GitHub", "news_queries": ["GitHub"], "feeds": feeds,
                                  "listing_pages": [{"url": LISTING, "page_url": PAGE}]}])


def test_collect_adds_listing_entries_the_feed_missed(web):
    routes, _, _ = web
    routes[FEED] = "github_changelog_feed.xml"
    result = vendor_feeds.collect(cfg([{"url": FEED}]), since(21))
    assert result.errors == []
    by_title = {p.title: p for p in result.packets}
    assert len(by_title) == len(result.packets) == 6  # lockfiles once, though both the feed and listing carry it
    lockfiles = by_title["GitHub Actions workflow lockfiles are generally available"]
    assert lockfiles.origin == FEED  # the feed's copy wins: exact time and its own text
    assert lockfiles.published_at == datetime(2026, 10, 28, 16, 30, tzinfo=UTC)
    ai_scan = by_title["AI Scan for repositories in public preview"]
    assert ai_scan.source == "vendor_feed" and ai_scan.origin == LISTING and ai_scan.competitor == "github"
    assert ai_scan.published_at == datetime(2026, 10, 28, tzinfo=UTC) and ai_scan.publisher == "GitHub"
    assert ai_scan.text == "" and ai_scan.text_status == "snippet" and ai_scan.text_source == "teaser"
    assert ai_scan.url == ai_scan.original_url


def test_collect_keeps_the_feed_when_the_listing_fails(web):
    routes, _, _ = web
    routes[FEED] = "github_changelog_feed.xml"
    routes[LISTING] = 503
    result = vendor_feeds.collect(cfg([{"url": FEED}]), since(21))
    assert [p.origin for p in result.packets] == [FEED]
    assert len(result.errors) == 1 and result.errors[0].startswith(f"{LISTING}: HTTPError: 503")


def test_collect_keeps_the_listing_when_the_feed_fails(web):
    routes, _, _ = web
    routes[FEED] = 500
    result = vendor_feeds.collect(cfg([{"url": FEED}]), since(21))
    assert len(result.packets) == 6 and {p.origin for p in result.packets} == {LISTING}
    assert len(result.errors) == 1 and result.errors[0].startswith(f"{FEED}: HTTPError: 500")


def test_listing_host_counts_as_the_competitors_own_source():
    competitor = cfg([]).competitors[0]
    assert "github.blog" in own_sources(competitor)
