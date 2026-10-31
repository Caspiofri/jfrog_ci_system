"""Why a page's text is or isn't there (fetch_status), recorded per item; offline with fake responses.

A bot check is only recognised and recorded, never answered: such a site needs another source (its RSS feed)."""
import pytest
import requests

from ci.packet import Packet
from ci.pipeline import read_full_text
from modules import reader
from modules.reader import FetchResult

ARTICLE = "<html><body><article>" + "<p>GitHub ships a package firewall for npm. " * 60 + "</p></article></body></html>"
CHALLENGE = "<html><head><title>Just a moment...</title></head><body><div id='challenge-platform'></div></body></html>"


class Resp:
    def __init__(self, status=200, text=ARTICLE, ctype="text/html; charset=utf-8", headers=None, url="https://x/a"):
        self.status_code, self.text, self.url = status, text, url
        self.headers = {"content-type": ctype, **(headers or {})}


@pytest.mark.parametrize(("resp", "status", "http"), [
    (Resp(), "ok", 200),
    (Resp(403, CHALLENGE), "cloudflare_challenge", 403),
    (Resp(403, "<html>forbidden</html>", headers={"cf-mitigated": "challenge"}), "cloudflare_challenge", 403),
    (Resp(403, "<html>Forbidden</html>"), "http_403", 403),
    (Resp(404, "<html>gone</html>"), "http_404", 404),
    (Resp(200, "%PDF-1.4", ctype="application/pdf"), "not_html", 200),
    (Resp(200, "<html><body></body></html>"), "empty", 200),
])
def test_fetch_page_says_why(monkeypatch, resp, status, http):
    monkeypatch.setattr(reader.requests, "get", lambda *a, **k: resp)
    res = reader.fetch_page("https://x/a")
    assert (res.status, res.http_status) == (status, http)
    assert (res.text is not None) == (status == "ok")


@pytest.mark.parametrize(("exc", "status"), [(requests.Timeout(), "timeout"),
                                             (requests.ConnectionError(), "connection_error"),
                                             (ValueError("bad"), "error:ValueError")])
def test_network_failures_say_why(monkeypatch, exc, status):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(reader.requests, "get", boom)
    assert reader.fetch_page("https://x/a").status == status
    assert reader.fetch_text("https://x/a") is None  # the old interface keeps its behaviour


def pkt(**kw):
    base = {"source": "google_news", "origin": "q", "competitor": "github", "title": "GitHub ships a firewall",
            "url": "https://devops.com/a", "original_url": "https://devops.com/a", "text": "teaser text"}
    return Packet(**{**base, **kw})


def test_the_pipeline_records_the_fetch_status_on_the_item():
    blocked = read_full_text(pkt(), lambda url: FetchResult(None, "cloudflare_challenge", 403, url))
    assert (blocked.text_status, blocked.fetch_status, blocked.fetch_http_status) == \
        ("snippet", "cloudflare_challenge", 403)
    page = "GitHub ships a firewall that blocks malicious npm packages before install. " * 30
    ok = read_full_text(pkt(), lambda url: FetchResult(page, "ok", 200, url))
    assert (ok.text_status, ok.fetch_status) == ("full", "ok")
    short = read_full_text(pkt(text="a long teaser " * 20), lambda url: FetchResult("tiny", "ok", 200, url))
    assert (short.text_status, short.fetch_status) == ("snippet", "shorter_than_teaser")


def test_skipped_fetches_and_plain_fetchers_are_recorded_too():
    feed = read_full_text(pkt(text_status="full"), lambda url: pytest.fail("must not fetch"))
    assert feed.fetch_status == "skipped_full_feed"
    gnews = read_full_text(pkt(url="https://news.google.com/rss/articles/x", url_resolved=False),
                           lambda url: pytest.fail("must not fetch"))
    assert gnews.fetch_status == "skipped_unresolved"
    assert read_full_text(pkt(), lambda url: None).fetch_status == "failed"  # a plain str/None fetcher
    assert read_full_text(pkt(), lambda url: "word " * 400).fetch_status == "ok"
