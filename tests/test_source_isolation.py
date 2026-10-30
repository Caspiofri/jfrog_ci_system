"""One failing source (its collector, or its shortlist LLM call) is logged and recorded, and the run goes on."""
import asyncio
import importlib
from datetime import date
from unittest.mock import patch

import pytest

from modules import nodes
from modules.models import Article


def _art(name, origin, url=None):
    return Article(subject="s", name=name, published_at=date(2026, 10, 30), content="c",
                   url=url or f"https://{origin}.example/{name}", origin=origin)


def _ok(urls):
    return {u: ("ok", u) for u in urls}


def test_failing_collector_is_recorded_not_raised(capsys):
    def boom(state):
        raise RuntimeError("feed down")
    out = nodes.isolated_collector("vendor", boom)({})
    assert out == {"extra_articles": [],
                   "source_errors": [{"source": "vendor", "stage": "collect", "error": "RuntimeError: feed down"}]}
    assert "source 'vendor' failed" in capsys.readouterr().out


def test_working_collector_passes_its_articles_through():
    arts = [_art("a", "vendor")]
    assert nodes.isolated_collector("vendor", lambda state: arts)({}) == {"extra_articles": arts}


def test_hackernews_node_survives_an_unexpected_error():
    with patch.object(nodes.hackernews, "collect", side_effect=TypeError("bad hit")):
        out = nodes.collect_hackernews({"hn_queries": ["Snyk"], "subject": "s"})
    assert out["extra_articles"] == []
    assert out["source_errors"][0]["source"] == "hackernews"


def test_merge_goes_on_with_the_sources_that_worked_and_counts_the_failed():
    state = {"articles": [], "extra_articles": [_art("a", "vendor"), _art("b", "vendor")],
             "source_errors": [{"source": "hackernews", "stage": "collect", "error": "x"}]}
    with patch.object(nodes.link_utils, "resolve_links", side_effect=_ok), \
            patch.object(nodes.article_store, "upgrade_bad_links", side_effect=lambda a: a):
        out = nodes.merge_sources(state)
    assert [a.name for a in out["articles"]] == ["a", "b"]
    assert out["run_stats"] == {"merged": 2, "collect_failures": 1}


def test_merge_counts_no_failures_on_a_clean_run():
    state = {"articles": [], "extra_articles": [_art("a", "vendor")], "source_errors": []}
    with patch.object(nodes.link_utils, "resolve_links", side_effect=_ok), \
            patch.object(nodes.article_store, "upgrade_bad_links", side_effect=lambda a: a):
        assert nodes.merge_sources(state)["run_stats"]["collect_failures"] == 0


def _fake_gemini(prompt, config=None):
    if "bad-llm" in prompt:
        raise RuntimeError("503 overloaded")
    if "bad-reply" in prompt:
        return "sorry, I cannot help with that"  # no JSON array: fillter_articles raises ValueError
    return "[0]"


def test_shortlist_skips_a_source_whose_llm_call_fails():
    arts = [_art("bad-llm", "hackernews"), _art("good", "vendor"), _art("bad-reply", "github")]
    state = {"articles": arts, "subject": "s", "run_stats": {"merged": 3}}
    with patch.object(nodes, "_call_gemini", side_effect=_fake_gemini):
        out = nodes.shortlist_articles(state)
    assert [a.name for a in out["candidates"]] == ["good"]
    assert sorted((e["source"], e["stage"]) for e in out["source_errors"]) == [
        ("github", "shortlist"), ("hackernews", "shortlist")]
    assert "RuntimeError: 503 overloaded" in {e["error"] for e in out["source_errors"]}
    assert out["run_stats"] == {"merged": 3, "shortlisted": 1, "shortlist_failures": 2}


def test_shortlist_without_failures_records_zero():
    state = {"articles": [_art("good", "vendor")], "subject": "s", "run_stats": {}}
    with patch.object(nodes, "_call_gemini", side_effect=_fake_gemini):
        out = nodes.shortlist_articles(state)
    assert out["source_errors"] == [] and out["run_stats"]["shortlist_failures"] == 0


def test_graph_finishes_and_records_the_failure_when_a_collector_breaks():
    with patch.object(nodes.hackernews, "collect", side_effect=RuntimeError("algolia down")), \
            patch.object(nodes.link_utils, "resolve_links", side_effect=_ok):
        from modules import graph as graph_mod
        graph_mod = importlib.reload(graph_mod)
        state = {"subject": "s", "digest_name": "d", "hn_queries": ["Snyk"], "articles": [], "extra_articles": [],
                 "top_articles": [], "candidates": [], "source_errors": []}
        out = asyncio.run(graph_mod.graph.ainvoke(state, config={"configurable": {"thread_id": "t"}}))
    assert out["email_status"] == "no_content"
    assert out["source_errors"] == [{"source": "hackernews", "stage": "collect", "error": "RuntimeError: algolia down"}]
    assert out["run_stats"]["collect_failures"] == 1
    assert nodes.every_source_failed(out)  # main.py reports this run as failed


def test_missing_credentials_fail_the_shortlist_instead_of_skipping_a_source():
    missing = nodes.llm_clients.MissingCredentials("GOOGLE_API_KEY is not set")
    with patch.object(nodes, "_call_gemini", side_effect=missing), \
            pytest.raises(nodes.llm_clients.MissingCredentials):
        nodes.shortlist_articles({"articles": [_art("good", "vendor")], "subject": "s", "run_stats": {}})


def test_missing_credentials_are_not_retried():
    calls = []

    def no_key():
        calls.append(1)
        raise nodes.llm_clients.MissingCredentials("GOOGLE_API_KEY is not set")
    with patch.object(nodes.llm_clients, "gemini_client", side_effect=no_key), \
            pytest.raises(nodes.llm_clients.MissingCredentials):
        nodes._call_gemini("p")
    assert calls == [1]


def test_missing_credentials_in_a_collector_fail_the_run():
    def no_key(state):
        raise nodes.llm_clients.MissingCredentials("x")
    with pytest.raises(nodes.llm_clients.MissingCredentials):
        nodes.isolated_collector("vendor", no_key)({})


def _err(source, stage):
    return {"source": source, "stage": stage, "error": "x"}


def test_every_source_failed_at_collect():
    assert nodes.every_source_failed({"source_errors": [_err(s, "collect") for s in nodes.COLLECTOR_SOURCES]})


def test_every_source_failed_at_shortlist():
    arts = [_art("a", "hackernews"), _art("b", "vendor")]
    errors = [_err("hackernews", "shortlist"), _err("vendor", "shortlist")]
    assert nodes.every_source_failed({"articles": arts, "source_errors": errors})


def test_one_working_source_is_not_a_failed_run():
    arts = [_art("a", "hackernews"), _art("b", "vendor")]
    assert not nodes.every_source_failed({"articles": arts, "source_errors": [_err("vendor", "shortlist")]})
    assert not nodes.every_source_failed({"articles": [], "source_errors": []})  # an empty day is not a failure
