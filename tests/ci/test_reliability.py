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
    with Store(store_path) as s:
        s.add_items(rows, RUN2, START2)
        s.save_outputs(RUN2, "fp", [Classification(id=r["id"], competitor="github", category="Security", noise=False,
                                                   mentions_jfrog=False, confidence=0.9, method="llm") for r in rows],
                       [Ranked(id=r["id"], raw_score=3, score=3, reason="r", confidence=0.9) for r in rows])
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
