"""Complete feed bodies (Atom content / RSS content:encoded / release notes) are kept and the page is not fetched."""
from datetime import UTC, datetime

import feedparser
import pytest

from ci import pipeline
from ci.collectors import github_releases, vendor_feeds
from ci.config import Competitor, Feed
from ci.packet import FEED_FULL_MIN_CHARS, Packet

SINCE = datetime(2026, 10, 1, tzinfo=UTC)
ACME = Competitor(key="acme", name="Acme")
LONG = "Acme now installs npm packages faster by caching metadata. " * 20  # well past the threshold
assert len(LONG) > FEED_FULL_MIN_CHARS


def _rss(summary: str, content: str | None):
    encoded = f"<content:encoded><![CDATA[<p>{content}</p>]]></content:encoded>" if content is not None else ""
    xml = f"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
    <channel><title>Acme changelog</title><item><title>npm installs are now faster</title>
    <link>https://acme.example/changelog/npm</link><pubDate>Wed, 28 Oct 2026 10:00:00 +0000</pubDate>
    <description>{summary}</description>{encoded}</item></channel></rss>"""
    return feedparser.parse(xml)


def test_rss_content_encoded_long_enough_is_kept_as_the_full_item():
    [p] = vendor_feeds.parse(_rss("Short teaser", LONG), ACME, Feed(url="https://acme.example/rss"), SINCE)
    assert (p.text_status, p.text_source) == ("full", "feed") and p.text.startswith("Acme now installs")
    assert p.text == " ".join(LONG.split())  # the whole body, not cut to a teaser


def test_short_content_or_summary_only_stays_a_teaser():
    [short] = vendor_feeds.parse(_rss("Short teaser", "Tiny body."), ACME, Feed(url="https://a/rss"), SINCE)
    [summary] = vendor_feeds.parse(_rss(LONG, None), ACME, Feed(url="https://a/rss"), SINCE)
    assert (short.text_status, short.text_source) == ("snippet", "teaser")
    assert (summary.text_status, summary.text_source) == ("snippet", "teaser")  # a summary is never "complete"


def test_long_release_notes_are_complete():
    atom = feedparser.parse(f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>v1.30.1</title><link href="https://github.com/acme/cli/releases/tag/v1.30.1"/>
    <updated>2026-10-28T10:00:00Z</updated><content type="html">&lt;p&gt;{LONG}&lt;/p&gt;</content></entry></feed>""")
    [p] = github_releases.parse(atom, ACME, "acme/cli", SINCE)
    assert (p.text_status, p.text_source) == ("full", "feed")


def test_pipeline_skips_the_fetch_for_a_complete_feed_item_and_marks_fetched_pages():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return "page text " * 300

    feed_item = Packet(source="vendor_feed", origin="o", competitor="acme", title="t", url="https://a/1",
                       original_url="https://a/1", text=LONG, text_status="full", text_source="feed")
    teaser = feed_item.model_copy(update={"url": "https://a/2", "text": "teaser", "text_status": "snippet",
                                          "text_source": "teaser"})
    kept = pipeline.read_full_text(feed_item, fetch)
    page = pipeline.read_full_text(teaser, fetch)
    assert fetched == ["https://a/2"]
    assert kept.text_source == "feed" and kept.text == LONG[:pipeline.TEXT_MAX_CHARS]
    assert page.text_source == "page" and page.text_status == "full"


def test_old_packets_default_to_teaser():
    p = Packet.model_validate({"source": "hackernews", "origin": "q", "competitor": "acme", "title": "t",
                               "url": "https://a", "original_url": "https://a"})
    assert p.text_source == "teaser"


@pytest.mark.parametrize("ending", [" Read more", " Continue reading →", " [&#8230;]", " [...]",
                                    " Read the full article", " READ MORE »"])
def test_a_long_body_that_ends_like_a_teaser_is_not_complete(ending):
    [p] = vendor_feeds.parse(_rss("Short", LONG + ending), ACME, Feed(url="https://a/rss"), SINCE)
    assert (p.text_status, p.text_source) == ("snippet", "teaser")


@pytest.mark.parametrize("ending", ["…", "..."])
def test_a_short_body_ending_on_an_ellipsis_is_a_teaser(ending):
    short = LONG[:600]  # over FEED_FULL_MIN_CHARS, under twice it
    [p] = vendor_feeds.parse(_rss("Short", short + ending), ACME, Feed(url="https://a/rss"), SINCE)
    assert (p.text_status, p.text_source) == ("snippet", "teaser")


def test_a_complete_body_ending_normally_stays_complete():
    [p] = vendor_feeds.parse(_rss("Short", LONG + " Upgrade today."), ACME, Feed(url="https://a/rss"), SINCE)
    assert p.text_source == "feed"


@pytest.mark.parametrize("ending,truncated", [
    ("…", False), ("...", False),  # a bare ellipsis on a long body is just how it ends
    (" Read more", True), (" Continue reading →", True), (" [&#8230;]", True), (" [...]", True),
])
def test_on_a_long_body_only_explicit_markers_mean_teaser(ending, truncated):
    from ci.collectors.feedutil import ELLIPSIS_MAX_CHARS

    long_body = LONG * 2
    assert len(" ".join(long_body.split())) >= ELLIPSIS_MAX_CHARS
    [p] = vendor_feeds.parse(_rss("Short", long_body + ending), ACME, Feed(url="https://a/rss"), SINCE)
    assert (p.text_source == "teaser") is truncated
