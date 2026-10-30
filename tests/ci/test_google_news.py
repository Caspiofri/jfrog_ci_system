"""Google News collector, offline: fixture RSS and a fake decoder."""
from datetime import UTC, datetime
from pathlib import Path

import feedparser

from ci.collectors import google_news
from ci.config import CIConfig, Competitor

FIXTURE = (Path(__file__).parent / "fixtures" / "google_news_snyk.xml").read_bytes()
SINCE = datetime(2026, 10, 23, tzinfo=UTC)


def _cfg(*queries: str) -> CIConfig:
    return CIConfig(window_days=7, competitors=[Competitor(key="snyk", name="Snyk", news_queries=list(queries))])


def _fetch(url: str):
    if "broken" in url:
        raise ConnectionError("boom")
    return feedparser.parse(FIXTURE)


def _decoder(link: str):
    return {"https://news.google.com/rss/articles/AAA?oc=5": "https://snyk.io/blog/php-rce/"}.get(link)


def test_search_url_encodes_query_and_window():
    url = google_news.search_url('"Snyk"', 7)
    assert url.startswith("https://news.google.com/rss/search?q=%22Snyk%22+when%3A7d&")
    assert url.endswith("hl=en-US&gl=US&ceid=US:en")


def test_collect_builds_packets_and_drops_old_entries():
    res = google_news.collect(_cfg('"Snyk"'), SINCE, decoder=_decoder, fetch=_fetch)
    assert res.source == "google_news"
    assert [p.title for p in res.packets] == [
        "PHP fixes two critical unauthenticated RCE flaws",
        "Snyk - Acme - partners with Snyk",
    ]
    p = res.packets[0]
    assert (p.competitor, p.origin, p.publisher) == ("snyk", '"Snyk"', "Snyk")
    assert p.published_at == datetime(2026, 10, 26, 7, tzinfo=UTC)
    assert p.text == ""  # the summary only echoed the title and the publisher
    assert p.text_status == "snippet"
    assert (p.url, p.url_resolved) == ("https://snyk.io/blog/php-rce/", True)
    assert p.original_url == "https://news.google.com/rss/articles/AAA?oc=5"


def test_undecodable_url_is_kept_unresolved():
    p = google_news.collect(_cfg('"Snyk"'), SINCE, decoder=_decoder, fetch=_fetch).packets[1]
    assert p.url == p.original_url == "https://news.google.com/rss/articles/BBB?oc=5"
    assert not p.url_resolved


def test_decoder_exception_does_not_stop_the_run():
    def explode(link):
        raise RuntimeError("throttled")

    res = google_news.collect(_cfg('"Snyk"'), SINCE, decoder=explode, fetch=_fetch)
    assert len(res.packets) == 2 and not any(p.url_resolved for p in res.packets)


def test_failed_query_is_recorded_and_others_continue():
    res = google_news.collect(_cfg("broken", '"Snyk"'), SINCE, decoder=_decoder, fetch=_fetch)
    assert len(res.packets) == 2
    assert "broken" in res.errors[0] and "boom" in res.errors[0]


def test_decode_url_handles_library_failure(monkeypatch):
    monkeypatch.setattr(google_news, "DECODE_DELAY", 0)
    monkeypatch.setattr(google_news, "gnewsdecoder", lambda link, timeout: {"success": False, "message": "x"})
    assert google_news.decode_url("https://news.google.com/rss/articles/X") is None
    monkeypatch.setattr(google_news, "gnewsdecoder", lambda link, timeout: {"success": True, "decoded_url": "https://a.com"})
    assert google_news.decode_url("https://news.google.com/rss/articles/X") == "https://a.com"


def test_entry_without_link_is_skipped_and_recorded():
    res = google_news.collect(_cfg('"Snyk"'), SINCE, decoder=_decoder, fetch=_fetch)
    assert len(res.packets) == 2 and "Nowhere" not in {p.publisher for p in res.packets}
    assert len(res.errors) == 1 and "entry" in res.errors[0]


def test_naive_since_is_treated_as_utc():
    res = google_news.collect(_cfg('"Snyk"'), SINCE.replace(tzinfo=None), decoder=_decoder, fetch=_fetch)
    assert len(res.packets) == 2


def test_teaser_drops_the_echoed_title_and_publisher_but_keeps_other_text():
    html = ('<a href="https://news.google.com/a">PHP fixes two critical RCE flaws</a>&nbsp;&nbsp;'
            '<font color="#6f6f6f">The Hacker News</font> <p>Patch now: two bugs in php-cgi.</p>'
            '<ol><li><a href="https://news.google.com/b">Related: Snyk explains the bug</a></li></ol>')
    text = google_news._teaser(html, {"PHP fixes two critical RCE flaws"}, "The Hacker News")
    assert text == "Patch now: two bugs in php-cgi. Related: Snyk explains the bug"


def test_snippet_mentions_no_longer_count_the_title_twice():
    from ci.classify import MentionCounter
    from ci.config import CIConfig

    cfg = CIConfig(competitors=[{"key": "snyk", "name": "Snyk"}])
    res = google_news.collect(_cfg('"Snyk"'), SINCE, decoder=_decoder, fetch=_fetch)
    partner = res.packets[1]  # its summary is only its own link, worded differently from the title
    assert partner.text == ""
    counts, _ = MentionCounter(cfg)(partner.text)
    assert counts["snyk"] == 0  # the classifier counts the title itself, once, with TITLE_WEIGHT
