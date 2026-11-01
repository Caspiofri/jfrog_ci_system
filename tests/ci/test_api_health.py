"""Health screen through the API (D17, D21), offline: funnel, silent sources, eval cards with n, coverage counts."""
import json

import pytest
from fastapi.testclient import TestClient

from ci.api import health
from ci.api.app import create_app
from ci.store import Store
from tests.ci.test_api import CFG, NOW, RUN1, RUN2, build
from tests.ci.test_dedupe import fake_embed


def funnel_report(gn, hn, vf, hn_errors=()):
    return {"llm_calls": 6, "errors": [], "funnel": {"sources": {
        "google_news": {"collected": gn, "dup_url": 1, "kept": gn - 1, "errors": []},
        "hackernews": {"collected": hn, "dup_url": 0, "kept": hn, "errors": list(hn_errors)},
        "vendor_feed": {"collected": vf, "dup_url": 0, "kept": vf, "errors": []}}}}


@pytest.fixture
def env(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    with Store(store_path) as s:
        s.finish_run(RUN1, "ok", funnel_report(9, 2, 0))
        s.finish_run(RUN2, "ok", funnel_report(2, 0, 0, hn_errors=["query 'Snyk' failed: 503"]))
    evals, cov, chg = tmp_path / "evals", tmp_path / "coverage", tmp_path / "changes"
    for p in (evals, cov, chg):
        p.mkdir()
    (evals / "20261031T100000Z.json").write_text(json.dumps({
        "created_at": "2026-10-31T10:00:00Z", "split": "train", "live": True, "fingerprint": "fp", "n": 40,
        "metrics": {"competitor": {"accuracy": 0.9, "n": 30}, "category": {"accuracy": 0.8, "n": 5},
                    "noise": {"tp": 8, "fp": 1, "fn": 2, "precision": 0.89, "recall": 0.8},
                    "score": {"n": 30, "exact": 0.5, "within_1": 0.9},
                    "important": {"precision": 1.0, "precision_n": 2, "recall": 0.5, "recall_n": 2},
                    "mentions_jfrog": {"tp": 0, "fp": 0, "fn": 0}}}))
    labels = tmp_path / "golden.jsonl"
    labels.write_text("".join(json.dumps(r) + "\n" for r in [
        {"id": "a", "noise": False, "score": 4, "category": "Security"},
        {"id": "b", "noise": False, "score": 3, "category": "Security"},
        {"id": "c", "noise": True}]))
    (chg / "20261031T0500Z-cccccc.report.json").write_text(json.dumps({
        "run_id": "20261031T0500Z-cccccc", "started_at": "2026-10-31T05:00:00+00:00", "live": True, "status": "ok",
        "pages": 21, "fetched": 21, "changes": 1, "failures": [], "unconfirmed": [], "needs_review": []}))
    app = create_app(store_path=store_path, runs_dir=runs_dir, changes_path=tmp_path / "none.sqlite",
                     labels_out=tmp_path / "l.jsonl", split_path=split, cfg=CFG, now=lambda: NOW, embed_fn=fake_embed,
                     evals_dir=evals, coverage_dir=cov, events_path=tmp_path / "events.yaml", changes_out_dir=chg,
                     labels_path=labels)
    return TestClient(app), tmp_path


def test_run_and_funnel_with_routing_at_the_current_level(env):
    c, _ = env
    h = c.get("/api/v1/health").json()
    assert h["run"]["run_id"] == RUN2 and h["run"]["llm_calls"] == 6
    f = {r["source"]: r for r in h["funnel"]["sources"]}
    assert (f["google_news"]["collected"], f["google_news"]["kept"]) == (2, 1)
    assert (f["google_news"]["published"], f["google_news"]["held_for_review"]) == (1, 0)  # new2
    h1 = c.get("/api/v1/health", params={"run_id": RUN1}).json()["funnel"]["totals"]
    assert (h1["published"], h1["held_for_review"]) == (2, 3)  # pub1, late / uv, uv4, jf
    assert c.get("/api/v1/health", params={"run_id": "nope"}).status_code == 404


def test_silent_sources_say_how_many_runs_so_far(env):
    c, _ = env
    s = c.get("/api/v1/health").json()["silent_sources"]
    assert s["runs_so_far"] == 2 and s["label"] == "2 runs so far" and s["insufficient_history"] is False
    st = {r["source"]: r["status"] for r in s["items"]}
    assert st == {"google_news": "healthy", "hackernews": "critical", "vendor_feed": "silent"}
    gn = next(r for r in s["items"] if r["source"] == "google_news")
    assert gn["last_item"] == "2026-10-31T04:00:00Z" and gn["hours_silent"] == 5.0


def test_one_run_is_not_enough_to_call_a_source_silent(env):
    c, tmp = env
    with Store(tmp / "ci.sqlite") as s:
        s._db.execute("DELETE FROM runs WHERE run_id = ?", (RUN1,))
        s._db.commit()
    s = c.get("/api/v1/health").json()["silent_sources"]
    assert s["label"] == "1 run so far" and s["insufficient_history"] is True
    assert {r["source"]: r["status"] for r in s["items"]}["vendor_feed"] == "healthy"  # not "silent" after 1 run


def test_eval_cards_carry_n_and_weak_and_untested_markers(env):
    c, _ = env
    e = c.get("/api/v1/health").json()["eval"]
    cards = {x["metric"]: x for x in e["cards"]}
    assert e["split"] == "train" and e["test_eval_run"] is False
    assert cards["competitor_accuracy"].items() >= {"value": 0.9, "n": 30, "weak": False, "untested": False}.items()
    assert cards["category_accuracy"]["weak"] is True  # n = 5 < 10
    assert (cards["noise_precision"]["n"], cards["noise_recall"]["n"]) == (9, 10)
    imp = cards["important_recall"]
    assert imp["weak"] is True and "1 of 2 non-noise labels score 4-5" in imp["note"]
    assert "coverage check is the main evidence" in imp["note"]
    assert cards["mentions_jfrog_precision"]["untested"] is True
    assert cards["funding_m_and_a"].items() >= {"n": 0, "untested": True}.items()
    assert e["labels"] == {"total": 3, "non_noise": 2, "important": 1, "funding_m_and_a": 0}


def test_coverage_is_counts_with_n_and_change_detection_is_summarised(env, monkeypatch):
    c, tmp = env
    h = c.get("/api/v1/health").json()
    assert h["coverage"]["status"] == "none"  # no coverage report yet
    assert h["change_detection"]["pages"] == 21 and h["change_detection"]["age_hours"] == 4.0
    (tmp / "coverage" / f"{RUN1}.json").write_text("{}")
    (tmp / "runs" / f"{RUN1}.jsonl").write_text("")
    (tmp / "events.yaml").write_text("events: []\n")
    monkeypatch.setattr(health.coverage, "run_window", lambda run_id, runs_dir: ("2026-10-16", "2026-10-30", 14))
    monkeypatch.setattr(health.coverage, "evaluate", lambda *a, **k: {
        "window": {"first": "2026-10-16", "last": "2026-10-30"},
        "overall": {"events": 25, "captured": 24}, "high_importance": {"min": 4, "events": 3, "captured": 3},
        "by_source_kind": {"feed": {"events": 19, "captured": 19}}, "missed": [{"id": "aws-inspector"}]})
    cov = c.get("/api/v1/health").json()["coverage"]
    assert cov["overall"] == {"captured": 24, "n": 25} and cov["important"] == {"captured": 3, "n": 3, "min_score": 4}
    assert "recall" not in json.dumps(cov)  # counts with n, never a rate
    assert cov["list"].startswith("dev")


def test_runs_list(env):
    c, _ = env
    rows = c.get("/api/v1/runs").json()["items"]
    assert [r["run_id"] for r in rows] == [RUN2, RUN1] and rows[0]["llm_calls"] == 6


def test_extraction_success_per_source_and_publisher_with_n(env):
    c, tmp = env
    with Store(tmp / "ci.sqlite") as s:  # one Google News item of the daily run whose page fetch failed
        from tests.ci.test_api import raw as mkraw
        row = {**mkraw("blocked", "https://devops.com/x", "Blocked by Cloudflare", "2026-10-31T01:00:00Z", RUN2),
               "text": "", "text_status": "snippet", "publisher": "DevOps.com"}
        s.add_items([row], RUN2, "2026-10-31T04:00:00+00:00")
    ex = c.get("/api/v1/health").json()["extraction"]
    run = ex["run"]
    assert run["run_id"] == RUN2 and (run["extracted"], run["n"], run["rate"]) == (1, 2, 0.5)
    gn = next(r for r in run["by_source"] if r["key"] == "google_news")
    assert (gn["extracted"], gn["n"]) == (1, 2) and gn["by_status"]["snippet"] == 1
    pubs = {r["key"]: (r["extracted"], r["n"]) for r in run["by_publisher"]}
    assert pubs["DevOps.com"] == (0, 1) and pubs["theregister.com"] == (1, 1)
    assert (ex["all"]["extracted"], ex["all"]["n"]) == (8, 9)  # 7 fixture items + the test-split item + blocked
    assert pubs and next(r for r in run["by_publisher"] if r["key"] == "DevOps.com")["fetch"] == {"not_recorded": 1}
    assert ex["all"]["fetch"] == {"not_recorded": 9}  # items stored before fetch_status existed


def test_liveness_flags_stale_and_overdue_runs():
    """D48: a killed run stays "running" and a missed day leaves no row; both looked like yesterday's success."""
    from datetime import UTC, datetime

    now = datetime(2026, 11, 2, 12, tzinfo=UTC)

    def r(run_id, status, started, processed=None, kind="daily"):
        return {"run_id": run_id, "kind": kind, "status": status, "started_at": started,
                "processed_at": processed or started}

    assert health.liveness([], now)["state"] == "none"
    ok = r("a", "ok", "2026-11-02T04:00:00+00:00")
    assert health.liveness([ok], now)["state"] == "ok" and health.liveness([ok], now)["hours_since_latest"] == 8.0
    hung = r("b", "running", "2026-11-02T04:00:00+00:00", "2026-11-02T04:05:00+00:00")
    assert health.marker(hung, now) == "stale" and health.liveness([hung], now)["stale_run_ids"] == ["b"]
    fresh = r("c", "running", "2026-11-02T11:30:00+00:00")
    assert health.liveness([ok, fresh], now)["state"] == "running"
    old = r("d", "ok", "2026-11-01T04:00:00+00:00")  # 32 h ago: the 2 Nov run never happened
    assert health.liveness([old], now)["state"] == "overdue"
    imp = r("e", "ok", "2026-11-02T10:00:00+00:00", kind="import")  # an import is not the daily run
    assert health.liveness([old, imp], now)["state"] == "overdue"
    assert health.liveness([old, r("f", "failed", "2026-11-02T04:00:00+00:00")], now)["state"] == "failed"


def test_health_and_runs_carry_the_liveness_markers(env):
    c, _ = env
    live = c.get("/api/v1/health").json()["liveness"]
    assert live["latest_run_id"] in (RUN1, RUN2) and live["state"] in ("ok", "overdue")
    assert (live["stale_after_hours"], live["overdue_after_hours"]) == (1.0, 26.0)
    assert {r["marker"] for r in c.get("/api/v1/runs").json()["items"]} <= {"ok", "degraded", "failed", "stale",
                                                                              "running"}
