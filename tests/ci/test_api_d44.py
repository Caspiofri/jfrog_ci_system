"""D44, the Daily Brief information hierarchy: the Brief lists published items scored 3+, a summary block counts the
window (published and held by preliminary score) from the same query, Review filters to one Brief window, insight
states, and the text basis and lens on every item. Offline, on the test_api fixture plus a few more runs."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ci.api.app import create_app
from ci.classify import Classification
from ci.llm import FakeLLM
from ci.rank import Ranked
from ci.store import Store
from tests.ci.test_api import CFG, build, ids, raw
from tests.ci.test_dedupe import fake_embed

NOW = datetime(2026, 11, 3, 9, tzinfo=UTC)
RUN3, START3 = "20261101T0400Z-cccccc", "2026-11-01T04:00:00+00:00"  # Brief 2026-11-01: a mix
RUN4, START4 = "20261102T0400Z-dddddd", "2026-11-02T04:00:00+00:00"  # Brief 2026-11-02: nothing new
RUN5, START5 = "20261103T0400Z-eeeeee", "2026-11-03T04:00:00+00:00"  # Brief 2026-11-03: every item held
VETTED, UNVETTED = "https://www.theregister.com/", "https://gbhackers.com/"

# item_id: (host, published, score, run, extra raw fields)
MORE = {
    "s5": (VETTED, "2026-10-31T20:00:00Z", 5, RUN3, {}),
    "s3": (VETTED, "2026-10-31T21:00:00Z", 3, RUN3, {"text_status": "snippet", "text_source": "teaser",
                                                    "text": "A short teaser.", "fetch_status": "cloudflare_challenge"}),
    "s2": (VETTED, "2026-10-31T22:00:00Z", 2, RUN3, {}),
    "s1": (VETTED, "2026-10-31T23:00:00Z", 1, RUN3, {}),
    "h4": (UNVETTED, "2026-10-31T19:00:00Z", 4, RUN3, {}),
    "h2": (UNVETTED, "2026-10-31T18:00:00Z", 2, RUN3, {}),
    # a scheduled changelog entry: the source dates it after our run (C2)
    "fut": (VETTED, "2026-11-02T05:00:00Z", 3, RUN3, {}),
    "a5": (UNVETTED, "2026-11-02T20:00:00Z", 5, RUN5, {}),
    "a3": (UNVETTED, "2026-11-02T21:00:00Z", 3, RUN5, {}),
}


def add_runs(store_path):
    with Store(store_path) as s:
        for run, start in ((RUN3, START3), (RUN4, START4), (RUN5, START5)):
            s.start_run(run, "daily", start, "fp", "fake")
            s.finish_run(run, "ok", {})
            mine = {i: v for i, v in MORE.items() if v[3] == run}
            s.add_items([{**raw(i, f"{host}{i}", f"Story {i}", pub, run), **extra}
                         for i, (host, pub, _, _, extra) in mine.items()], run, start)
            s.save_outputs(run, "fp", [Classification(id=i, competitor="github", category="Product & Features",
                                                      noise=False, mentions_jfrog=False, confidence=0.9,
                                                      method="llm") for i in mine],
                           [Ranked(id=i, raw_score=v[2], score=v[2], noise=False, reason="r", why_it_matters="w",
                                   confidence=0.9) for i, v in mine.items()])


@pytest.fixture
def env(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    add_runs(store_path)
    app = create_app(store_path=store_path, runs_dir=runs_dir, changes_path=tmp_path / "none.sqlite",
                     labels_out=tmp_path / "labels.jsonl", split_path=split, cfg=CFG, now=lambda: NOW,
                     insights_llm=lambda: FakeLLM(lambda p, s: {"insights": []}), embed_fn=fake_embed)
    return TestClient(app), store_path


def brief(c, date):
    return c.get("/api/v1/brief", params={"date": date}).json()


def review(c, **params):
    return c.get("/api/v1/review", params=params).json()


def test_brief_lists_published_3_plus_and_counts_the_rest(env):
    c, _ = env
    b = brief(c, "2026-11-01")
    assert b["brief_min_score"] == 3
    assert ids(b["items"]["items"]) == ["s5", "fut", "s3"]  # s2 and s1 are published but below the Brief
    assert b["summary"] == {"brief_min_score": 3, "published": 3, "published_high": 1,
                            "published_below": 2, "held": 2, "held_high": 1,
                            "held_by_preliminary_score": {"5": 0, "4": 1, "3": 0, "<=2": 1, "unscored": 0, "noise": 0},
                            "level": "strict"}
    assert b["summary"]["published"] == b["items"]["total"]
    assert b["counts"]["items"] == 5  # deprecated counts keep their old meaning: every published item


def test_held_total_is_the_window_filtered_review_queue(env):
    c, _ = env
    for date in ("2026-10-30", "2026-11-01", "2026-11-02", "2026-11-03"):
        r = review(c, brief=date)
        assert r["total"] == brief(c, date)["summary"]["held"], date
        assert r["scope"]["brief"] == date and r["scope"]["window"]["anchor"]
    r = review(c, brief="2026-11-01")
    assert sorted(x["item"]["item_id"] for x in r["items"]) == ["h2", "h4"]
    assert r["backlog_total"] == 7 == review(c)["total"]  # uv, uv4, jf, h4, h2, a5, a3: the whole backlog
    assert review(c)["backlog_total"] == 7
    assert c.get("/api/v1/review", params={"brief": "2026-12-25"}).json()["error"]["code"] == "not_found"


def test_the_14_day_import_day(env):
    c, _ = env
    b = brief(c, "2026-10-30")
    assert b["window"]["anchor_kind"] == "import"
    assert ids(b["items"]["items"]) == ["pub1", "late"]
    s = b["summary"]
    assert (s["published"], s["published_high"], s["published_below"]) == (2, 1, 0)
    assert s["held"] == 3
    assert s["held_by_preliminary_score"] == {"5": 0, "4": 1, "3": 2, "<=2": 0, "unscored": 0, "noise": 0}


def test_empty_window(env):
    c, _ = env
    b = brief(c, "2026-11-02")
    assert b["status"] == "ok" and b["items"]["total"] == 0 and b["items"]["items"] == []
    assert b["summary"] == {"brief_min_score": 3, "published": 0, "published_high": 0,
                            "published_below": 0, "held": 0, "held_high": 0,
                            "held_by_preliminary_score": {"5": 0, "4": 0, "3": 0, "<=2": 0, "unscored": 0, "noise": 0},
                            "level": "strict"}
    assert review(c, brief="2026-11-02")["total"] == 0


def test_all_items_held(env):
    c, _ = env
    b = brief(c, "2026-11-03")
    assert b["items"]["total"] == 0  # "nothing published" is not "nothing important": the summary says why
    assert b["summary"]["held"] == 2 and b["summary"]["held_high"] == 1
    assert b["summary"]["held_by_preliminary_score"] == {"5": 1, "4": 0, "3": 1, "<=2": 0, "unscored": 0, "noise": 0}
    rows = c.get("/api/v1/briefs").json()["items"]
    assert {r["date"]: (r["published"], r["held"]) for r in rows}["2026-11-03"] == (0, 2)


def test_a_future_dated_item_is_stored_at_its_discovery_time(env):
    c, store_path = env
    it = c.get("/api/v1/items/fut").json()["item"]
    assert it["published_at"] == it["discovered_at"] == "2026-11-01T04:00:00Z"
    assert it["discovery_lag_hours"] == 0.0 and it["badge"] is None
    assert next(x for x in brief(c, "2026-11-01")["items"]["items"] if x["item_id"] == "fut")["badge"] == "new"
    with Store(store_path) as s:
        assert s._db.execute("SELECT COUNT(*) FROM items WHERE published_at > discovered_at").fetchone()[0] == 0


def test_the_threshold_is_a_config_value(env, tmp_path):
    _, store_path = env
    cfg_path = tmp_path / "brief.yaml"
    cfg_path.write_text("min_score: 2\n")
    c = TestClient(create_app(store_path=store_path, runs_dir=tmp_path / "runs", changes_path=tmp_path / "x.sqlite",
                              cfg=CFG, now=lambda: NOW, brief_config_path=cfg_path))
    b = brief(c, "2026-11-01")
    assert b["brief_min_score"] == 2 and ids(b["items"]["items"]) == ["s5", "fut", "s3", "s2"]
    assert b["summary"]["published_below"] == 1


def test_text_basis_and_lens_fields(env):
    c, store_path = env
    s3 = c.get("/api/v1/items/s3").json()["item"]
    assert s3["text_basis"] == {"status": "snippet", "source": "teaser", "label": "Headline and teaser only",
                                "reason": "cloudflare_challenge", "reason_detail": None,
                                "chars_used_for_scoring": len("A short teaser.")}
    s5 = c.get("/api/v1/items/s5").json()["item"]
    assert s5["text_basis"]["reason"] is None and s5["text_basis"]["label"] == "Full article"
    assert s5["text_basis"]["chars_used_for_scoring"] == 1080 and s5["lens"] is None
    with Store(store_path) as s:
        s.save_lens(RUN3, "lensfp", [
            {"item_id": "s5", "status": "ok", "axis": "ai_mcp", "capability_quote": "MCP Registry",
             "relation": "improves_shared", "why": "It touches JFrog's MCP Registry.", "reason": ""},
            {"item_id": "s3", "status": "ok", "axis": None, "capability_quote": "", "relation": "not_related",
             "why": "No JFrog capability.", "reason": ""},
            {"item_id": "s2", "status": "rejected", "axis": None, "capability_quote": "", "relation": None,
             "why": "", "reason": "capability quote not on the sheet"}])
    assert c.get("/api/v1/items/s5").json()["item"]["lens"] == {
        "axis": "ai_mcp", "capability_quote": "MCP Registry", "relation": "improves_shared",
        "why_it_matters": "It touches JFrog's MCP Registry.", "why": "It touches JFrog's MCP Registry."}
    lens3 = c.get("/api/v1/items/s3").json()["item"]["lens"]
    assert lens3["axis"] is None and lens3["capability_quote"] is None and lens3["relation"] == "not_related"
    assert c.get("/api/v1/items/s2").json()["item"]["lens"] is None


def test_lens_status_says_whether_a_lens_ran_and_how_it_ended(env):
    c, store_path = env
    assert c.get("/api/v1/items/s5").json()["item"]["lens_status"] is None  # no lens row
    with Store(store_path) as s:
        s.save_lens(RUN3, "lensfp", [
            {"item_id": "s5", "status": "ok", "axis": "ai_mcp", "capability_quote": "MCP Registry",
             "relation": "improves_shared", "why": "w", "reason": ""},
            {"item_id": "s2", "status": "rejected", "axis": None, "capability_quote": "", "relation": None,
             "why": "", "reason": "capability quote not on the sheet"},
            {"item_id": "s3", "status": "failed", "axis": None, "capability_quote": "", "relation": None,
             "why": "", "reason": "model error"}])
    got = {i: c.get(f"/api/v1/items/{i}").json()["item"] for i in ("s5", "s2", "s3")}
    assert {i: x["lens_status"] for i, x in got.items()} == {"s5": "ok", "s2": "rejected", "s3": "failed"}
    assert got["s2"]["lens"] is None and got["s3"]["lens"] is None  # lens stays null unless ok
    b = c.get("/api/v1/brief?date=2026-11-01").json()
    assert all("lens_status" in it for it in b["items"]["items"])


def stored(status, kept=0, rejected=0):
    return {"generated_at": "2026-11-01T05:00:00+00:00", "trigger": "daily", "level": "strict", "status": status,
            "fingerprint": "f", "model": "m", "insights": [{"insight_id": f"i{n}"} for n in range(kept)],
            "rejected": [{"title": "t", "pattern": "p", "reason": "quote not found"}] * rejected}


def test_insight_states(env):
    c, store_path = env
    assert brief(c, "2026-11-01")["insights"]["status"] == "disabled"
    with Store(store_path) as s:
        s.set_setting("insights_enabled", "true")
    assert brief(c, "2026-11-01")["insights"]["status"] == "not_run"
    for result, state, rejected in ((stored("none", rejected=3), "none_passed", 3),
                                    (stored("none"), "none_passed", 0),
                                    (stored("failed"), "failed", 0),
                                    (stored("partial", kept=2, rejected=1), "ok", 1)):
        with Store(store_path) as s:
            s.save_insights("2026-11-01", result)
            s._db.execute("UPDATE insights SET generated_at = ? WHERE rowid = last_insert_rowid()",
                          (datetime.now(UTC).isoformat(),))
            s._db.commit()
        b = brief(c, "2026-11-01")
        assert (b["insights"]["status"], b["insights"]["rejected"]) == (state, rejected), state
    with Store(store_path) as s:
        s.set_setting("insights_refreshing:2026-11-01", "2026-11-03T08:55:00Z")  # 5 minutes before NOW
    assert brief(c, "2026-11-01")["insights"]["status"] == "refreshing"
    assert c.post("/api/v1/brief/2026-11-01/insights/refresh").json()["error"]["code"] == "refresh_running"
    with Store(store_path) as s:
        s.set_setting("insights_refreshing:2026-11-01", "2026-11-03T08:00:00Z")  # stale: a crashed refresh
    assert brief(c, "2026-11-01")["insights"]["status"] == "ok"
    assert c.post("/api/v1/brief/2026-11-01/insights/refresh").status_code == 200
    with Store(store_path) as s:
        assert s.setting("insights_refreshing:2026-11-01") == ""  # cleared after the refresh


def test_a_scheduled_item_carries_its_source_date_while_it_is_in_the_future(env, tmp_path):
    """C2 follow-up: published_at stays the discovery time; the UI says "scheduled for <date> per source" from
    scheduled_for, which is set only while the source's date is still ahead of now."""
    c, store_path = env
    it = c.get("/api/v1/items/fut").json()["item"]  # NOW is 3 Nov: the source's 2 Nov 05:00Z has passed
    assert it["published_at_source"] == "2026-11-02T05:00:00Z" and it["scheduled_for"] is None
    early = TestClient(create_app(store_path=store_path, runs_dir=tmp_path / "runs", changes_path=tmp_path / "x.sqlite",
                                  cfg=CFG, now=lambda: datetime(2026, 11, 1, 9, tzinfo=UTC)))
    it = early.get("/api/v1/items/fut").json()["item"]
    assert it["published_at"] == "2026-11-01T04:00:00Z" and it["scheduled_for"] == "2026-11-02T05:00:00Z"
    listed = next(x for x in brief(early, "2026-11-01")["items"]["items"] if x["item_id"] == "fut")
    assert listed["scheduled_for"] == "2026-11-02T05:00:00Z"
    s5 = early.get("/api/v1/items/s5").json()["item"]
    assert s5["published_at_source"] is None and s5["scheduled_for"] is None


def test_held_items_the_ranker_never_scored_are_counted_as_unscored(env, tmp_path):
    """D49 review: a ranker outage holds items as model_failure with no score; they were counted as '<=2', which
    says nothing big is pending. They now have their own bucket, and never count as held_high."""
    c, store_path = env
    with Store(store_path) as s:
        s.add_items([raw("u1", f"{VETTED}u1", "Story u1", "2026-11-02T22:00:00Z", RUN5)], RUN5, START5)
        s.save_outputs(RUN5, "fp", [Classification(id="u1", competitor="github", category="Security", noise=False,
                                                   mentions_jfrog=False, confidence=0.9, method="llm")],
                       [Ranked(id="u1", raw_score=None, score=None, degraded=True, noise=False, reason="",
                               confidence=0.9)])
    summary = brief(c, "2026-11-03")["summary"]
    assert summary["held"] == 3 and summary["held_high"] == 1
    assert summary["held_by_preliminary_score"] == {"5": 1, "4": 0, "3": 1, "<=2": 0, "unscored": 1, "noise": 0}
    assert review(c, brief="2026-11-03")["total"] == summary["held"]


def test_an_insight_lists_its_cited_items_with_score_and_link(env):
    """D50: the generator reads scores 1-2 too, so a cited item may not be in the Brief; the card can still open it."""
    c, store_path = env
    gen = {**stored("ok"), "insights": [{"insight_id": "i0", "item_ids": ["s5", "s2", "gone"]}]}
    with Store(store_path) as s:
        s.set_setting("insights_enabled", "true")
        s.save_insights("2026-11-01", gen)
    [ins] = brief(c, "2026-11-01")["insights"]["items"]
    assert ins["item_ids"] == ["s5", "s2", "gone"]  # unchanged
    rows = {r["item_id"]: r for r in ins["cited_items"]}
    assert list(rows) == ["s5", "s2"]  # an id no longer in the store is left out
    assert (rows["s5"]["score"], rows["s5"]["in_brief"], rows["s5"]["status"]) == (5, True, "auto_published")
    assert (rows["s2"]["score"], rows["s2"]["in_brief"]) == (2, False)  # scored 2: not listed, still linked
    assert rows["s2"]["url"] == f"{VETTED}s2" and rows["s2"]["title"] == "Story s2"
