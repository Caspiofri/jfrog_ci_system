"""Hacker News collector: parsing, the title/URL filter and per-query isolation (HTTP patched)."""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import requests

from ci.collectors import hackernews
from ci.config import CIConfig, Competitor

SINCE = datetime(2026, 10, 23, tzinfo=UTC)


def _hit(object_id="1", title="Snyk launches X", url="https://snyk.io/blog/x", story_text=None, ts=1761700000):
    return {"objectID": object_id, "title": title, "url": url, "story_text": story_text,
            "created_at_i": ts, "points": 5, "num_comments": 2}


def _cfg(*competitors):
    return CIConfig(competitors=[Competitor(key=k, name=k, hn_queries=qs) for k, qs in competitors])


@pytest.fixture
def fake_get(monkeypatch):
    """Patch requests.get; `responses` maps query -> list of hits, a list of pages (lists) with an
    (pages, nbHits) tuple, or an exception to raise."""
    responses = {}
    calls = []

    def get(url, params, timeout):
        calls.append(params)
        answer = responses[params["query"]]
        if isinstance(answer, Exception):
            raise answer
        pages, total = answer if isinstance(answer, tuple) else ([answer], len(answer))
        resp = MagicMock()
        resp.json.return_value = {"hits": pages[params["page"]] if params["page"] < len(pages) else [],
                                  "nbHits": total}
        return resp

    monkeypatch.setattr(hackernews.requests, "get", get)
    return responses, calls


def test_packet_fields_for_link_story(fake_get):
    responses, calls = fake_get
    responses["Snyk"] = [_hit()]
    result = hackernews.collect(_cfg(("snyk", ["Snyk"])), SINCE)
    assert result.errors == [] and result.source == "hackernews"
    [p] = result.packets
    assert (p.competitor, p.origin, p.title) == ("snyk", "Snyk", "Snyk launches X")
    assert p.url == "https://snyk.io/blog/x"
    assert p.original_url == "https://news.ycombinator.com/item?id=1"
    assert p.published_at == datetime.fromtimestamp(1761700000, tz=UTC)
    assert p.published_at.tzinfo is not None
    assert (p.text, p.text_status, p.publisher) == ("", "snippet", "Hacker News")
    assert calls[0]["numericFilters"] == f"created_at_i>={int(SINCE.timestamp())},points>={hackernews.MIN_POINTS}"


def test_text_post_uses_item_url_and_plain_text(fake_get):
    responses, _ = fake_get
    responses["GitLab"] = [_hit(object_id="9", title="Ask HN: GitLab or GitHub?", url=None,
                                story_text="<p>Which one &amp; why?</p><p>Thanks</p>")]
    [p] = hackernews.collect(_cfg(("gitlab", ["GitLab"])), SINCE).packets
    assert p.url == p.original_url == "https://news.ycombinator.com/item?id=9"
    assert p.text == "Which one & why? Thanks"


def test_filter_keeps_title_or_url_matches_only(fake_get):
    responses, _ = fake_get
    responses["supply chain attack"] = [
        _hit("1", title="A Supply Chain Attack on X", url="https://a.com/1"),
        _hit("2", title="What happened", url="https://b.com/litellm-supply-chain-attack"),
        _hit("3", title="Attackers run supply chain campaign", url="https://c.com/3"),
        _hit("4", title="", url="https://d.com/supply-chain-attack"),
    ]
    packets = hackernews.collect(_cfg(("industry", ["supply chain attack"])), SINCE).packets
    assert [p.original_url[-1] for p in packets] == ["1", "2"]


def test_failing_query_is_isolated(fake_get):
    responses, _ = fake_get
    responses["Snyk"] = requests.Timeout("timed out")
    responses["Sonatype"] = [_hit(title="Sonatype report")]
    responses["GitLab"] = [{"objectID": "x"}]  # malformed: no created_at_i
    responses["GitLab"][0]["title"] = "GitLab news"
    result = hackernews.collect(_cfg(("snyk", ["Snyk"]), ("sonatype", ["Sonatype"]), ("gitlab", ["GitLab"])), SINCE)
    assert [p.competitor for p in result.packets] == ["sonatype"]
    assert len(result.errors) == 2
    assert "Snyk" in result.errors[0] and "Timeout" in result.errors[0]
    assert "GitLab" in result.errors[1]


def test_no_queries_no_requests(fake_get):
    _, calls = fake_get
    result = hackernews.collect(_cfg(("cloudsmith", [])), SINCE)
    assert result.packets == [] and result.errors == [] and calls == []


def test_bad_hit_is_skipped_and_other_hits_survive(fake_get):
    responses, _ = fake_get
    responses["Snyk"] = [_hit("1", title=["not", "a", "string"]), _hit("2", title="Snyk ships Y")]
    result = hackernews.collect(_cfg(("snyk", ["Snyk"])), SINCE)
    assert [p.title for p in result.packets] == ["Snyk ships Y"]
    assert result.errors == ["hackernews 'Snyk': skipped 1 malformed hits"]


def test_filter_ignores_host_and_needs_whole_words(fake_get):
    responses, _ = fake_get
    responses["GitLab"] = [
        _hit("1", title="Show HN: Android TV root", url="https://gitlab.com/someone/tv-root"),
        _hit("2", title="Gitlabber 2.0 released", url="https://x.com/gitlabber"),
        _hit("3", title="Ruby regexp fixes", url="https://ruby-lang.org/news/regexp-fixes-for_gitlab"),
        _hit("4", title="GitLab 19.0", url="https://about.gitlab.com/releases"),
    ]
    packets = hackernews.collect(_cfg(("gitlab", ["GitLab"])), SINCE).packets
    assert [p.original_url[-1] for p in packets] == ["3", "4"]


def test_second_page_fetched_and_truncation_reported(fake_get):
    responses, calls = fake_get
    responses["Snyk"] = ([[_hit("1")], [_hit("2")]], 5)
    result = hackernews.collect(_cfg(("snyk", ["Snyk"])), SINCE)
    assert [c["page"] for c in calls] == [0, 1]
    assert len(result.packets) == 2
    assert result.errors == ["hackernews 'Snyk': truncated: 2 of 5"]
