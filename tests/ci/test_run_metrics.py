"""Per-run quality metrics (ci.run_metrics): one row per daily run, written at its end, served for Health."""
import json

import pytest
from fastapi.testclient import TestClient

from ci import daily, insights, lens, run_metrics
from ci.api.app import create_app
from ci.llm import FakeLLM
from ci.store import Store
from tests.ci.test_api import CFG, NOW, RUN2, build
from tests.ci.test_daily import OLD_RUN, A, B, fake_collect, paths, row, run  # noqa: F401
from tests.ci.test_dedupe import fake_embed
from tests.ci.test_lens import answer_row, lens_and_more, sheet_path  # noqa: F401


def metrics_of(paths, run_id):  # noqa: F811
    with Store(paths["store_path"]) as s:
        [m] = s.run_metrics(run_id)
    return m


def steps_of(m):
    return {x["step"]: x for x in m["steps"]}


def test_an_import_run_writes_one_metrics_row_with_counts_and_steps(paths):  # noqa: F811
    res = run(paths, from_run=OLD_RUN)
    assert res.status == "ok" and "metrics_error" not in res.report
    m = metrics_of(paths, OLD_RUN)
    assert (m["kind"], m["status"], m["started_at"]) == ("import", "ok", res.report["started_at"])
    assert m["fingerprints"] == {"classify_rank": "fp-test", "lens": lens.fingerprint(),
                                 "insights": insights.fingerprint()}
    it = m["items"]
    assert (it["kept"], it["test_skip"], it["to_model"], it["noise"], it["non_noise"]) == (3, 1, 2, 0, 2)
    assert it["published"] + it["held"] <= it["routed_n"] == 2
    assert m["extraction"]["n"] == 3 and set(m["extraction"]["by_source"]) == {"google_news"}
    assert m["validation"] == {"outputs": 0, "items": 0, "by_stage": {}, "reasons": []}
    s = steps_of(m)
    assert [x["step"] for x in m["steps"]] == ["load_run", "store", "classify", "rank", "validate", "lens", "insights"]
    assert s["classify"]["status"] == "ok" and s["classify"]["llm_calls"] >= 1 and s["classify"]["seconds"] >= 0
    assert (s["lens"]["status"], s["insights"]["status"]) == ("skipped", "skipped")
    assert m["llm_calls"] == res.report["llm_calls"]
    json.dumps(m)


def test_a_degraded_step_names_its_items(paths):  # noqa: F811
    def down(prompt, schema):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    run(paths, from_run=OLD_RUN, llm=FakeLLM(down))
    s = steps_of(metrics_of(paths, OLD_RUN))
    assert s["classify"]["status"] == "degraded" and set(s["classify"]["item_ids"]) == {A["id"], B["id"]}
    assert s["rank"]["status"] == "degraded" and "2 of 2 items degraded" in s["rank"]["errors"][0]


def test_a_crashed_step_is_recorded_as_where_the_run_stopped(paths, monkeypatch):  # noqa: F811
    class Boom:
        def __init__(self, llm):
            pass

        def rank(self, items, classifications):
            raise ValueError("ranker exploded")

    monkeypatch.setattr(daily, "Ranker", Boom)
    res = run(paths, from_run=OLD_RUN)
    assert res.status == "failed"
    m = metrics_of(paths, OLD_RUN)
    assert m["status"] == "failed" and "ranker exploded" in m["error"] and m["items"] is None
    s = steps_of(m)
    assert s["classify"]["status"] == "ok" and s["rank"]["status"] == "failed" and "validate" not in s


def test_a_failed_collection_writes_a_failed_row(paths):  # noqa: F811
    run(paths, collect=fake_collect([], failed=True))
    m = metrics_of(paths, "20261101T0400Z-bbbbbb")
    assert m["status"] == "failed" and steps_of(m)["collect"]["status"] == "failed" and m["llm_calls"] == 0


def test_lens_quote_check_and_relations_with_n(paths, sheet_path, monkeypatch):  # noqa: F811
    def answers(prompt, schema):
        item = schema["properties"]["items"]["items"]["properties"]
        if "relation" in item:
            a, b = item["id"]["enum"]
            return {"items": [answer_row(a), answer_row(b, capability_quote="stops every attack")]}
        return lens_and_more(prompt, schema)

    res = daily.run_daily(cfg=daily.ci_config.CIConfig(competitors=[]), embed_fn=fake_embed, fingerprint="fp",
                          from_run=OLD_RUN, llm=FakeLLM(answers), sheet_path=sheet_path, **paths)
    lm = metrics_of(paths, OLD_RUN)["lens"]
    assert res.status == "ok" and (lm["n"], lm["ok"], lm["rejected"]) == (2, 1, 1)
    assert lm["quote_check"] == {"passed": 1, "failed": 1, "n": 2}
    assert lm["relations"] == {"closes_gap": 1} and lm["relations_n"] == 1


def test_lens_block_counts_not_related_outside_the_quote_check():
    rows = [{"status": "ok", "relation": "not_related", "reason": ""},
            {"status": "ok", "relation": "improves_shared", "reason": ""},
            {"status": "rejected", "relation": None, "reason": "relation 'x' not in ..."},
            {"status": "failed", "relation": None, "reason": "batch failed"}]
    b = run_metrics.lens_block(rows, "ok")
    assert b["quote_check"] == {"passed": 1, "failed": 0, "n": 1}
    assert b["relations"] == {"not_related": 1, "improves_shared": 1} and (b["failed"], b["n"]) == (1, 4)


def test_insights_block_keeps_the_rejection_reasons():
    b = run_metrics.insights_block({"status": "partial", "insights": 1, "rejected": 1,
                                    "rejected_reasons": [{"title": "T", "reason": "claim not in source"}]})
    assert (b["produced"], b["rejected"], b["rejected_reasons"][0]["reason"]) == (1, 1, "claim not in source")
    assert run_metrics.insights_block({"status": "disabled"})["produced"] == 0


# ---- API ---------------------------------------------------------------------------------------------------------

def metrics_row(run_id, started_at):
    return run_metrics.build(run_id=run_id, kind="daily", status="degraded", started_at=started_at,
                             fingerprints={"classify_rank": "fp", "lens": "l", "insights": "i"}, model="fake",
                             llm_calls=3, steps=run_metrics.Steps(), items={"collected": 9})


@pytest.fixture
def api(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    with Store(store_path) as s:
        s.save_run_metrics(metrics_row(RUN2, s.run(RUN2)["started_at"]))
    evals = tmp_path / "evals"
    evals.mkdir()
    app = create_app(store_path=store_path, runs_dir=runs_dir, changes_path=tmp_path / "none.sqlite",
                     labels_out=tmp_path / "l.jsonl", split_path=split, cfg=CFG, now=lambda: NOW, embed_fn=fake_embed,
                     evals_dir=evals, coverage_dir=tmp_path / "cov", events_path=tmp_path / "events.yaml",
                     changes_out_dir=tmp_path / "chg", labels_path=tmp_path / "golden.jsonl")
    return TestClient(app), evals


def test_metrics_are_served_per_run_and_in_health(api):
    c, _ = api
    rows = c.get("/api/v1/run-metrics").json()
    assert rows["total"] == 1 and rows["items"][0]["run_id"] == RUN2
    assert c.get(f"/api/v1/run-metrics/{RUN2}").json()["items"] == {"collected": 9}
    assert c.get("/api/v1/run-metrics/nope").status_code == 404
    assert c.get("/api/v1/health").json()["run_metrics"]["fingerprints"]["lens"] == "l"


def test_test_eval_endpoint_shows_only_a_live_test_split_report(api):
    c, evals = api
    assert c.get("/api/v1/evals/test").json()["status"] == "none"
    (evals / "20261101T090000Z.json").write_text(json.dumps({
        "created_at": "2026-11-01T09:00:00Z", "split": "train", "live": True, "fingerprint": "fp", "n": 78}))
    (evals / "20261101T100000Z.json").write_text(json.dumps({
        "created_at": "2026-11-01T10:00:00Z", "split": "test", "live": True, "fingerprint": "c837f4fdaf70",
        "model": "gemini", "n": 29, "split_counts": {"test": 29, "train": 78},
        "metrics": {"competitor": {"accuracy": 0.9, "n": 29}}}))
    (evals / "insights_20261101T110000Z.json").write_text(json.dumps({"created_at": "2026-11-01T11:00:00Z"}))
    t = c.get("/api/v1/evals/test").json()
    assert (t["status"], t["n"], t["fingerprint"], t["created_at"]) == ("ok", 29, "c837f4fdaf70",
                                                                       "2026-11-01T10:00:00Z")
    assert t["metrics"]["competitor"]["n"] == 29 and t["test_runs"] == 1 and t["cards"]
    h = c.get("/api/v1/health").json()
    assert h["test_eval"]["report"] == "20261101T100000Z.json"
    assert h["eval"]["report"] == "20261101T100000Z.json"  # the insights eval file beside it is not a classifier eval


@pytest.mark.parametrize("kind", ["ok", "crash", "failed_collection"])
def test_a_failing_metrics_write_never_fails_the_run(paths, monkeypatch, caplog, kind):  # noqa: F811
    """The metrics row is a side output: a broken write is logged and noted in the report, the run's own status
    stands, on every path that writes one."""
    def broken(self, m):
        raise OSError("disk full")

    monkeypatch.setattr(Store, "save_run_metrics", broken)
    if kind == "crash":
        class Boom:
            def __init__(self, llm):
                pass

            def rank(self, items, classifications):
                raise ValueError("ranker exploded")

        monkeypatch.setattr(daily, "Ranker", Boom)
    res = (run(paths, collect=fake_collect([], failed=True)) if kind == "failed_collection"
           else run(paths, from_run=OLD_RUN))
    assert res.status == {"ok": "ok", "crash": "failed", "failed_collection": "failed"}[kind]
    assert res.report["metrics_error"] == "OSError: disk full"
    assert "run metrics not written" in caplog.text
    with Store(paths["store_path"]) as s:
        assert s.run(res.run_id)["status"] == res.status  # the run row is still finished
