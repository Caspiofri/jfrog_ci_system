"""Held-out coverage over several runs, offline: fixture events against fixture run files with known answers."""
import json

import pytest

from ci import coverage_heldout as ch
from ci.health_summary import coverage_summary

RUNS = ("20261031T1345Z-aaaaaa", "20261101T0400Z-bbbbbb")

EVENTS_YAML = """
events:
  - id: only-in-first
    competitor: gitlab
    date: 2026-10-31
    title: GitLab Orbit is GA
    official_url: https://about.gitlab.com/blog/gitlab-orbit-ga/
    category: AI & Agents
    expected_importance: 4
    match: {urls: [], title_keywords: [[GitLab Orbit]]}
  - id: only-in-second
    competitor: github
    date: 2026-11-02
    title: Dependabot reachability
    official_url: https://github.blog/changelog/dependabot-reachability
    category: Security
    expected_importance: 3
    match: {urls: [], title_keywords: [[Dependabot, reachability]]}
  - id: kept-then-dropped
    competitor: cloudsmith
    date: 2026-11-01
    title: Cloudsmith npm provenance
    official_url: https://cloudsmith.com/changelog/npm-provenance
    category: Security
    expected_importance: 3
    match: {urls: [], title_keywords: []}
  - id: missed
    competitor: github
    date: 2026-11-01
    title: Workflow lockfiles GA
    official_url: https://github.blog/changelog/workflow-lockfiles
    category: Security
    expected_importance: 5
    match: {urls: [], title_keywords: [[workflow lockfiles]]}
  - id: outside-period
    competitor: gitlab
    date: 2026-10-29
    title: GitLab Orbit preview
    official_url: https://about.gitlab.com/blog/gitlab-orbit-preview/
    category: AI & Agents
    expected_importance: 3
    match: {urls: [], title_keywords: [[GitLab Orbit]]}
"""


def item(i, title, url="https://example.com/x", competitor="gitlab"):
    return {"id": i, "title": title, "url": url, "competitor": competitor}


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(ch, "RUNS", RUNS)
    runs = tmp_path / "runs"
    runs.mkdir()
    a, b = RUNS
    write(runs / f"{a}.jsonl", [item("i1", "GitLab Orbit is GA today"),
                                item("i3", "npm provenance", "https://cloudsmith.com/changelog/npm-provenance")])
    write(runs / f"{a}.dropped.jsonl", [])
    write(runs / f"{b}.jsonl", [item("i2", "Dependabot adds reachability", competitor="github")])
    write(runs / f"{b}.dropped.jsonl", [item("i3", "npm provenance", "https://cloudsmith.com/changelog/npm-provenance")])
    events = tmp_path / "heldout.yaml"
    events.write_text(EVENTS_YAML, encoding="utf-8")
    return events, runs, tmp_path / "out"


def test_an_event_is_captured_when_any_run_matched_it(files):
    events, runs, out = files
    report, path = ch.run(events, runs, out)
    rows = {r["id"]: r for r in report["events"]}
    assert rows["only-in-first"]["captured_by_runs"] == [RUNS[0]]
    assert rows["only-in-second"]["captured_by_runs"] == [RUNS[1]]
    assert rows["kept-then-dropped"]["captured_by_runs"] == list(RUNS)
    assert rows["kept-then-dropped"]["kept"] and not rows["kept-then-dropped"]["dropped_only"]
    assert not rows["missed"]["captured"]
    assert report["overall"] == {"events": 4, "captured": 3, "recall": 0.75, "captured_in_kept": 3,
                                 "captured_dropped_only": 0}
    assert report["high_importance"]["events"] == 2 and report["high_importance"]["captured"] == 1
    assert [m["id"] for m in report["missed"]] == ["missed"]
    assert [m["id"] for m in report["out_of_window"]] == ["outside-period"]
    assert report["window"] == {"first": "2026-10-31", "last": "2026-11-02"} and report["window_days"] == 3
    assert report["runs"] == list(RUNS) and report["items_per_run"][RUNS[1]] == {"kept": 1, "dropped": 1}
    assert report["events_file"] == "heldout.yaml" and str(out) not in json.dumps(report)
    assert json.loads(path.read_text(encoding="utf-8"))["overall"]["captured"] == 3


def test_measured_once_never_overwritten(files):
    events, runs, out = files
    _, path = ch.run(events, runs, out)
    before = path.read_bytes()
    with pytest.raises(ch.AlreadyMeasured):
        ch.run(events, runs, out)
    assert path.read_bytes() == before
    assert ch.main(["--events", str(events), "--runs-dir", str(runs), "--out-dir", str(out)]) == 1


def test_missing_events_file_or_run_refuses_and_writes_nothing(files, tmp_path):
    events, runs, out = files
    with pytest.raises(FileNotFoundError):
        ch.run(tmp_path / "absent.yaml", runs, out)
    (runs / f"{RUNS[1]}.jsonl").unlink()
    with pytest.raises(FileNotFoundError):
        ch.run(events, runs, out)
    assert not out.exists()


def test_health_summary_reads_the_report_as_it_is(files):
    events, runs, out = files
    report, _ = ch.run(events, runs, out)
    block = coverage_summary(report, "held-out (31 Oct-2 Nov, measured once)", "2026-11-03")
    assert block["overall"] == {"captured": 3, "n": 4}
    assert block["list"].startswith("held-out") and block["run_id"] == ch.REPORT_ID


def test_fixed_runs_and_files():
    assert ch.RUNS == ("20261031T1345Z-802913", "20261101T0400Z-e9cae4", "20261102T0400Z-bed018",
                       "20261103T0400Z-d03c41")
    assert ch.EVENTS_PATH.name == "coverage_events_heldout_20261031_20261102.yaml"
    assert ch.EVENTS_PATH != ch.coverage.EVENTS_PATH  # never the dev list
