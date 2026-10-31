"""D32 output validation, offline: every model answer row and every final output is checked against the config lists;
anything else is rejected, logged with the item id and the reason, and routed to review."""
from ci import validate
from ci.classify import CATEGORIES, Classification
from ci.config import CIConfig
from ci.llm import FakeLLM
from ci.rank import Ranked

CFG = CIConfig(window_days=7, competitors=[])
CLS_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string", "enum": ["a", "b"]},
    "competitor": {"type": "string", "enum": ["github", "none"]},
    "category": {"type": "string", "enum": CATEGORIES},
    "noise": {"type": "boolean"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["id", "competitor", "category", "noise", "confidence"]}}}}
RANK_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "string", "enum": ["a", "b"]},
    "score": {"type": "integer", "minimum": 1, "maximum": 5},
    "reason": {"type": "string"}}, "required": ["id", "score", "reason"]}}}}


def ok_cls(i="a", **kw):
    return {"id": i, "competitor": "github", "category": "Security", "noise": False, "confidence": 0.9, **kw}


def test_valid_answer_has_no_rejections():
    assert validate.check_answer(CLS_SCHEMA, {"items": [ok_cls("a"), ok_cls("b")]}, "classifier") == []


def test_competitor_category_and_noise_outside_the_lists_are_rejected():
    rows = [ok_cls("a", competitor="jetbrains"), ok_cls("b", category="Gossip", noise="yes")]
    got = validate.check_answer(CLS_SCHEMA, {"items": rows}, "classifier")
    assert [(r.item_id, r.stage) for r in got] == [("a", "classifier"), ("b", "classifier")]
    assert "competitor 'jetbrains' not in" in got[0].reason
    assert "category 'Gossip' not in" in got[1].reason and "noise 'yes'" in got[1].reason


def test_invented_duplicate_and_missing_ids_are_rejected():
    rows = [ok_cls("a"), ok_cls("a"), ok_cls("zzz")]
    got = {(r.item_id, r.reason) for r in validate.check_answer(CLS_SCHEMA, {"items": rows}, "classifier")}
    assert ("zzz", "unknown item id (not in this batch)") in got
    assert ("a", "duplicate answer for this id") in got
    assert ("b", "no answer for this id") in got


def test_score_outside_1_to_5_is_rejected():
    rows = [{"id": "a", "score": 7, "reason": "x"}, {"id": "b", "score": 3.5, "reason": "x"}]
    got = validate.check_answer(RANK_SCHEMA, {"items": rows}, "ranker")
    assert [r.item_id for r in got] == ["a", "b"]
    assert "score 7 outside 1-5" in got[0].reason and "score 3.5 is not an integer" in got[1].reason


def test_unusable_answer_rejects_the_whole_batch():
    got = validate.check_answer(RANK_SCHEMA, {"nope": 1}, "ranker")
    assert {r.item_id for r in got} == {"a", "b"} and all("no items list" in r.reason for r in got)


def test_validating_llm_records_and_passes_the_answer_through():
    inner = FakeLLM(lambda p, s: {"items": [ok_cls("a", competitor="jetbrains"), ok_cls("b")]})
    llm = validate.ValidatingLLM(inner)
    answer = llm.complete("prompt", CLS_SCHEMA)
    assert len(answer["items"]) == 2  # the classifier still sees the answer and falls back on its own
    assert [(r.item_id, r.stage) for r in llm.rejections] == [("a", "classifier")]


def cls(i, **kw):
    base = {"id": i, "competitor": "none", "category": "Security", "noise": False, "mentions_jfrog": False,
            "confidence": 0.9, "method": "llm"}
    return Classification(**{**base, **kw})


def rk(i, score=3, **kw):
    return Ranked(**{"id": i, "raw_score": score, "score": score, "reason": "r", "confidence": 0.9, **kw})


def test_final_outputs_checked_against_config_lists():
    outs = validate.check_outputs(
        {"a", "b", "c", "d"}, CFG,
        [cls("a"), cls("b", competitor="jetbrains"), cls("c", category=None), cls("x")],
        [rk("a"), rk("b"), rk("c", score=9), rk("x")])
    reasons = {(r.item_id, r.reason) for r in outs}
    assert ("b", "competitor 'jetbrains' not in the config list") in reasons
    assert ("c", "category None not in the category list") in reasons
    assert ("c", "score 9 is neither 1-5 nor noise") in reasons
    assert ("x", "unknown item id (not sent to the model in this run)") in reasons
    assert ("d", "no classification") in reasons and ("d", "no ranking") in reasons
    assert not any(i == "a" for i, _ in reasons)


def test_noise_has_no_score_and_degraded_outputs_are_already_in_review():
    outs = validate.check_outputs(
        {"n", "m", "g"}, CFG,
        [cls("n", noise=True, category=None), cls("m", noise=True), cls("g", degraded=True, category=None,
                                                                        method="fallback", needs_review=True)],
        [rk("n", score=None, raw_score=None, noise=True), rk("m", score=2, noise=True),
         rk("g", score=None, raw_score=None, degraded=True, needs_review=True)])
    assert {(r.item_id, r.reason) for r in outs} == {("m", "noise item has score 2; noise has no score")}


def test_route_to_review_marks_both_outputs():
    rej = [validate.Rejection("a", "classifier", "competitor 'jetbrains' not in the config list")]
    c, r = validate.route_to_review(rej, [cls("a"), cls("b")], [rk("a"), rk("b")])
    assert c[0].needs_review and "invalid output" in c[0].review_reason and not c[1].needs_review
    assert r[0].needs_review and r[0].review_reasons[-1].startswith("invalid output (classifier)")
    assert not r[1].needs_review
