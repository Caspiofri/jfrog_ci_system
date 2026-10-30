"""Coverage check, offline: a fixture event list against fixture run files with known answers."""
import json
from datetime import date

import pytest

from ci import coverage
from ci.coverage import EVENTS_PATH, keyword_re, load_events, match_item, run

RUN_ID = "20261030T0800Z-abc123"

EVENTS_YAML = """
events:
  - id: url-event
    competitor: cloudsmith
    date: 2026-10-26
    title: Verify npm provenance through your Cloudsmith registry
    official_url: https://cloudsmith.com/changelog/verify-npm-provenance
    category: Security
    expected_importance: 3
    match:
      urls: [https://cloudsmith.com/blog/npm-provenance-launch]
      title_keywords: []
  - id: keyword-event
    competitor: gitlab
    date: 2026-10-29
    title: "GitLab Orbit is GA"
    official_url: https://about.gitlab.com/blog/gitlab-orbit-ga/
    category: AI & Agents
    expected_importance: 4
    match:
      urls: []
      title_keywords:
        - [GitLab Orbit]
  - id: dropped-event
    competitor: github
    date: 2026-10-28
    title: Prioritize Dependabot alerts with reachability analysis
    official_url: https://github.blog/changelog/dependabot-reachability
    category: Security
    expected_importance: 4
    match:
      urls: []
      title_keywords:
        - [Dependabot, reachability]
  - id: missed-event
    competitor: github
    date: 2026-10-28
    title: GitHub Actions workflow lockfiles are generally available
    official_url: https://github.blog/changelog/workflow-lockfiles
    category: Security
    expected_importance: 4
    match:
      urls: []
      title_keywords:
        - [workflow lockfiles]
  - id: strict-event
    competitor: industry
    date: 2026-10-29
    title: CISA adds GitLab CVE to KEV
    official_url: https://www.cisa.gov/alerts/2026/10/29/kev
    category: Security
    expected_importance: 3
    match:
      urls: []
      title_keywords:
        - [CISA, GitLab, exploit*]
  - id: old-event
    competitor: industry
    date: 2026-10-20
    title: LiteLLM release compromised
    official_url: https://docs.litellm.ai/blog/incident
    category: Security
    expected_importance: 4
    match:
      urls: []
      title_keywords:
        - [LiteLLM, compromise*]
"""


def _item(title, url, text="", original_url=None, **extra):
    return {"id": url[-8:], "title": title, "url": url, "original_url": original_url or url, "text": text,
            "competitor": "x", **extra}


KEPT = [
    # url-event: the alternate URL, with tracking params and a trailing slash that normalization removes
    _item("Cloudsmith ships provenance", "https://CLOUDSMITH.com/blog/npm-provenance-launch/?utm_source=rss"),
    # keyword-event: press coverage, different URL, the title names the event
    _item("GitLab launches Orbit context graph -- GitLab Orbit now GA", "https://news.example.com/orbit"),
    # strict-event must NOT match this: CISA and GitLab both appear, but the title is not about exploitation, and
    # "exploit" sits only in the text
    _item("CISA guidance for GitLab administrators", "https://news.example.com/cisa-gitlab",
          text="Attackers exploited other products this week."),
    # missed-event must NOT match this: the keywords are spread over title and text
    _item("New workflow features in GitHub", "https://news.example.com/workflows", text="lockfiles arrive"),
    # old-event: matched, but the event is outside the window
    _item("LiteLLM supply chain: release compromised on PyPI", "https://news.example.com/litellm"),
]
DROPPED = [
    {**_item("Dependabot gets reachability analysis", "https://news.example.com/dependabot"),
     "drop_stage": "embedding_dedupe", "duplicate_of": "abc"},
]


@pytest.fixture
def fixture_run(tmp_path):
    events = tmp_path / "events.yaml"
    events.write_text(EVENTS_YAML, encoding="utf-8")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN_ID}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in KEPT), encoding="utf-8")
    (runs / f"{RUN_ID}.dropped.jsonl").write_text("".join(json.dumps(r) + "\n" for r in DROPPED), encoding="utf-8")
    (runs / f"{RUN_ID}.report.json").write_text(json.dumps({"started_at": "2026-10-30T08:00:00+00:00",
                                                            "window_days": 7}), encoding="utf-8")
    out = tmp_path / "out"
    return run(RUN_ID, runs, events, out), out


def _event(report, eid):
    return next(e for e in report["events"] if e["id"] == eid)


def test_url_match_after_normalization(fixture_run):
    ev = _event(fixture_run[0], "url-event")
    assert ev["captured"] and ev["kept"]
    assert [m["reason"] for m in ev["matches"]] == ["url"]


def test_keyword_match_on_title(fixture_run):
    ev = _event(fixture_run[0], "keyword-event")
    assert ev["captured"]
    assert ev["matches"][0]["reason"] == "keywords: GitLab Orbit"


def test_dropped_only_capture(fixture_run):
    report = fixture_run[0]
    ev = _event(report, "dropped-event")
    assert ev["captured"] and not ev["kept"] and ev["dropped_only"]
    assert report["dropped_only"] == [{"id": "dropped-event", "title": ev["title"]}]
    assert report["overall"]["captured_dropped_only"] == 1


def test_keyword_group_does_not_match_unrelated_items(fixture_run):
    report = fixture_run[0]
    assert not _event(report, "strict-event")["captured"]
    assert not _event(report, "missed-event")["captured"]
    assert {m["id"] for m in report["missed"]} == {"strict-event", "missed-event"}


def test_out_of_window_event_excluded_from_recall(fixture_run):
    report = fixture_run[0]
    assert report["window"] == {"first": "2026-10-23", "last": "2026-10-30"}
    assert report["out_of_window"] == [{"id": "old-event", "date": "2026-10-20", "title": "LiteLLM release compromised",
                                        "competitor": "industry", "expected_importance": 4, "captured": True}]
    o = report["overall"]
    assert (o["events"], o["captured"], o["recall"]) == (5, 3, 0.6)
    # importance >= 4 in the window: keyword, dropped, missed; old-event does not count
    assert (report["high_importance"]["events"], report["high_importance"]["captured"]) == (3, 2)
    assert report["by_competitor"]["github"] == {"events": 2, "captured": 1, "recall": 0.5}
    assert "industry" in report["by_competitor"] and report["by_competitor"]["industry"]["events"] == 1


def test_writes_report_and_formats(fixture_run):
    report, out = fixture_run
    saved = json.loads((out / f"{RUN_ID}.json").read_text(encoding="utf-8"))
    assert saved["overall"] == report["overall"]
    table = coverage.format_report(report)
    assert "recall   60%  3/5 events" in table
    assert "[4] missed-event" in table and "2026-10-20 [4] old-event: matched" in table


def test_keyword_semantics():
    assert keyword_re("exploit*").search("Actively Exploited flaw")
    assert not keyword_re("exploit").search("Actively Exploited flaw")
    assert not keyword_re("19.5.1").search("GitLab 19.5.10 released")
    assert keyword_re("npm  firewall").search("GitHub's NPM\nFirewall")
    assert match_item(load_events(EVENTS_PATH)[0], {"title": "", "url": "https://example.com"}) is None


def test_window_from_run_id_without_report(tmp_path):
    assert coverage.run_window(RUN_ID, tmp_path) == (date(2026, 10, 23), date(2026, 10, 30), 7)


def test_real_event_list_is_valid():
    events = load_events(EVENTS_PATH)
    assert 15 <= len(events) <= 30
    assert all(e.keyword_groups or e.urls for e in events)


def test_rejects_unknown_category(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(EVENTS_YAML.replace("category: Security", "category: Security News", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="D11"):
        load_events(bad)
