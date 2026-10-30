"""Ranker (PRD D14): the LLM scores importance 1-5 on the written rubric, then code adjusts and orders.

Adjustments, in order: +1 when the item mentions JFrog (capped at 5), a cap for items we only have a snippet of,
and noise forced to 1. Ties are broken by classifier confidence, then by date (newest first).
Noise items are never sent to the LLM: their score is 1 whatever it would say.
"""
import json
import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from ci.classify import Classification
from ci.llm import JsonLLM, LLMError

log = logging.getLogger(__name__)

BATCH_SIZE = 10
LLM_TEXT_CHARS = 2500
MIN_SCORE, MAX_SCORE = 1, 5
JFROG_BONUS = 1
SNIPPET_SCORE_CAP = 4  # an item we could only read a snippet of cannot score above this (Ofri, Oct 30: was 3)
SNIPPET_REVIEW_MIN = 4  # ...and at or above this it goes to review: a high score resting on a teaser needs a human
NOISE_SCORE = 1
FALLBACK_SCORE = 3  # when the LLM gave no usable score: the midpoint, so a failure neither buries nor promotes

# PRD "Item lifecycle", Importance (D14), verbatim
RUBRIC = """Importance (D14). 1–5, answering "how much does this change JFrog's competitive picture?"

| Score | Meaning |
| --- | --- |
| 5 | Direct threat: acquisition, a head-on competing product, a direct comparison to JFrog |
| 4 | Change on a head-to-head axis: pricing, an AI or MCP capability |
| 3 | Routine product update, or relevant industry news |
| 2 | Related, no competitive impact |
| 1 | Noise |"""


class Ranked(BaseModel):
    id: str
    raw_score: int | None  # the LLM's score; None for noise (not asked) or an unusable answer
    fallback: bool = False  # True when the LLM gave no usable score and FALLBACK_SCORE was used
    score: int  # after the code adjustments
    reason: str  # one line
    adjustments: list[str] = []
    needs_review: bool = False  # D9: routed to the analyst review queue whatever the autonomy threshold
    review_reasons: list[str] = []
    confidence: float  # the classifier's, used for tie-breaking
    published_at: datetime | None = None


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def adjust(raw: int, item: dict, cls: Classification, fallback: bool = False) -> tuple[int, list[str]]:
    """The code side of D14: bonus, snippet cap, noise. Returns the final score and what was applied.
    A fallback score gets no JFrog bonus: a failure never promotes an item."""
    if cls.noise:
        return NOISE_SCORE, [] if raw == NOISE_SCORE else [f"noise -> {NOISE_SCORE}"]
    score, notes = raw, []
    if cls.mentions_jfrog and score < MAX_SCORE and not fallback:
        score = min(MAX_SCORE, score + JFROG_BONUS)
        notes.append(f"+{JFROG_BONUS} Mentions JFrog")
    if item.get("text_status") == "snippet" and score > SNIPPET_SCORE_CAP:
        score = SNIPPET_SCORE_CAP
        notes.append(f"snippet cap {SNIPPET_SCORE_CAP}")
    return score, notes


# D9 forced-review rules, one (reason, predicate) per rule; the start of routing, kept explicit and small.
REVIEW_RULES = [
    ("snippet-only item scored >= 4",
     lambda item, cls, score: item.get("text_status") == "snippet" and score >= SNIPPET_REVIEW_MIN),
]


def review_reasons(item: dict, cls: Classification, score: int) -> list[str]:
    return [reason for reason, applies in REVIEW_RULES if applies(item, cls, score)]


def sort_key(r: Ranked):
    ts = r.published_at.timestamp() if r.published_at else float("-inf")
    return (-r.score, -r.confidence, -ts, r.id)


def order(ranked: list[Ranked]) -> list[Ranked]:
    """Highest score first; ties by classifier confidence, then newest; then id so the order is stable."""
    return sorted(ranked, key=sort_key)


class Ranker:
    def __init__(self, llm: JsonLLM, batch_size: int = BATCH_SIZE):
        self.llm = llm
        self.batch_size = batch_size

    @staticmethod
    def schema(ids: list[str]) -> dict:
        return {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "enum": ids},
                    "score": {"type": "integer", "minimum": MIN_SCORE, "maximum": MAX_SCORE},
                    "reason": {"type": "string"},
                },
                "required": ["id", "score", "reason"],
            }}},
            "required": ["items"],
        }

    @staticmethod
    def prompt(pairs: list[tuple[dict, Classification]]) -> str:
        payload = [{"id": it["id"], "competitor": c.competitor, "category": c.category, "source": it.get("source"),
                    "publisher": it.get("publisher") or "", "title": it.get("title") or "",
                    "text": (it.get("text") or "")[:LLM_TEXT_CHARS]} for it, c in pairs]
        return f"""You rank news items for JFrog's competitive-intelligence team.
JFrog sells a software supply chain platform: Artifactory (artifact and package repositories), Xray (security
scanning), Curation, and AI/MCP tooling. Score each item on this rubric:

{RUBRIC}

Score the content against the rubric only; code applies its own adjustments afterwards. For each id give the score
and a one-line reason (under 25 words) naming what drove it. Answer only about the ids given, once each.

Items (JSON):
{json.dumps(payload, ensure_ascii=False, indent=1)}
"""

    def _llm_scores(self, pairs: list[tuple[dict, Classification]]) -> dict[str, tuple[int | None, str]]:
        ids = [it["id"] for it, _ in pairs]
        try:
            answer = self.llm.complete(self.prompt(pairs), self.schema(ids))
            rows = answer.get("items") if isinstance(answer, dict) else None
            if not isinstance(rows, list):
                raise LLMError(f"no items list in answer: {str(answer)[:200]}")
        except Exception as e:  # one bad batch must not stop the run
            log.warning("ranker batch of %d failed: %s", len(pairs), e)
            return {}
        out: dict[str, tuple[int | None, str]] = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("id") not in ids or row["id"] in out:
                continue
            score, reason = row.get("score"), row.get("reason")
            if isinstance(score, float) and score.is_integer():
                score = int(score)
            if isinstance(score, bool) or not isinstance(score, int) or not MIN_SCORE <= score <= MAX_SCORE:
                continue
            reason = " ".join(str(reason or "").split())
            out[row["id"]] = (score, reason)
        return out

    def rank(self, items: list[dict], classifications: list[Classification]) -> list[Ranked]:
        """Ranked items, best first. classifications is matched to items by id."""
        by_id = {c.id: c for c in classifications}
        pairs = [(it, by_id[it["id"]]) for it in items]
        to_score = [(it, c) for it, c in pairs if not c.noise]
        scores: dict[str, tuple[int | None, str]] = {}
        for start in range(0, len(to_score), self.batch_size):
            scores.update(self._llm_scores(to_score[start:start + self.batch_size]))
        ranked = []
        for it, c in pairs:
            if c.noise:
                raw, reason = None, "classified as noise"
            elif it["id"] in scores:
                raw, reason = scores[it["id"]]
            else:
                raw, reason = None, "ranker answer unusable; midpoint score"
            fallback = raw is None and not c.noise
            score, notes = adjust(FALLBACK_SCORE if raw is None else raw, it, c, fallback=fallback)
            reasons = review_reasons(it, c, score)
            ranked.append(Ranked(id=it["id"], raw_score=raw, fallback=fallback, score=score,
                                 needs_review=bool(reasons), review_reasons=reasons,
                                 reason=reason or "(no reason given)", adjustments=notes, confidence=c.confidence,
                                 published_at=_as_datetime(it.get("published_at"))))
        return order(ranked)


def rank(items: list[dict], classifications: list[Classification], llm: JsonLLM) -> list[Ranked]:
    return Ranker(llm).rank(items, classifications)
