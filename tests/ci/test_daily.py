"""The daily run and the store, offline: a fake collector, the FakeLLM and a fake embedding function."""
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from ci import daily
from ci.config import CIConfig
from ci.llm import FakeLLM
from ci.packet import Packet, packet_id
from ci.pipeline import RunResult
from ci.store import Store
from tests.ci.test_dedupe import fake_embed

CFG = CIConfig(window_days=7, competitors=[])
OLD_RUN = "20261030T1312Z-aaaaaa"
OLD_START = "2026-10-30T13:12:00+00:00"
NEW_START = "2026-11-01T04:00:00+00:00"


def row(url: str, title: str, run_id: str = OLD_RUN, source: str = "google_news") -> dict:
    p = Packet(source=source, origin="q", competitor="industry", title=title, url=url, original_url=url,
               published_at=datetime(2026, 10, 29, 10, tzinfo=UTC), text=f"{title} body text", id=packet_id(url),
               run_id=run_id, collected_at=datetime.fromisoformat(OLD_START))
    return p.model_dump(mode="json")


A = row("https://a.example/1", "Alpha ships a registry")
B = row("https://b.example/2", "Beta raises funding")
T = row("https://t.example/3", "Gamma held-out story")  # on the test side of the split


def answer(prompt: str, schema: dict) -> dict:
    """Classifier and ranker answers for every id in the schema."""
    ids = schema["properties"]["items"]["items"]["properties"]["id"]["enum"]
    if "score" in schema["properties"]["items"]["items"]["properties"]:
        return {"items": [{"id": i, "score": 3, "reason": "routine", "why_it_matters": "minor"} for i in ids]}
    return {"items": [{"id": i, "competitor": "none", "category": "Security", "noise": False, "confidence": 0.7}
                      for i in ids]}


@pytest.fixture
def paths(tmp_path):
    runs, data = tmp_path / "runs", tmp_path / "data"
    runs.mkdir()
    (runs / f"{OLD_RUN}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (A, B, T)), encoding="utf-8")
    (runs / f"{OLD_RUN}.report.json").write_text(json.dumps({
        "run_id": OLD_RUN, "started_at": OLD_START, "sources": {
            "google_news": {"collected": 5, "dup_url": 2, "dup_embedding": 0, "kept": 3, "errors": []}}}))
    split = tmp_path / "split_assignments.json"
    split.write_text(json.dumps({"version": 1, "sides": {A["id"]: "train", T["id"]: "test"}}))
    return {"runs_dir": runs, "data_dir": data, "store_path": data / "ci.sqlite", "split_path": split}


def run(paths, **kw):
    kw.setdefault("llm", FakeLLM(answer))
    kw.setdefault("sheet_path", paths["data_dir"] / "no-sheet.md")  # no lens unless a test gives a sheet
    return daily.run_daily(cfg=CFG, embed_fn=fake_embed, fingerprint="fp-test", **paths, **kw)


def rows_of(path, sql):
    db = sqlite3.connect(path)
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_import_keeps_discovery_time_and_stores_output_per_item(paths):
    llm = FakeLLM(answer)
    res = run(paths, from_run=OLD_RUN, llm=llm)
    assert res.status == "ok" and res.exit_code == 0
    with Store(paths["store_path"]) as s:
        assert s.item(A["id"])["discovered_at"] == OLD_START
        assert s.run(OLD_RUN)["fingerprint"] == "fp-test" and s.run(OLD_RUN)["kind"] == "import"
        out = {o["item_id"]: o for o in s.outputs()}
    assert set(out) == {A["id"], B["id"]}
    assert out[A["id"]]["run_id"] == OLD_RUN and out[A["id"]]["fingerprint"] == "fp-test"
    assert out[A["id"]]["ranking"]["score"] == 3
    assert res.report["llm_calls"] == len(llm.calls) == 2  # one classifier batch, one ranker batch
    totals = res.report["funnel"]["totals"]
    assert (totals["collected"], totals["dup_url"], totals["kept"], totals["new"]) == (5, 2, 3, 3)
    assert (paths["runs_dir"] / f"{OLD_RUN}.daily.json").exists()


def test_test_split_item_is_stored_but_never_reaches_the_model(paths):
    llm = FakeLLM(answer)
    res = run(paths, from_run=OLD_RUN, llm=llm)
    assert all(T["id"] not in prompt for prompt, _ in llm.calls)
    assert rows_of(paths["store_path"], "SELECT item_id, reason FROM skips") == [(T["id"], daily.TEST_SKIP)]
    assert rows_of(paths["store_path"], f"SELECT * FROM classifications WHERE item_id = '{T['id']}'") == []
    assert rows_of(paths["store_path"], f"SELECT * FROM rankings WHERE item_id = '{T['id']}'") == []
    assert res.report["funnel"]["totals"]["test_skip"] == 1


def test_missing_split_file_stops_before_collection_and_llm(paths):
    paths["split_path"].unlink()
    llm = FakeLLM(answer)

    def collect(*a, **k):
        raise AssertionError("must not collect")

    with pytest.raises(daily.SplitMissing):
        run(paths, llm=llm, collect=collect)
    assert llm.calls == []


def test_import_adds_items_to_the_dedupe_history(paths):
    run(paths, from_run=OLD_RUN)
    seen = rows_of(paths["data_dir"] / "seen_urls.sqlite", "SELECT id, run_id FROM seen")
    assert {i for i, _ in seen} == {A["id"], B["id"], T["id"]} and {r for _, r in seen} == {OLD_RUN}


def fake_collect(rows, run_id="20261101T0400Z-bbbbbb", failed=False):
    def collect(cfg, *, days=None, runs_dir=None, data_dir=None):
        report = {"run_id": run_id, "started_at": NEW_START, "status": "failed" if failed else "ok",
                  "status_reason": "every source failed and nothing was collected" if failed else "",
                  "pipeline_errors": [], "sources": {"google_news": {"collected": len(rows), "dup_url": 0,
                                                                     "dup_embedding": 0, "errors": []}}}
        return RunResult(run_id, [Packet.model_validate({**r, "run_id": run_id}) for r in rows], [], report)
    return collect


def test_daily_run_never_makes_a_known_item_new_again(paths):
    run(paths, from_run=OLD_RUN)
    c = row("https://c.example/4", "Delta new story", run_id="20261101T0400Z-bbbbbb")
    llm = FakeLLM(answer)
    res = run(paths, llm=llm, collect=fake_collect([A, c]))
    assert res.status == "ok"
    with Store(paths["store_path"]) as s:
        assert s.item(A["id"])["discovered_at"] == OLD_START  # not the new run's start
        assert s.item(c["id"])["discovered_at"] == NEW_START
    assert all(A["id"] not in prompt for prompt, _ in llm.calls)  # already classified: no second LLM call
    t = res.report["funnel"]["totals"]
    assert (t["known"], t["new"], t["to_model"]) == (1, 1, 1)
    assert len(rows_of(paths["store_path"], f"SELECT * FROM sightings WHERE item_id = '{A['id']}'")) == 2


def test_failed_collection_is_recorded_and_exits_non_zero(paths):
    llm = FakeLLM(answer)
    res = run(paths, llm=llm, collect=fake_collect([], failed=True))
    assert res.status == "failed" and res.exit_code == daily.EXIT_FAILED and llm.calls == []
    with Store(paths["store_path"]) as s:
        assert s.run("20261101T0400Z-bbbbbb")["status"] == "failed"


def test_llm_failure_stores_degraded_output_and_exits_3(paths):
    def down(prompt, schema):
        raise RuntimeError("503")

    res = run(paths, from_run=OLD_RUN, llm=FakeLLM(down))
    assert res.status == "degraded" and res.exit_code == daily.EXIT_DEGRADED
    t = res.report["funnel"]["totals"]
    assert (t["fallback"], t["rank_degraded"]) == (2, 2)
    with Store(paths["store_path"]) as s:
        assert s.run(OLD_RUN)["status"] == "degraded" and s.run(OLD_RUN)["error"]
        assert len(s.outputs()) == 2  # stored, flagged degraded, never silently a normal score


def test_store_discovery_time_only_moves_earlier(tmp_path):
    with Store(tmp_path / "ci.sqlite") as s:
        assert s.add_items([A], "later", "2026-11-02T00:00:00+00:00") == [A["id"]]
        assert s.add_items([A], "earlier", OLD_START) == []
        assert s.item(A["id"])["discovered_at"] == OLD_START and s.item(A["id"])["first_run_id"] == "earlier"
        s.add_items([A], "latest", "2026-11-05T00:00:00+00:00")
        assert s.item(A["id"])["discovered_at"] == OLD_START


def test_default_fingerprint_is_the_evals(paths, monkeypatch):
    monkeypatch.setattr(daily.eval_golden, "fingerprint", lambda cfg: "eval-fp")
    res = daily.run_daily(cfg=CFG, embed_fn=fake_embed, from_run=OLD_RUN, llm=FakeLLM(answer), **paths)
    assert res.report["fingerprint"] == "eval-fp"


@pytest.mark.parametrize(("outcome", "code"), [("split", 1), ("degraded", 3), ("ok", 0)])
def test_main_exit_codes(monkeypatch, capsys, outcome, code):
    def fake(**kw):
        if outcome == "split":
            raise daily.SplitMissing("missing")
        report = {"run_id": "r", "kind": "daily", "status": outcome, "fingerprint": "f", "model": "m",
                  "llm_calls": 0, "errors": [], "funnel": {"sources": {}, "totals": dict.fromkeys(
                      daily.FUNNEL_COLUMNS, 0)}}
        return daily.DailyResult("r", outcome, report, ["x"] if outcome != "ok" else [])

    monkeypatch.setattr(daily, "run_daily", fake)
    monkeypatch.setattr(daily, "run_lock", _no_lock)
    assert daily.main([]) == code
    err = capsys.readouterr().err
    assert {"split": "FAILED", "degraded": "DEGRADED", "ok": ""}[outcome] in err


class _no_lock:
    def __init__(self, name):
        pass

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False



def test_invalid_model_output_is_rejected_logged_and_sent_to_review(paths, caplog):
    def bad(prompt, schema):
        got = answer(prompt, schema)
        if "score" in schema["properties"]["items"]["items"]["properties"]:
            got["items"][0]["score"] = 9  # outside 1-5
        else:
            got["items"][0]["competitor"] = "jetbrains"  # not in the config list
            got["items"].append({**got["items"][1], "id": "invented0000000"})  # not an item we sent
        return got

    res = run(paths, from_run=OLD_RUN, llm=FakeLLM(bad))
    assert res.status == "degraded" and res.exit_code == daily.EXIT_DEGRADED
    rej = rows_of(paths["store_path"], "SELECT item_id, stage, reason FROM rejections ORDER BY stage, item_id")
    by_item = {(i, st) for i, st, _ in rej}
    assert (A["id"], "classifier") in by_item and ("invented0000000", "classifier") in by_item
    assert any(st == "ranker" and "outside 1-5" in why for _, st, why in rej)
    assert "rejected classifier output for item invented0000000" in caplog.text
    with Store(paths["store_path"]) as s:
        out = {o["item_id"]: o for o in s.outputs()}
    assert "invented0000000" not in out  # an id we never sent is not stored
    assert out[A["id"]]["ranking"]["needs_review"]
    assert any(r.startswith("invalid output (classifier)") for r in out[A["id"]]["ranking"]["review_reasons"])
    assert res.report["funnel"]["totals"]["rejected"] >= 1


def test_the_fetch_status_reaches_the_store_and_the_item_payload(paths):
    """D39: a daily run stores why an item's text is missing, and the API shows it as the text basis reason.
    (The 31 Oct 13:45Z run predates a78fd35, so its items say not_recorded; this pins the path end to end.)"""
    from ci.api import service as svc

    blocked = {**row("https://thehackernews.com/x", "Teaser only story", run_id="20261101T0400Z-bbbbbb"),
               "fetch_status": "cloudflare_challenge", "fetch_http_status": 403}
    assert run(paths, collect=fake_collect([blocked])).status == "ok"
    with Store(paths["store_path"]) as s:
        raw = json.loads(s.item(blocked["id"])["raw"])
    assert (raw["fetch_status"], raw["fetch_http_status"]) == ("cloudflare_challenge", 403)
    assert svc.text_basis(raw)["reason"] == "cloudflare_challenge"
