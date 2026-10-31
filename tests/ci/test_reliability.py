"""Reliability check of a daily run (D41): every held item + a fixed-seed sample of auto-published ones; answers in
the review file, counted with n. Offline."""
from datetime import UTC, datetime

import pytest
import yaml

from ci import reliability
from ci.classify import Classification
from ci.rank import Ranked
from ci.store import Store
from tests.ci.test_api import RUN2, build, raw

START2 = "2026-10-31T04:00:00+00:00"
MORNING = datetime(2026, 10, 31, 6, 30, tzinfo=UTC)


@pytest.fixture
def store(tmp_path, monkeypatch):
    store_path, _, _ = build(tmp_path)
    rows = [raw(f"auto{n:02d}", f"https://www.theregister.com/{n}", f"Story {n}", "2026-10-31T01:00:00Z", RUN2)
            for n in range(25)]
    rows += [raw("held1", "https://gbhackers.com/h", "Aggregator story", "2026-10-31T01:00:00Z", RUN2)]
    stock = raw("stock1", "https://finance.example.com/s", "GitLab Reaches a Fresh 52-Week High",
                "2026-10-31T01:00:00Z", RUN2)
    with Store(store_path) as s:
        s.add_items(rows + [stock], RUN2, START2)
        cls = [Classification(id=r["id"], competitor="github", category="Security", noise=False, mentions_jfrog=False,
                              confidence=0.9, method="llm") for r in rows]
        cls.append(Classification(id="stock1", competitor="gitlab", category=None, noise=True, mentions_jfrog=False,
                                  confidence=0.9, method="llm", shadow_prefilter="stock chatter: 52-week high/low"))
        s.save_outputs(RUN2, "fp", cls, [Ranked(id=r["id"], raw_score=3, score=3, reason="r", confidence=0.9)
                                         for r in rows] + [Ranked(id="stock1", raw_score=None, score=None, noise=True,
                                                                  reason="noise", confidence=0.9)])
    monkeypatch.setattr(reliability.ci_config, "load", lambda: reliability.ci_config.CIConfig(competitors=[]))
    return store_path


def test_make_takes_every_held_item_and_a_fixed_seed_sample(store, tmp_path):
    path = reliability.make(store_path=store, out_dir=tmp_path / "reviews", now=MORNING)
    data = yaml.safe_load(path.read_text())
    groups = [x["group"] for x in data["items"]]
    assert groups.count("held") == 1 and groups.count("auto") == 20 and data["auto_published_total"] == 26
    held = next(x for x in data["items"] if x["group"] == "held")
    assert held["id"] == "held1" and held["held_for"] == ["unvetted_source"]
    assert held["shown"] == {"competitor": "github", "category": "Security", "score": 3}
    assert all(x["answer"] == {"competitor": None, "category": None, "score": None} for x in data["items"])
    again = reliability.make(store_path=store, out_dir=tmp_path / "again", now=MORNING)
    assert [x["id"] for x in yaml.safe_load(again.read_text())["items"]] == [x["id"] for x in data["items"]]
    with pytest.raises(SystemExit, match="not overwritten"):
        reliability.make(store_path=store, out_dir=tmp_path / "reviews", now=MORNING)


def test_make_says_when_there_is_no_daily_run_today(store, tmp_path):
    with pytest.raises(SystemExit, match="no daily run on 2026-11-02"):
        reliability.make(store_path=store, out_dir=tmp_path / "r", now=datetime(2026, 11, 2, 6, 30, tzinfo=UTC))


def test_score_counts_right_and_wrong_per_field_with_n(store, tmp_path):
    path = reliability.make(store_path=store, out_dir=tmp_path / "reviews", now=MORNING)
    data = yaml.safe_load(path.read_text())
    for n, x in enumerate(data["items"]):
        x["answer"] = {"competitor": "right", "category": "wrong" if n < 3 else "right", "score": None if n == 0
                       else "right"}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    res = reliability.score(path)
    g = res["groups"]["all"]
    assert g["items"] == 21 and g["competitor"] == {"right": 21, "wrong": 0, "n": 21, "unanswered": 0, "accuracy": 1.0}
    assert (g["category"]["right"], g["category"]["n"]) == (18, 21)
    assert (g["score"]["n"], g["score"]["unanswered"]) == (20, 1)
    assert len(res["wrong_items"]) == 3 and path.with_suffix(".results.json").exists()
    data["items"][0]["answer"]["score"] = "maybe"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(SystemExit, match="right, wrong or null"):
        reliability.score(path)


def test_the_shadow_prefilters_flags_are_listed_for_a_noise_answer_and_scored(store, tmp_path):
    path = reliability.make(store_path=store, out_dir=tmp_path / "reviews", now=MORNING)
    data = yaml.safe_load(path.read_text())
    assert data["prefilter"] == [{"id": "stock1", "title": "GitLab Reaches a Fresh 52-Week High",
                                  "url": "https://finance.example.com/s",
                                  "would_drop_because": "stock chatter: 52-week high/low", "classifier_noise": True,
                                  "status": "dropped", "noise": None}]
    assert "stock1" not in [x["id"] for x in data["items"]]  # noise is neither held nor auto-published
    data["prefilter"][0]["noise"] = "yes"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    p = reliability.score(path)["prefilter"]
    assert (p["flagged"], p["noise_yes"], p["n"], p["precision"], p["relevant_flagged"]) == (1, 1, 1, 1.0, [])


def test_the_briefs_insights_are_listed_one_row_per_claim_for_a_supported_answer(store, tmp_path):
    with Store(store) as s:  # an insight stored for the Brief of 2026-10-31 (the daily run's Israel date)
        s.save_insights("2026-10-31", {"generated_at": "2026-10-31T04:10:00+00:00", "trigger": "daily",
                                       "level": "strict", "status": "partial", "fingerprint": "ifp", "model": "m",
                                       "insights": [{"insight_id": "ins_2026-10-31_1", "pattern": "shared_threat",
                                                     "title": "Attacks on AI tooling", "claims": [
                                                         {"text": "Story 1 and 2 report attacks", "item_ids":
                                                          ["auto01", "auto02"], "quote": "q", "quote_item_id":
                                                          "auto01", "jfrog_quote": ""},
                                                         {"text": "JFrog Curation blocks this", "item_ids": ["auto03"],
                                                          "quote": "q2", "quote_item_id": "auto03",
                                                          "jfrog_quote": "blocks malicious"}]}]})
    path = reliability.make(store_path=store, out_dir=tmp_path / "reviews", now=MORNING)
    data = yaml.safe_load(path.read_text())
    assert data["insights_meta"]["status"] == "partial" and data["insights_meta"]["fingerprint"] == "ifp"
    rows = data["insights"]
    assert [(r["insight_id"], r["claim_no"]) for r in rows] == [("ins_2026-10-31_1", 1), ("ins_2026-10-31_1", 2)]
    assert [c["title"] for c in rows[0]["cited"]] == ["Story 1", "Story 2"] and rows[0]["supported"] is None
    assert rows[1]["jfrog_quote"] == "blocks malicious"
    rows[0]["supported"], rows[1]["supported"] = "yes", "no"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    res = reliability.score(path)["insights"]
    assert (res["supported"], res["unsupported"], res["n"], res["insights"]) == (1, 1, 2, 1)
    assert res["unsupported_claims"][0]["claim_no"] == 2


def test_no_insights_stored_gives_an_empty_section(store, tmp_path):
    data = yaml.safe_load(reliability.make(store_path=store, out_dir=tmp_path / "r", now=MORNING).read_text())
    assert data["insights"] == [] and data["insights_meta"]["status"] == "none stored"
