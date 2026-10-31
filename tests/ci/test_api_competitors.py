"""Competitors screen and changed-cell review through the API (D20, D31, D36, D9/D13), offline."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from ci.api.app import create_app
from ci.changes.diff import Cell, CellStore, ChangeItem
from ci.classify import Classification
from ci.rank import Ranked
from ci.store import Store
from tests.ci.test_api import CFG, NOW, RUN1, START1, build, raw
from tests.ci.test_dedupe import fake_embed

T_OLD, T_NEW = datetime(2026, 10, 25, tzinfo=UTC), datetime(2026, 10, 30, 12, tzinfo=UTC)


def cell(comp, axis, value, as_of=T_OLD, **kw):
    return Cell(**{"competitor": comp, "axis": axis, "value": value, "evidence": f"quote: {value}", "confidence": 0.9,
                   "source_url": f"https://{comp}.example/{axis}", "page_key": "p", "as_of": as_of,
                   "checked_at": as_of, **kw})


@pytest.fixture
def env(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    with Store(store_path) as s:  # a deal: Funding/M&A/Partnerships is held at every level (D34)
        s.add_items([raw("deal", "https://www.theregister.com/deal", "GitHub acquires a startup",
                         "2026-10-29T09:00:00Z", RUN1)], RUN1, START1)
        s.save_outputs(RUN1, "fp", [Classification(id="deal", competitor="github",
                                                   category="Funding/M&A/Partnerships", noise=False,
                                                   mentions_jfrog=False, confidence=0.9, method="llm")],
                       [Ranked(id="deal", raw_score=5, score=5, reason="r", confidence=0.9)])
    changes = tmp_path / "changes.sqlite"
    cs = CellStore(changes)
    cs.put(cell("jfrog", "security_scanning", "Xray SCA with Contextual Analysis"), "r1", "baseline")
    cs.put(cell("github", "package_coverage", "not stated", confidence=0.0), "r1", "baseline")
    old = cell("github", "security_scanning", "CodeQL and Dependabot")
    cs.put(old, "r1", "baseline")
    new = cell("github", "security_scanning", "CodeQL, Dependabot and AI Scan", as_of=T_NEW)
    cs.put(new, "r2", "changed", ChangeItem(
        id="chg1", run_id="r2", competitor="github", axis="security_scanning", axis_label="Security scanning",
        page_key="p", page_url="https://github.example/sec", page_type="product", old_value=old.value,
        new_value=new.value, old_evidence=old.evidence, new_evidence=new.evidence, old_confidence=0.9,
        new_confidence=0.9, old_as_of=T_OLD, new_as_of=T_NEW, diff="-a\n+b", reason="r"))
    cs.close()
    app = create_app(store_path=store_path, runs_dir=runs_dir, changes_path=changes, labels_out=tmp_path / "l.jsonl",
                     split_path=split, cfg=CFG, now=lambda: NOW, embed_fn=fake_embed)
    return TestClient(app), store_path, changes


def cards(c, **params):
    return {x["key"]: x for x in c.get("/api/v1/competitors", params=params).json()["items"]}


def test_cards_count_by_discovery_time_published_only(env):
    c, _, _ = env
    gh = cards(c)["github"]
    assert gh["items_today"] == 1  # new2, in the Brief of Oct 31
    assert gh["items_7d"] == 3  # pub1, new2, and "late" (published Oct 20, found Oct 30): discovery time counts
    assert (gh["items_prev_7d"], gh["trend"]["direction"]) == (0, "up")
    assert gh["threat"] == 4 and gh["top_item"]["item_id"] == "pub1"
    assert (gh["pending_review"], gh["pending_max_score"]) == (3, 5)  # uv, uv4 (unvetted) and the deal
    assert {m["category"] for m in gh["category_mix"]} == {"Security", "Product & Features", "AI & Agents"}
    assert (gh["tracked_changes"], gh["head_to_head_changes"]) == (1, 1)
    assert cards(c)["snyk"]["pending_review"] == 1 and cards(c)["industry"]["tracked_changes"] is None
    assert c.get("/api/v1/competitors").json()["counted_by"] == "discovered_at"


def test_deals_block_lists_the_category_as_is_with_status(env):
    c, _, _ = env
    deals = c.get("/api/v1/competitors").json()["deals"]
    assert deals["total"] == 1 and deals["items"][0]["item_id"] == "deal"
    assert deals["items"][0]["status"] == "awaiting_review"  # M&A is held at every level until approved


def test_profile_head_to_head_states_and_change(env):
    c, _, _ = env
    p = c.get("/api/v1/competitors/github").json()
    axes = {a["axis"]: a for a in p["head_to_head"]["axes"]}
    assert len(axes) == 7
    sec = axes["security_scanning"]
    assert sec["competitor"]["value"] == "CodeQL, Dependabot and AI Scan" and sec["changed"] is True
    assert sec["competitor"]["change"]["status"] == "awaiting_review"
    assert sec["jfrog"]["value"] == "Xray SCA with Contextual Analysis"
    pc = axes["package_coverage"]["competitor"]
    assert (pc["state"], pc["value"]) == ("not_stated", None)
    assert axes["pricing_model"]["competitor"]["state"] == "not_tracked"
    assert c.get("/api/v1/competitors/industry").json()["head_to_head"] is None
    assert c.get("/api/v1/competitors/jetbrains").status_code == 404


def test_activity_is_by_publication_day_and_latest_items_are_published_only(env):
    c, _, _ = env
    p = c.get("/api/v1/competitors/github").json()
    series = {x["date"]: x for x in p["activity"]["series"]}
    assert len(series) == 30 and series["2026-10-20"]["items"] == 1  # "late" sits on the day it was published
    assert {x["item_id"] for x in p["latest_items"]["items"]} == {"pub1", "late", "new2"}
    assert [d["item_id"] for d in p["deals"]] == ["deal"]


def test_review_lists_the_changed_cell_until_it_is_decided(env):
    c, store_path, changes = env
    q = c.get("/api/v1/review", params={"kind": "change"}).json()
    assert [x["change_id"] for x in q["items"]] == ["chg1"] and q["counts_by_reason"]["changed_cell"] == 1
    r = c.post("/api/v1/changes/chg1/dismiss", json={"reason": "wrong_extraction"}).json()
    assert r["status"] == "dismissed" and r["cell"]["value"] == "CodeQL and Dependabot"  # the old value is back
    assert c.get("/api/v1/review", params={"kind": "change"}).json()["total"] == 0
    assert c.post("/api/v1/changes/chg1/approve").status_code == 409  # already decided
    hist = c.get("/api/v1/competitors/github/cells/security_scanning/history").json()["items"]
    assert [h["event"] for h in hist] == ["baseline", "changed", "dismissed"]
    with Store(store_path) as s:
        assert [(a["target_kind"], a["action"]) for a in s.actions()] == [("change", "dismiss")]


def test_approve_and_edit_a_changed_cell(env):
    c, _, changes = env
    assert c.patch("/api/v1/changes/chg1", json={"value": " "}).status_code == 422
    r = c.patch("/api/v1/changes/chg1", json={"value": "CodeQL, Dependabot, AI Scan (preview)"}).json()
    assert r["status"] == "edited" and r["cell"]["value"] == "CodeQL, Dependabot, AI Scan (preview)"
    assert c.post("/api/v1/changes/nope/approve").status_code == 404
    assert c.post("/api/v1/changes/chg1/dismiss", json={"reason": "bored"}).status_code == 422
