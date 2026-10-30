"""Reader extraction: the article's own text, without 'Other logs' carousels, asides or related posts."""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import trafilatura

from modules import reader

PAGE = (Path(__file__).parent / "fixtures" / "cloudsmith_changelog.html").read_text(encoding="utf-8")
MAIN = ["pnpm clients now make 40% fewer metadata requests", "Cloudsmith indexes npm metadata"]
NEIGHBOURS = ["usage limits", "OpenID Connect", "Other logs", "Mumbai"]


def test_the_fixture_reproduces_the_bug_with_plain_extraction():
    old = trafilatura.extract(PAGE, include_comments=False, include_tables=False)
    assert "usage limits" in old.lower()  # the carousel leaks in without the new extraction


def test_only_the_main_entry_is_extracted():
    text = reader.extract_main_text(PAGE)
    for line in MAIN:
        assert line in text
    for neighbour in NEIGHBOURS:
        assert neighbour.lower() not in text.lower(), neighbour


ARTICLE = " ".join(
    f"Paragraph {i}: GitLab shipped a fix for the critical remote code execution flaw in its Ruby-based importer, "
    "and administrators of self-managed instances should upgrade to the patched release as soon as possible."
    for i in range(8))


def _page(article_html: str, extra: str = "") -> str:
    return (f"<html><head><title>GitLab patches RCE</title></head><body><header><nav>Home News</nav></header>"
            f"<main>{article_html}{extra}</main><footer>Copyright</footer></body></html>")


def _body() -> str:
    return f"<h1>GitLab patches critical RCE</h1><p>{ARTICLE}</p>"


@pytest.mark.parametrize("html", [
    _page(f'<div class="post-related-content-wrapper"><article>{_body()}</article></div>'),
    _page(f'<article class="post has-carousel">{_body()}</article>'),
    _page(f'<div class="uncorrelated-layout"><article>{_body()}</article></div>'),
    _page(f'<article aria-label="Related to CVE-2026-1234">{_body()}</article>'),
    _page(f'<div class="related-wrapper"><h1>GitLab patches critical RCE</h1><div><p>{ARTICLE}</p></div></div>'),
], ids=["wrapper-class", "article-has-carousel", "uncorrelated", "aria-label", "holds-the-h1"])
def test_the_article_survives_misleading_markup(html):
    text = reader.extract_main_text(html)
    assert text and "Paragraph 7" in text and len(text) > 0.9 * len(ARTICLE)


def test_related_blocks_and_outside_asides_go_in_article_callouts_stay():
    callout = '<aside class="note"><p>Note: self-managed GitLab 17.x is affected only with the importer on.</p></aside>'
    extra = ('<aside><p>Sidebar teaser: Snyk raises a Series H round.</p></aside>'
             '<div id="related-posts"><p>Related teaser: Sonatype launches Nexus Pro.</p></div>'
             '<ul class="more-stories"><li>More teaser: Cloudsmith adds OIDC.</li></ul>'
             '<section class="you-might-like"><p>Maybe teaser: JFrog Xray update.</p></section>')
    html = (f"<html><body><main><article>{_body()}{callout}</article></main>{extra}<footer>c</footer></body></html>")
    stripped = reader.strip_related(html)
    assert "self-managed GitLab 17.x" in stripped  # the in-article callout stays
    assert "teaser" not in stripped
    text = reader.extract_main_text(html)
    assert "Paragraph 7" in text and "teaser" not in text


def test_safety_net_falls_back_to_plain_when_stripping_loses_unexplained_text(monkeypatch, caplog):
    html = _page(f"<article>{_body()}</article>")
    monkeypatch.setattr(reader, "_strip", lambda h, plain="": ("<html><body><p>tiny</p></body></html>", 10))
    with caplog.at_level("WARNING"):
        text = reader.extract_main_text(html)
    assert "Paragraph 7" in text and "using plain extraction" in caplog.text


def test_precision_mode_stays_off_on_a_real_page():
    """favor_precision drops this short story outright; with it off the story is kept."""
    html = _page(f"<div><p>{ARTICLE[:600]}</p></div>")
    plain = reader.extract_main_text(html)
    assert reader.FAVOR_PRECISION is False and plain and "Paragraph 0" in plain


def test_fetch_text_uses_the_shared_extraction():
    url = "https://cloudsmith.com/changelog/npm-installs-are-now-faster-with-fewer-requests-and-lookups"
    resp = MagicMock(status_code=200, url=url, text=PAGE)
    resp.headers = {"content-type": "text/html; charset=utf-8"}
    with patch("modules.reader.requests.get", return_value=resp):
        text = reader.fetch_text(url)
    assert MAIN[0] in text and "usage limits" not in text.lower()


PARA = ("The vulnerability CVE-2026-1234 in libfoo allows remote code execution via crafted headers. "
        "Maintainers released version 2.3.4 with a fix and recommend upgrading immediately. ")
BODY = "".join(f"<p>Paragraph {i}. {PARA}</p>" for i in range(12))
CARDS = ('<div class="related-posts"><h3>Related posts</h3><ul><li><a href="/a">Other post A about Kubernetes</a></li>'
         '<li><a href="/b">Other post B about Docker images</a></li></ul></div>')
COMMENTS = '<section class="comments">' + "".join(
    f"<p>Comment {i}: great article thanks a lot for sharing this with the community, very useful!</p>"
    for i in range(40)) + "</section>"


def _chrome(inner: str) -> str:
    return (f"<html><head><title>T</title></head><body><header><nav><a href='/'>Home</a></nav></header>{inner}"
            "<footer><p>Copyright 2026 Example Corp.</p></footer></body></html>")


def test_a_related_wrapper_that_is_the_article_survives_heavy_chrome():
    """The wrapper holds under half the page (comments), has no h1: it used to go, 2263 -> 9 chars."""
    html = _chrome(f'<div class="post-related-content-wrapper"><div class="entry"><h2>Title</h2>{BODY}</div>{CARDS}'
                   f"</div>{COMMENTS}")
    text = reader.extract_main_text(html)
    assert text.count("Paragraph") == 12 and "Other post A" not in text


def test_a_prose_carousel_never_costs_a_paragraph_of_the_plain_extraction():
    cut = len(BODY) * 55 // 100
    cut = BODY.rfind("<p>", 0, cut)
    html = _chrome(f'<div class="content"><h1>T</h1>{BODY[:cut]}</div><div class="carousel">{BODY[cut:]}</div>')
    plain = trafilatura.extract(html, include_comments=False, include_tables=False)
    text = reader.extract_main_text(html)
    # stripping never costs a paragraph the plain extraction had (trafilatura alone already skips this carousel)
    assert set(re.findall(r"Paragraph \d+", plain)) <= set(re.findall(r"Paragraph \d+", text))


def test_a_link_card_listing_goes_even_when_it_is_most_of_a_leaky_extraction():
    text = reader.extract_main_text(PAGE)  # the Cloudsmith carousel: ~59% of the plain extraction
    assert len(text) == 885 and "usage limits" not in text.lower()
