"""GitHub releases collector: releases.atom parsing, title format, window, and per-repo failure isolation (offline)."""
from datetime import UTC, datetime

import requests

from ci.collectors import feedutil, github_releases
from ci.config import CIConfig
from tests.ci.test_vendor_feeds import SINCE, fake_get


def cfg(repos: list[str]) -> CIConfig:
    return CIConfig(competitors=[{"key": "acme", "name": "Acme", "news_queries": ["Acme"], "github_repos": repos}])


def test_releases_become_packets(monkeypatch):
    routes = {"https://github.com/acme/acme-cli/releases.atom": "releases.atom"}
    monkeypatch.setattr(feedutil.requests, "get", fake_get(routes))
    result = github_releases.collect(cfg(["acme/acme-cli"]), SINCE)
    assert result.source == "github_releases" and result.errors == []
    [p] = result.packets  # v1.0.0 is outside the window
    assert p.title == "acme-cli Release v1.30.1"
    assert p.source == "github_releases" and p.origin == "acme/acme-cli" and p.competitor == "acme"
    assert p.url == p.original_url == "https://github.com/acme/acme-cli/releases/tag/v1.30.1"
    assert p.published_at == datetime(2026, 10, 28, 13, 13, 42, tzinfo=UTC)
    assert p.text == "Fixes Fix push retries" and p.publisher == "Acme"


def test_failing_repo_is_isolated(monkeypatch):
    routes = {"https://github.com/acme/acme-cli/releases.atom": "releases.atom",
              "https://github.com/acme/gone/releases.atom": 404}
    monkeypatch.setattr(feedutil.requests, "get", fake_get(routes))
    result = github_releases.collect(cfg(["acme/gone", "acme/acme-cli"]), SINCE)
    assert [p.title for p in result.packets] == ["acme-cli Release v1.30.1"]
    assert len(result.errors) == 1 and result.errors[0].startswith("acme/gone: HTTPError")


def test_connection_error_is_recorded(monkeypatch):
    def get(url, headers=None, timeout=None):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(feedutil.requests, "get", get)
    result = github_releases.collect(cfg(["acme/acme-cli"]), SINCE)
    assert result.packets == [] and result.errors == ["acme/acme-cli: ConnectionError: no network"]
