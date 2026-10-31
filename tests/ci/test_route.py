"""Routing (D9, D34, D36): hold reasons per level, statuses, and the measured counts on the 14-day import."""
import json
from pathlib import Path

import pytest

from ci import route
from ci.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "routing_389e71.json"


def x(**kw):
    base = {"item_id": "i1", "url": "https://www.theregister.com/a", "noise": False, "category": "Security",
            "mentions_jfrog": False, "confidence": 0.9, "score": 3, "text_status": "full"}
    return route.RouteInput(**{**base, **kw})


def codes(item, level=None):
    rs = route.hold_reasons(item)
    return {r.code for r in rs if level is None or level in r.held_at}


def test_a_vetted_routine_item_is_published_at_every_level():
    for level in route.LEVELS:
        assert route.status(x(), level) == "auto_published"


@pytest.mark.parametrize(("score", "held_at"), [(3, {"strict"}), (4, {"strict", "balanced"})])
def test_unvetted_source_strict_always_balanced_only_at_score_4(score, held_at):
    item = x(url="https://gbhackers.com/a", score=score)
    assert {lv for lv in route.LEVELS if "unvetted_source" in codes(item, lv)} == held_at


def test_subdomain_of_a_vetted_host_is_vetted():
    assert "unvetted_source" not in codes(x(url="https://updates.snyk.io/x"))


@pytest.mark.parametrize("kw", [{"confidence": 0.79}, {"text_status": "snippet", "score": 4},
                                {"text_status": "junk", "score": 5}])
def test_low_confidence_teaser_and_junk_held_at_strict_and_balanced_not_relaxed(kw):
    item = x(**kw)
    assert route.status(item, "strict") == route.status(item, "balanced") == "awaiting_review"
    assert route.status(item, "relaxed") == "auto_published"


def test_boundaries_confidence_0_8_and_teaser_at_score_3_are_not_held():
    assert codes(x(confidence=0.8)) == set()
    assert codes(x(text_status="snippet", score=3)) == set()


@pytest.mark.parametrize(("kw", "code"), [
    ({"category": "Pricing & Packaging"}, "pricing"),
    ({"category": "Funding/M&A/Partnerships"}, "m_and_a"),
    ({"mentions_jfrog": True}, "mentions_jfrog"),
    ({"classifier_degraded": True}, "model_failure"),
    ({"ranker_degraded": True, "score": None}, "model_failure"),
    ({"rejections": ("classifier: competitor 'x' not in the config list",)}, "invalid_output"),
])
def test_always_held_reasons_hold_at_every_level(kw, code):
    item = x(**kw)
    assert code in codes(item, "relaxed")
    assert all(route.status(item, lv) == "awaiting_review" for lv in route.LEVELS)


def test_changed_cell_is_held_at_every_level():
    assert all(route.is_held(route.change_hold_reasons(), lv) for lv in route.LEVELS)


def test_noise_is_dropped_never_queued():
    item = x(noise=True, mentions_jfrog=True, url="https://gbhackers.com/a")
    assert route.hold_reasons(item) == []
    assert all(route.status(item, lv) == "dropped" for lv in route.LEVELS)


def test_analyst_decision_overrides_routing():
    item = x(mentions_jfrog=True)
    assert route.status(item, "strict", decision="approved") == "approved"
    assert route.status(x(), "relaxed", decision="dismissed") == "dismissed"
    with pytest.raises(ValueError):
        route.status(item, decision="maybe")
    with pytest.raises(ValueError):
        route.is_held([], "lenient")


def test_measured_counts_on_the_14_day_import():
    """D36 rules on the stored outputs of run 389e71 (n=228 non-noise of 256 classified): 88 / 31 / 12. Before Q-B
    added the teaser and junk holds, the same data gave 84 / 28 / 12 (D34); 87 / 31 / 12 before D49 vetted github.com
    per org, which holds the one third-party repo (github.com/cognitionai, score 3, Hacker News) at strict."""
    data = json.loads(FIXTURE.read_text())
    inputs = [route.RouteInput(**{**d, "rejections": tuple(d["rejections"])}) for d in data["items"]]
    assert len(inputs) == 256
    counts = route.level_counts(inputs)
    assert {lv: (c["held"], c["n"]) for lv, c in counts.items()} == {
        "strict": (88, 228), "balanced": (31, 228), "relaxed": (12, 228)}
    by = route.reason_counts(inputs)
    assert (by["unvetted_source"], by["pricing"], by["m_and_a"], by["mentions_jfrog"]) == (80, 3, 4, 5)
    assert by.get("low_confidence", 0) == 0 and by.get("model_failure", 0) == 0


def test_fixture_holds_no_article_text():
    data = json.loads(FIXTURE.read_text())
    assert all(set(d) <= set(route.RouteInput.__dataclass_fields__) for d in data["items"])
    def host_or_org(url: str) -> bool:  # host only, no path; github.com keeps its org segment (D49)
        return url.count("/") == 3 or (url.startswith("https://github.com/") and url.count("/") == 4)

    assert all(host_or_org(d["url"]) for d in data["items"])


def test_autonomy_level_setting_defaults_to_strict(tmp_path):
    with Store(tmp_path / "ci.sqlite") as s:
        assert s.autonomy_level() == "strict"
        s.set_autonomy_level("balanced")
        assert s.autonomy_level() == "balanced"
        with pytest.raises(ValueError):
            s.set_autonomy_level("lenient")
