"""The CI API v1 (Brief, Review, Log, actions, Trust this source) on a store built by a fixture, offline."""
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ci import insights
from ci.api.app import create_app
from ci.classify import Classification
from ci.config import CIConfig, Competitor
from ci.llm import FakeLLM
from ci.rank import Ranked
from ci.store import Store
from tests.ci.test_dedupe import fake_embed

CFG = CIConfig(competitors=[Competitor(key="github", name="GitHub"), Competitor(key="snyk", name="Snyk"),
                            Competitor(key="industry", name="Industry")])
RUN1, START1 = "20261030T1312Z-aaaaaa", "2026-10-30T13:12:00+00:00"  # Brief 2026-10-30 (import)
RUN2, START2 = "20261031T0400Z-bbbbbb", "2026-10-31T04:00:00+00:00"  # Brief 2026-10-31 (daily)
NOW = datetime(2026, 10, 31, 9, tzinfo=UTC)
LONG = "Lorem ipsum dolor sit amet " * 40  # 1080 chars: the API must cut it to an excerpt


def raw(item_id, url, title, published, run, competitor="github", text=LONG):
    return {"id": item_id, "url": url, "source": "google_news", "competitor": competitor, "title": title,
            "published_at": published, "run_id": run, "text": text, "text_status": "full", "date_precision": "time",
            "publisher": "", "url_resolved": True}


# item_id: (url, title, published, run, category, score, noise, mentions_jfrog)
ITEMS = {
    "pub1": ("https://www.theregister.com/a", "GitHub ships firewall", "2026-10-30T10:00:00Z", RUN1, "Security", 4,
             False, False),
    "late": ("https://www.theregister.com/b", "Old changelog found late", "2026-10-20T00:00:00Z", RUN1,
             "Product & Features", 3, False, False),
    "uv": ("https://gbhackers.com/x", "Aggregator story", "2026-10-30T08:00:00Z", RUN1, "Security", 3, False, False),
    "uv4": ("https://gbhackers.com/y", "Aggregator big story", "2026-10-30T09:00:00Z", RUN1, "Security", 4, False,
            False),
    "jf": ("https://www.theregister.com/c", "Snyk compares itself to JFrog", "2026-10-30T07:00:00Z", RUN1,
           "Customers & Market", 3, False, True),
    "noise": ("https://finance.example.com/n", "Stock price target raised", "2026-10-30T06:00:00Z", RUN1, None,
              None, True, False),
    "new2": ("https://www.theregister.com/d", "Copilot agents GA", "2026-10-31T02:00:00Z", RUN2, "AI & Agents", 3,
             False, False),
}


def build(tmp_path):
    store_path, runs_dir = tmp_path / "ci.sqlite", tmp_path / "runs"
    runs_dir.mkdir()
    with Store(store_path) as s:
        for run, start, kind in ((RUN1, START1, "import"), (RUN2, START2, "daily")):
            s.start_run(run, kind, start, "fp", "fake")
            s.finish_run(run, "ok", {})
            rows = [raw(i, u, t, p, r, "snyk" if i == "jf" else "github")
                    for i, (u, t, p, r, *_rest) in ITEMS.items() if r == run]
            if run == RUN1:
                rows.append(raw("held_out", "https://www.theregister.com/t", "Test split story",
                                "2026-10-30T05:00:00Z", RUN1))
            s.add_items(rows, run, start)
            cls, rk = [], []
            for i, (_, _, _, r, cat, score, noise, jf) in ITEMS.items():
                if r != run:
                    continue
                cls.append(Classification(id=i, competitor="snyk" if i == "jf" else "github", category=cat,
                                          noise=noise, mentions_jfrog=jf, confidence=0.9, method="llm"))
                rk.append(Ranked(id=i, raw_score=score, score=score, noise=noise, reason="r",
                                 why_it_matters="w", confidence=0.9))
            s.save_outputs(run, "fp", cls, rk)
        s.save_skips(RUN1, {"held_out": "golden-set test split: no prediction until after the test eval"})
    (runs_dir / f"{RUN1}.dropped.jsonl").write_text(json.dumps({
        "id": "dup1", "run_id": RUN1, "url": "https://www.theregister.com/a?utm=1", "title": "GitHub ships firewall",
        "source": "google_news", "competitor": "github", "published_at": "2026-10-30T10:00:00Z",
        "collected_at": START1, "drop_stage": "url_dedupe", "drop_reason": "URL seen", "duplicate_of": "pub1"}) + "\n")
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"version": 1, "sides": {"held_out": "test", "pub1": "train"}}))
    return store_path, runs_dir, split


@pytest.fixture
def env(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    labels = tmp_path / "analyst_labels.jsonl"
    app = create_app(store_path=store_path, runs_dir=runs_dir, changes_path=tmp_path / "none.sqlite",
                     labels_out=labels, split_path=split, cfg=CFG, now=lambda: NOW,
                     insights_llm=lambda: FakeLLM(lambda p, s: {"insights": []}), embed_fn=fake_embed)
    return TestClient(app), store_path, labels


def ids(rows):
    return [r["item_id"] for r in rows]


def test_meta(env):
    c, _, _ = env
    m = c.get("/api/v1/meta").json()
    assert m["level"] == "strict" and m["latest_brief_date"] == "2026-10-31" and m["insights_enabled"] is False
    assert [x["key"] for x in m["competitors"]] == ["github", "snyk", "industry"] and m["meta"]["mode"] == "live"
    assert "snapshot" not in m["meta"]  # the demo marker only exists in demo mode


def test_brief_window_badges_order_and_published_only(env):
    c, _, _ = env
    b = c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()
    assert b["window"]["anchor"] == "2026-10-30T13:12:00Z" and b["window"]["prev_anchor"] == "2026-10-29T13:12:00Z"
    assert b["window"]["anchor_kind"] == "import"  # the backfill Brief: the UI labels it and hides "Found late"
    items = b["items"]["items"]
    assert ids(items) == ["pub1", "late"]  # uv, uv4 (unvetted) and jf held at strict; noise dropped; test split out
    assert [x["badge"] for x in items] == ["new", "late"]
    assert items[1]["published_at"] == "2026-10-20T00:00:00Z" and items[1]["discovery_lag_hours"] == 253.2
    assert b["counts"]["found_late"] == 1 and b["counts"]["awaiting_review"] == 3
    assert b["insights"] == {"status": "disabled", "generator_status": None, "items": [], "enabled": False,
                             "rejected": 0}
    assert len(b["intensity"]["series"]) == 14 and b["intensity"]["series"][-1] == {"date": "2026-10-30",
                                                                                     "score": 7, "items": 2}


def test_brief_since_previous_brief_and_kpis_against_it(env):
    c, _, _ = env
    b = c.get("/api/v1/brief").json()
    assert b["date"] == "2026-10-31"
    assert b["window"]["prev_anchor"] == "2026-10-30T13:12:00Z" and b["window"]["hours"] == 14.8
    assert b["window"]["anchor_kind"] == "daily"
    assert ids(b["items"]["items"]) == ["new2"]
    assert {k["key"]: (k["value"], k["prev"]) for k in b["kpis"]}["items"] == (1, 2)


def test_brief_for_a_day_without_a_run(env):
    c, _, _ = env
    assert c.get("/api/v1/brief", params={"date": "2026-10-25"}).json()["status"] == "missing"
    rows = c.get("/api/v1/briefs").json()["items"]
    assert [(r["date"], r["anchor_kind"]) for r in rows] == [("2026-10-31", "daily"), ("2026-10-30", "import")]


def test_no_article_text_leaves_the_api(env):
    c, _, _ = env
    body = c.get("/api/v1/brief", params={"date": "2026-10-30"}).text
    assert LONG[:400] not in body and '"text"' not in body
    for it in c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()["items"]["items"]:
        assert len(it["excerpt"]) <= 280


def test_review_levels_reasons_and_order(env):
    c, _, _ = env
    r = c.get("/api/v1/review").json()
    assert r["level"] == "strict" and r["total"] == 3
    assert ids([x["item"] for x in r["items"]])[0] == "jf"  # held at every level comes first
    assert r["counts_by_reason"] == {"unvetted_source": 2, "mentions_jfrog": 1}
    assert {x["level"]: (x["held"], x["n"]) for x in r["levels"]} == {
        "strict": (3, 6), "balanced": (2, 6), "relaxed": (1, 6)}
    assert c.get("/api/v1/review", params={"level": "balanced"}).json()["total"] == 2
    assert c.get("/api/v1/review", params={"reason": "mentions_jfrog"}).json()["total"] == 1


def test_changing_the_level_reroutes_at_once(env):
    c, _, _ = env
    assert c.put("/api/v1/settings/autonomy-level", json={"level": "relaxed"}).json()["level"] == "relaxed"
    b = c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()
    assert set(ids(b["items"]["items"])) == {"pub1", "late", "uv", "uv4"}
    assert c.put("/api/v1/settings/autonomy-level", json={"level": "lenient"}).status_code == 422


def test_approve_adds_a_held_item_to_the_brief_and_bad_transitions_are_409(env):
    c, _, _ = env
    r = c.post("/api/v1/items/jf/approve", json={"note": "checked"}).json()
    assert r["status"] == "approved" and r["version"] == 1 and r["measures"] == "confirmed"
    assert "jf" in ids(c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()["items"]["items"])
    bad = c.post("/api/v1/items/pub1/approve")
    assert bad.status_code == 409 and bad.json()["error"]["details"]["status"] == "auto_published"
    assert c.post("/api/v1/items/noise/approve").status_code == 409
    assert c.post("/api/v1/items/nope/approve").json()["error"]["code"] == "not_found"


def test_dismiss_flag_unflag_and_if_match(env):
    c, store_path, _ = env
    r = c.post("/api/v1/items/pub1/dismiss", json={"reason": "wrong_competitor"}).json()
    assert r["status"] == "dismissed" and r["measures"] == "classifier"
    assert "pub1" not in ids(c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()["items"]["items"])
    assert c.post("/api/v1/items/late/dismiss", json={"reason": "bored"}).status_code == 422
    f = c.post("/api/v1/items/late/flag").json()
    assert f["status"] == "flagged" and f["flagged"] is True
    assert c.post("/api/v1/items/late/flag", headers={"If-Match": "0"}).status_code == 409  # stale version
    assert c.delete("/api/v1/items/late/flag", headers={"If-Match": "1"}).json()["status"] == "auto_published"
    with Store(store_path) as s:
        assert [a["action"] for a in s.actions()] == ["dismiss", "flag", "unflag"]


def test_edit_validates_against_the_config_and_writes_a_candidate_not_a_label(env):
    c, _, labels = env
    assert c.patch("/api/v1/items/late", json={"competitor": "jetbrains"}).status_code == 422
    assert c.patch("/api/v1/items/late", json={}).status_code == 400
    assert c.patch("/api/v1/items/late", json={"score": 9}).status_code == 422
    r = c.patch("/api/v1/items/late", json={"category": "Security", "note": "it is"}).json()
    assert r["action"] == "edit"
    item = c.get("/api/v1/items/late").json()["item"]
    assert item["category"] == "Security" and item["edited"] == {"category": "Security"}
    row = json.loads(labels.read_text().splitlines()[0])
    assert row["id"] == "late" and row["source"] == "analyst" and row["category"] == "Security"
    assert c.patch("/api/v1/items/held_out", json={"score": 3}).status_code == 409  # test split: no edits


def test_trust_this_source_releases_and_can_be_undone(env):
    c, _, _ = env
    r = c.post("/api/v1/sources/trust", json={"host": "www.GBHackers.com", "from_item_id": "uv"}).json()
    assert r["host"] == "gbhackers.com" and r["released"]["item_ids"] == ["uv", "uv4"]
    assert c.get("/api/v1/review").json()["total"] == 1
    assert c.post("/api/v1/sources/trust", json={"host": "gbhackers.com"}).status_code == 409
    assert c.post("/api/v1/sources/trust", json={"host": "theregister.com"}).status_code == 409  # in the yaml
    assert c.post("/api/v1/sources/trust", json={"host": "github.com"}).status_code == 409  # vetted per org (D49)
    assert c.post("/api/v1/sources/trust", json={"host": "gitlab.com"}).status_code == 409  # vetted per org (D53)
    assert c.post("/api/v1/sources/trust", json={"host": "gist.github.com"}).status_code == 409  # never vetted
    assert c.post("/api/v1/sources/trust", json={"host": "not a host"}).status_code == 422
    assert {"host": "gbhackers.com", "group": "trusted"}.items() <= next(
        x for x in c.get("/api/v1/sources").json()["items"] if x["host"] == "gbhackers.com").items()
    assert c.delete("/api/v1/sources/trust/gbhackers.com").json()["removed"] is True
    assert c.get("/api/v1/review").json()["total"] == 3
    assert c.delete("/api/v1/sources/trust/theregister.com").status_code == 409
    assert c.delete("/api/v1/sources/trust/example.org").status_code == 404


def test_trust_is_suggested_after_three_approvals_and_no_dismissals(env):
    c, store_path, _ = env
    with Store(store_path) as s:
        s.add_items([raw(f"g{n}", f"https://gbhackers.com/{n}", f"t{n}", "2026-10-30T01:00:00Z", RUN1)
                     for n in range(3)], RUN1, START1)
        for n in range(3):
            s.apply_item_action(f"g{n}", "approve", {"decision": "approved"})
    rows = c.get("/api/v1/sources", params={"kind": "unvetted"}).json()["items"]
    gb = next(x for x in rows if x["host"] == "gbhackers.com")
    assert gb["approved"] == 3 and gb["suggest"] is True
    assert [x["host"] for x in c.get("/api/v1/sources", params={"kind": "suggested"}).json()["items"]] == \
        ["gbhackers.com"]


def test_log_has_every_sighting_and_every_drop_with_its_stage(env):
    c, _, _ = env
    log = c.get("/api/v1/log", params={"limit": 200}).json()
    rows = {r["item_id"]: r for r in log["items"]}
    assert len(rows) == 9 and log["total"] == 9
    assert (rows["held_out"]["status"], rows["held_out"]["stage"]) == ("held_out", "test_skip")
    assert (rows["noise"]["status"], rows["noise"]["stage"]) == ("dropped", "classify")
    assert (rows["dup1"]["stage"], rows["dup1"]["duplicate_of"]) == ("url_dedupe", "pub1")
    assert (rows["uv"]["status"], rows["uv"]["stage"], rows["uv"]["reason"]) == \
        ("awaiting_review", "route", "unvetted_source")
    assert log["counts"]["status"]["dropped"] == 2
    only = c.get("/api/v1/log", params={"status": "dropped", "stage": "url_dedupe"}).json()
    assert ids(only["items"]) == ["dup1"] and only["counts"]["status"]["dropped"] == 2
    assert ids(c.get("/api/v1/log", params={"run_id": RUN2}).json()["items"]) == ["new2"]
    assert c.get("/api/v1/log", params={"limit": 0}).status_code == 400


def test_refresh_insights_is_off_until_enabled(env):
    c, store_path, _ = env
    r = c.post("/api/v1/brief/2026-10-30/insights/refresh")
    assert r.status_code == 409 and r.json()["error"]["code"] == "insights_disabled"
    with Store(store_path) as s:
        s.set_setting("insights_enabled", "true")
    r = c.post("/api/v1/brief/2026-10-30/insights/refresh").json()
    assert r["status"] in ("partial", "none")
    ins = c.get("/api/v1/brief", params={"date": "2026-10-30"}).json()["insights"]
    assert ins["trigger"] == "refresh" and ins["enabled"] is True and "insights" not in ins
    with Store(store_path) as s:  # D53: the generation records what it ran with
        meta = s.latest_insights("2026-10-30")["metadata"]
    assert meta["fingerprints"]["insights"] == insights.fingerprint() and meta["commit"]["sha"]


def test_errors_use_the_envelope(env):
    c, _, _ = env
    e = c.get("/api/v1/items/nope").json()
    assert e["error"]["code"] == "not_found" and "meta" in e
    assert c.get("/api/v1/review", params={"level": "lenient"}).json()["error"]["code"] == "validation_error"


def test_brief_list_filters(env):
    c, _, _ = env
    q = {"date": "2026-10-30"}
    assert ids(c.get("/api/v1/brief", params={**q, "badge": "late"}).json()["items"]["items"]) == ["late"]
    assert ids(c.get("/api/v1/brief", params={**q, "category": ["Security", "AI & Agents"]}).json()["items"]
               ["items"]) == ["pub1"]
    assert c.get("/api/v1/brief", params={**q, "competitor": "snyk"}).json()["items"]["total"] == 0
