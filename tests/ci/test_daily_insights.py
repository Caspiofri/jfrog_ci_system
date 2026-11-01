"""Insights inside the daily run (D49 review, D45): a failure is stored as failed (the Brief says failed, not
"never ran"), a second run on the same Israel day leaves the Brief's insights alone, and a failed refresh answers
with the error envelope. Offline."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ci import daily
from ci.api.app import create_app
from ci.llm import FakeLLM
from ci.packet import Packet
from ci.pipeline import RunResult
from ci.store import Store
from tests.ci.test_daily import CFG, paths, row  # noqa: F401  (paths is the fixture)
from tests.ci.test_dedupe import fake_embed
from tests.ci.test_lens import lens_and_more, sheet_path  # noqa: F401

# vetted host, so the items are published at Strict and reach the insights generator
V1, V2 = row("https://www.theregister.com/a", "Vetted story one"), row("https://www.theregister.com/b", "Story two")
MORNING, AFTERNOON = "2026-11-01T04:00:00+00:00", "2026-11-01T13:00:00+00:00"  # 06:00 and 15:00 in Israel


def collect_at(run_id, started_at, rows):
    def collect(cfg, *, days=None, runs_dir=None, data_dir=None):
        report = {"run_id": run_id, "started_at": started_at, "status": "ok", "status_reason": "",
                  "pipeline_errors": [], "sources": {"google_news": {"collected": len(rows), "dup_url": 0,
                                                                     "dup_embedding": 0, "errors": []}}}
        return RunResult(run_id, [Packet.model_validate({**r, "run_id": run_id}) for r in rows], [], report)
    return collect


def daily_run(paths, sheet_path, collect, embed_fn=fake_embed):  # noqa: F811
    return daily.run_daily(cfg=CFG, embed_fn=embed_fn, fingerprint="fp", llm=FakeLLM(lens_and_more),
                           sheet_path=sheet_path, collect=collect, **paths)


@pytest.fixture
def enabled(paths):  # noqa: F811
    paths["data_dir"].mkdir(parents=True, exist_ok=True)
    with Store(paths["store_path"]) as s:
        s.set_setting("insights_enabled", "true")
    return paths


def test_an_insights_failure_is_stored_as_failed(enabled, sheet_path):  # noqa: F811
    calls = {"n": 0}

    def embed(texts):  # dedupe of the run works; the insights' story grouping (the second call) breaks
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("embedding model unavailable")
        return fake_embed(texts)

    res = daily_run(enabled, sheet_path, collect_at("20261101T0400Z-mmmmmm", MORNING, [V1, V2]), embed_fn=embed)
    assert res.status == "degraded" and res.report["insights"]["status"] == "failed"
    with Store(enabled["store_path"]) as s:
        stored = s.latest_insights("2026-11-01")
    assert stored["status"] == "failed" and "embedding model unavailable" in stored["error"]
    c = TestClient(create_app(store_path=enabled["store_path"], runs_dir=enabled["runs_dir"], cfg=CFG,
                              now=lambda: datetime(2026, 11, 1, 6, tzinfo=UTC)))
    assert c.get("/api/v1/brief", params={"date": "2026-11-01"}).json()["insights"]["status"] == "failed"


def test_a_second_run_on_the_same_day_leaves_the_briefs_insights_alone(enabled, sheet_path):  # noqa: F811
    first = daily_run(enabled, sheet_path, collect_at("20261101T0400Z-mmmmmm", MORNING, [V1]))
    assert first.report["insights"]["brief_date"] == "2026-11-01"
    with Store(enabled["store_path"]) as s:
        before = s.latest_insights("2026-11-01")["generated_at"]
    later = row("https://www.theregister.com/afternoon", "Afternoon story")
    second = daily_run(enabled, sheet_path, collect_at("20261101T1300Z-aaaaaa", AFTERNOON, [later]))
    assert second.report["insights"]["status"] == "skipped"
    assert "anchored on run 20261101T0400Z-mmmmmm" in second.report["insights"]["reason"]
    with Store(enabled["store_path"]) as s:
        assert s.latest_insights("2026-11-01")["generated_at"] == before
        [m] = s.run_metrics("20261101T1300Z-aaaaaa")
    assert {x["step"]: x for x in m["steps"]}["insights"]["status"] == "skipped"
    assert second.status == "ok"  # skipping is not an error


def test_a_failed_refresh_answers_with_the_error_envelope(enabled, sheet_path):  # noqa: F811
    daily_run(enabled, sheet_path, collect_at("20261101T0400Z-mmmmmm", MORNING, [V1, V2]))

    def broken(texts):
        raise RuntimeError("embedding model unavailable")

    c = TestClient(create_app(store_path=enabled["store_path"], runs_dir=enabled["runs_dir"], cfg=CFG,
                              now=lambda: datetime(2026, 11, 1, 6, tzinfo=UTC), embed_fn=broken,
                              insights_llm=lambda: FakeLLM(lens_and_more)))
    r = c.post("/api/v1/brief/2026-11-01/insights/refresh")
    assert r.status_code == 502 and r.json()["error"]["code"] == "insights_failed"
    with Store(enabled["store_path"]) as s:
        assert s.setting("insights_refreshing:2026-11-01") == ""  # the running mark is cleared
