"""Ranker (D14) offline: the code adjustments (JFrog bonus, snippet cap, noise), tie-breaking and degraded answers."""
import pytest

from ci.classify import Classification
from ci.llm import FakeLLM, LLMError
from ci.rank import FALLBACK_SCORE, RUBRIC, SNIPPET_SCORE_CAP, Ranker, adjust


def _item(i, text_status="full", published_at="2026-10-29T10:00:00Z"):
    return {"id": f"id{i}", "title": f"Story {i}", "text": "body", "text_status": text_status,
            "published_at": published_at, "source": "google_news"}


def _cls(i, noise=False, jfrog=False, confidence=0.8):
    return Classification(id=f"id{i}", competitor="snyk", category="Security", noise=noise, mentions_jfrog=jfrog,
                          confidence=confidence, method="rules")


def _scores(mapping):
    """A responder giving each id in the batch the score in mapping (default 3)."""
    def respond(prompt, schema):
        ids = schema["properties"]["items"]["items"]["properties"]["id"]["enum"]
        return {"items": [{"id": i, "score": mapping.get(i, 3), "reason": f"why {i}"} for i in ids]}
    return respond


def test_rubric_is_verbatim_in_the_prompt():
    llm = FakeLLM(_scores({}))
    Ranker(llm).rank([_item(1)], [_cls(1)])
    prompt = llm.calls[0][0]
    assert RUBRIC in prompt
    assert "| 5 | Direct threat: acquisition, a head-on competing product, a direct comparison to JFrog |" in prompt


@pytest.mark.parametrize("raw,status,jfrog,noise,expected", [
    (3, "full", True, False, 4),    # bonus
    (5, "full", True, False, 5),    # bonus capped at 5
    (5, "snippet", False, False, SNIPPET_SCORE_CAP),  # snippet cap
    (4, "snippet", True, False, 4),  # bonus then cap
    (2, "snippet", True, False, 3),  # bonus below the cap survives
    (5, "full", True, True, 1),     # noise wins over everything
    (2, "partial", False, False, 2),  # partial text is not capped
])
def test_adjustments(raw, status, jfrog, noise, expected):
    score, _ = adjust(raw, {"text_status": status}, _cls(1, noise=noise, jfrog=jfrog))
    assert score == expected


def test_output_has_raw_and_final_score_and_reason():
    llm = FakeLLM(_scores({"id1": 4}))
    (r,) = Ranker(llm).rank([_item(1, text_status="snippet")], [_cls(1, jfrog=True)])
    assert (r.raw_score, r.score, r.reason) == (4, 4, "why id1")
    assert r.adjustments == ["+1 Mentions JFrog", "snippet cap 4"]


def test_noise_items_are_forced_to_1_without_an_llm_call():
    llm = FakeLLM(_scores({}))
    out = Ranker(llm).rank([_item(1), _item(2)], [_cls(1, noise=True, jfrog=True), _cls(2)])
    assert len(llm.calls) == 1
    ids = llm.calls[0][1]["properties"]["items"]["items"]["properties"]["id"]["enum"]
    assert ids == ["id2"]
    noise = next(r for r in out if r.id == "id1")
    assert (noise.raw_score, noise.score) == (None, 1)


def test_order_by_score_then_confidence_then_date():
    items = [_item(1, published_at="2026-10-28T00:00:00Z"), _item(2, published_at="2026-10-29T00:00:00Z"),
             _item(3, published_at="2026-10-27T00:00:00Z"), _item(4, published_at=None), _item(5)]
    cls = [_cls(1, confidence=0.7), _cls(2, confidence=0.7), _cls(3, confidence=0.9), _cls(4, confidence=0.7),
           _cls(5, confidence=0.1)]
    llm = FakeLLM(_scores({"id1": 3, "id2": 3, "id3": 3, "id4": 3, "id5": 5}))
    out = Ranker(llm).rank(items, cls)
    # 5 first on score; then 3 on confidence; then 2 (newer) before 1; undated 4 last
    assert [r.id for r in out] == ["id5", "id3", "id2", "id1", "id4"]


def test_batches_of_ten():
    llm = FakeLLM(_scores({}))
    Ranker(llm, batch_size=10).rank([_item(i) for i in range(21)], [_cls(i) for i in range(21)])
    assert len(llm.calls) == 3


@pytest.mark.parametrize("answer", [
    LLMError("down"), {"nope": 1}, {"items": []},
    {"items": [{"id": "id1", "score": 9, "reason": "x"}]},
    {"items": [{"id": "id1", "score": "high", "reason": "x"}]},
    {"items": [{"id": "invented", "score": 5, "reason": "x"}]},
])
def test_unusable_answer_falls_back_to_midpoint(answer):
    (r,) = Ranker(FakeLLM([answer])).rank([_item(1)], [_cls(1)])
    assert r.raw_score is None and r.score == FALLBACK_SCORE
    assert "unusable" in r.reason


def test_partial_answer_keeps_the_scores_it_has():
    answer = {"items": [{"id": "id1", "score": 5.0, "reason": "  head-on\n product "}]}
    out = {r.id: r for r in Ranker(FakeLLM([answer])).rank([_item(1), _item(2)], [_cls(1), _cls(2)])}
    assert (out["id1"].raw_score, out["id1"].reason) == (5, "head-on product")
    assert out["id2"].raw_score is None


def test_a_fallback_score_gets_no_jfrog_bonus():
    (r,) = Ranker(FakeLLM([{"items": []}])).rank([_item(1)], [_cls(1, jfrog=True)])
    assert r.fallback and (r.raw_score, r.score) == (None, FALLBACK_SCORE) and r.adjustments == []
    (ok,) = Ranker(FakeLLM(_scores({}))).rank([_item(1)], [_cls(1, jfrog=True)])
    assert not ok.fallback and ok.score == 4


@pytest.mark.parametrize("status,raw,review", [
    ("snippet", 4, True), ("snippet", 5, True), ("snippet", 3, False), ("full", 5, False), ("partial", 4, False)])
def test_snippet_item_scored_4_or_more_needs_review(status, raw, review):
    (r,) = Ranker(FakeLLM(_scores({"id1": raw}))).rank([_item(1, text_status=status)], [_cls(1)])
    assert r.needs_review is review
    assert r.review_reasons == (["snippet-only item scored >= 4"] if review else [])
