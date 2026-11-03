"""D83: Health summaries saved into the demo snapshot, and demo Health reading only them."""
import json

import pytest
from fastapi.testclient import TestClient

from ci import demo
from ci import health_summary as hs
from ci.api.app import create_app
from tests.ci.test_api import CFG
from tests.ci.test_demo import snap  # noqa: F401

REPORT = {"run_id": "20261102T0400Z-bed018", "runs_dir": "output/runs",
          "events_file": "/home/someone/repo/evals/heldout_events.yaml", "window_days": 3,
          "window": {"first": "2026-10-31", "last": "2026-11-02"},
          "overall": {"events": 9, "captured": 7, "recall": 0.78, "captured_in_kept": 7, "captured_dropped_only": 0},
          "high_importance": {"min": 4, "events": 3, "captured": 3, "recall": 1.0},
          "by_source_kind": {"feed": {"events": 5, "captured": 5, "recall": 1.0},
                             "external": {"events": 4, "captured": 2, "recall": 0.5}},
          "missed": [{"id": "e1", "title": "Snyk adds X", "competitor": "snyk", "expected_importance": 3,
                      "official_url": "https://snyk.io/blog/x", "extra": "dropped"}],
          "events": [{"id": "e2", "matches": [{"title": "t", "url": "https://a"}]}]}


def test_coverage_summary_keeps_the_live_shape_and_drops_paths_and_matches():
    c = hs.coverage_summary(REPORT, "held-out (31 Oct-2 Nov)", "2026-11-03")
    assert c["list"] == "held-out (31 Oct-2 Nov)" and c["measured_on"] == "2026-11-03"
    assert c["overall"] == {"captured": 7, "n": 9} and c["important"] == {"captured": 3, "n": 3, "min_score": 4}
    assert c["by_source_kind"] == {"feed": {"captured": 5, "n": 5}, "external": {"captured": 2, "n": 4}}
    assert c["missed"] == [{k: v for k, v in REPORT["missed"][0].items() if k != "extra"}]
    text = json.dumps(c)
    assert "/home/" not in text and "matches" not in text and "events_file" not in text and "recall" not in text


def test_check_refuses_paths_and_per_item_fields_but_keeps_confusion_rows():
    with pytest.raises(hs.Unsafe, match="local path"):
        hs.check({"a": {"b": ["/home/ofri/x.json"]}})
    with pytest.raises(hs.Unsafe, match="matches"):
        hs.check({"events": [{"matches": []}]})
    hs.check({"metrics": {"confusion": {"category": [{"label": "Security", "pred": "AI", "n": 4}]}}})


def test_test_eval_summary_drops_per_item_misses_and_dates_itself():
    block = {"status": "ok", "created_at": "2026-11-02T16:46:38Z", "n": 29, "items": [{"id": "x"}],
             "metrics": {"extraction_detector": {"tp": 1, "misses": [{"id": "e7", "labeled_bad": True}]},
                         "category": {"accuracy": 0.71, "n": 24}}}
    s = hs.test_eval_summary(block)
    assert "items" not in s and s["metrics"]["extraction_detector"] == {"tp": 1}
    assert s["measured_on"] == "2026-11-02T16:46:38Z"


def test_demo_health_reads_only_the_snapshot_summaries(snap, tmp_path):  # noqa: F811
    out, _, _ = snap
    # output-style dirs full of results: demo mode must ignore them
    evals = tmp_path / "evals"
    evals.mkdir()
    (evals / "20261102T164638Z.json").write_text(json.dumps({"split": "test", "live": True, "created_at": "x"}))
    app = lambda: TestClient(create_app(cfg=CFG, demo=demo.load(out), evals_dir=evals,  # noqa: E731
                                        coverage_dir=tmp_path, changes_out_dir=tmp_path))
    h = app().get("/api/v1/health").json()
    for block in ("eval", "test_eval", "coverage", "change_detection"):
        assert h[block]["status"] == "not_in_snapshot" and "not included in this snapshot" in h[block]["note"]
    hs.save(out, "coverage", hs.coverage_summary(REPORT, "held-out (31 Oct-2 Nov)", "2026-11-03"))
    hs.save(out, "change_detection", hs.change_summary({"run_id": "c1", "started_at": "2026-11-03T04:05:48+00:00",
                                                        "status": "ok", "pages": 21, "changes": 0}))
    h = app().get("/api/v1/health").json()
    assert h["coverage"]["list"] == "held-out (31 Oct-2 Nov)" and h["coverage"]["overall"] == {"captured": 7, "n": 9}
    assert h["change_detection"]["pages"] == 21 and isinstance(h["change_detection"]["age_hours"], float)
    assert h["test_eval"]["status"] == "not_in_snapshot"  # the evals dir passed in was not read


def test_the_cli_writes_coverage_and_refuses_an_unsafe_report(tmp_path):
    rep = tmp_path / "r.json"
    rep.write_text(json.dumps(REPORT))
    args = ["coverage", "--report", str(rep), "--list", "held-out", "--measured-on", "2026-11-03", "--out",
            str(tmp_path / "snap")]
    assert hs.main(args) == 0 and (tmp_path / "snap" / "health" / "coverage.json").exists()
    rep.write_text(json.dumps({**REPORT, "missed": [{"id": "e", "official_url": "/home/x"}]}))
    assert hs.main(args) == 1
