"""Insight continuity (API layer only): each insight of a Brief against the previous Brief's insights, by stored
story_ids. Offline, no LLM call; ci/insights.py is not involved."""
from ci.api import service as svc
from ci.store import Store
from tests.ci.test_api_d44 import brief, env  # noqa: F401  (fixture)


def ins(insight_id, pattern, stories, title="t"):
    return {"insight_id": insight_id, "pattern": pattern, "story_ids": list(stories), "item_ids": [], "title": title,
            "claims": []}


PREV = [ins("p1", "competitor_momentum", "abc"), ins("p2", "shared_threat", "xyz"),
        ins("p3", "axis_convergence", "mn"), ins("p4", "competitor_momentum", "def")]


def test_new_continuing_and_strengthened():
    today = [ins("t1", "competitor_momentum", "ab"),  # 2 shared, nothing new
             ins("t2", "shared_threat", "xyzw"),  # 3 shared, 1 new story
             ins("t3", "axis_convergence", "mq"),  # only 1 shared: not enough
             ins("t4", "competitor_momentum", "uv")]  # nothing shared
    cont, prev = svc.insight_continuity(today, PREV, "2026-10-31")
    assert cont["t1"] == {"status": "continuing", "since": "2026-10-31", "new_stories": 0, "matched": ["p1"]}
    assert cont["t2"] == {"status": "strengthened", "since": "2026-10-31", "new_stories": 1, "matched": ["p2"]}
    assert cont["t3"]["status"] == "new" and cont["t4"] == {"status": "new", "since": None, "new_stories": None,
                                                              "matched": []}
    assert prev == {"date": "2026-10-31", "insights": 4, "unmatched": 2, "unmatched_ids": ["p3", "p4"]}


def test_two_previous_insights_matching_one_of_today():
    today = [ins("t1", "competitor_momentum", "abdeg")]  # shares 2 with p1 (a, b) and 2 with p4 (d, e)
    cont, prev = svc.insight_continuity(today, PREV, "2026-10-31")
    # new_stories counts against both matches together: only g is new (c and f are not cited today)
    assert cont["t1"] == {"status": "strengthened", "since": "2026-10-31", "new_stories": 1, "matched": ["p1", "p4"]}
    assert prev["unmatched"] == 2 and prev["unmatched_ids"] == ["p2", "p3"]  # both matches count as matched


def test_shared_stories_under_another_pattern_is_new():
    cont, prev = svc.insight_continuity([ins("t1", "shared_threat", "abc")], PREV, "2026-10-31")
    assert cont["t1"]["status"] == "new" and prev["unmatched"] == 4


def test_no_previous_brief_or_no_previous_insights():
    cont, prev = svc.insight_continuity([ins("t1", "shared_threat", "xyz")], [], None)
    assert cont["t1"]["status"] == "new" and prev == {"date": None, "insights": 0, "unmatched": 0,
                                                      "unmatched_ids": []}
    assert svc.insight_continuity([], PREV, "2026-10-31")[1]["unmatched"] == 4  # no insights today: none matched


def gen(at, insights):
    return {"generated_at": at, "trigger": "daily", "level": "strict", "status": "ok", "fingerprint": "f",
            "model": "m", "insights": insights, "rejected": []}


def test_the_brief_serves_continuity_per_insight_and_the_previous_side(env):  # noqa: F811
    c, store_path = env
    with Store(store_path) as s:
        s.save_insights("2026-11-02", gen("2026-11-02T04:05:00+00:00", PREV))
        s.save_insights("2026-11-03", gen("2026-11-03T04:05:00+00:00",
                                          [ins("t1", "competitor_momentum", "abdeg"), ins("t2", "shared_threat", "xy"),
                                           ins("t3", "axis_convergence", "q")]))
    b = brief(c, "2026-11-03")["insights"]
    assert {x["insight_id"]: x["continuity"]["status"] for x in b["items"]} == \
        {"t1": "strengthened", "t2": "continuing", "t3": "new"}
    assert b["items"][0]["continuity"] == {"status": "strengthened", "since": "2026-11-02", "new_stories": 1,
                                           "matched": ["p1", "p4"]}
    assert b["previous"] == {"date": "2026-11-02", "status": "ok", "insights": 4, "unmatched": 1,
                             "unmatched_ids": ["p3"]}
    first = brief(c, "2026-11-02")["insights"]  # the Brief before has no stored insights: everything is new
    assert all(x["continuity"]["status"] == "new" for x in first["items"])
    assert first["previous"] == {"date": "2026-11-01", "status": None, "insights": 0, "unmatched": 0,
                                 "unmatched_ids": []}
    with Store(store_path) as s:  # the stored generations are read, never changed
        assert [x["insight_id"] for x in s.latest_insights("2026-11-03")["insights"]] == ["t1", "t2", "t3"]
        assert "continuity" not in s.latest_insights("2026-11-03")["insights"][0]
