"""Ranker (PRD D14): the LLM scores importance 1-5 on the written rubric, then code adjusts and orders.

Adjustments, in order: +1 when the item mentions JFrog (capped at 5), a cap for items we only have a snippet of,
and noise forced to 1. Ties are broken by classifier confidence, then by date (newest first).
Noise items are never sent to the LLM: their score is 1 whatever it would say.
When the LLM fails for an item, it gets no score at all (score None, degraded, sent to review): a failure must never
look like a normal score. Degraded items sort after every scored one and are never auto-publishable.
"""
import json
import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from ci.classify import Classification, content_text
from ci.llm import JsonLLM, LLMError

log = logging.getLogger(__name__)

BATCH_SIZE = 10
LLM_TEXT_CHARS = 2500
MIN_SCORE, MAX_SCORE = 1, 5
JFROG_BONUS = 1
SNIPPET_SCORE_CAP = 4  # an item we could only read a snippet of cannot score above this (Ofri, Oct 30: was 3)
SNIPPET_REVIEW_MIN = 4  # ...and at or above this it goes to review: a high score resting on a teaser needs a human
NOISE_SCORE = 1
WHY_MAX_CHARS = 160
NOISE_WHY = "Not relevant to JFrog's competitive picture."

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
    degraded: bool = False  # the LLM gave no usable score: score is None and the item is in review
    score: int | None  # after the code adjustments; None when degraded
    reason: str  # one line
    why_it_matters: str = ""  # one line, to JFrog, <= WHY_MAX_CHARS; NOISE_WHY for noise, "" when degraded
    adjustments: list[str] = []
    needs_review: bool = False  # D9: routed to the analyst review queue whatever the autonomy threshold
    review_reasons: list[str] = []
    confidence: float  # the classifier's, used for tie-breaking
    published_at: datetime | None = None

    @property
    def auto_publishable(self) -> bool:
        """Scored and not held for review (the autonomy threshold applies on top of this, later)."""
        return self.score is not None and not self.degraded and not self.needs_review


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


def adjust(raw: int, item: dict, cls: Classification) -> tuple[int, list[str]]:
    """The code side of D14: bonus, snippet cap, noise. Returns the final score and what was applied."""
    if cls.noise:
        return NOISE_SCORE, [] if raw == NOISE_SCORE else [f"noise -> {NOISE_SCORE}"]
    score, notes = raw, []
    if cls.mentions_jfrog and score < MAX_SCORE:
        score = min(MAX_SCORE, score + JFROG_BONUS)
        notes.append(f"+{JFROG_BONUS} Mentions JFrog")
    status = item.get("text_status")
    if status in ("snippet", "junk") and score > SNIPPET_SCORE_CAP:  # junk text is read like a snippet
        score = SNIPPET_SCORE_CAP
        notes.append(f"{status} cap {SNIPPET_SCORE_CAP}")
    return score, notes


# D9 forced-review rules, one (reason, predicate) per rule; the start of routing, kept explicit and small.
REVIEW_RULES = [
    ("snippet-only item scored >= 4",
     lambda item, cls, score: item.get("text_status") == "snippet" and score >= SNIPPET_REVIEW_MIN),
    ("junk extraction",
     lambda item, cls, score: item.get("text_status") == "junk" and score >= SNIPPET_REVIEW_MIN),
]


def review_reasons(item: dict, cls: Classification, score: int) -> list[str]:
    """The REVIEW_RULES that apply, plus the classifier's own reason when it sent the item to review."""
    held = [cls.review_reason] if cls.needs_review and cls.review_reason else []
    return [reason for reason, applies in REVIEW_RULES if applies(item, cls, score)] + held


def why_line(value, reason: str) -> str:
    """The model's why_it_matters as one line when it is usable (non-empty, <= WHY_MAX_CHARS); otherwise the reason
    line, cut to fit."""
    why = " ".join(str(value or "").split()) if isinstance(value, str) else ""
    if why and len(why) <= WHY_MAX_CHARS:
        return why
    fallback = " ".join((reason or "").split())
    return fallback if len(fallback) <= WHY_MAX_CHARS else fallback[:WHY_MAX_CHARS - 1].rstrip() + "…"


def sort_key(r: Ranked):
    ts = r.published_at.timestamp() if r.published_at else float("-inf")
    return (r.score is None, -(r.score or 0), -r.confidence, -ts, r.id)


def order(ranked: list[Ranked]) -> list[Ranked]:
    """Highest score first, degraded (unscored) items last; ties by classifier confidence, then newest; then id so
    the order is stable."""
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
                    "why_it_matters": {"type": "string", "maxLength": WHY_MAX_CHARS},
                },
                "required": ["id", "score", "reason", "why_it_matters"],
            }}},
            "required": ["items"],
        }

    @staticmethod
    def prompt(pairs: list[tuple[dict, Classification]]) -> str:
        payload = [{"id": it["id"], "competitor": c.competitor, "category": c.category, "source": it.get("source"),
                    "publisher": it.get("publisher") or "", "title": it.get("title") or "",
                    "text": content_text(it)[:LLM_TEXT_CHARS]} for it, c in pairs]
        return f"""You rank news items for JFrog's competitive-intelligence team.
JFrog sells a software supply chain platform: Artifactory (artifact and package repositories), Xray (security
scanning), Curation, and AI/MCP tooling. Score each item on this rubric:

{RUBRIC}

Score the content against the rubric only; code applies its own adjustments afterwards. For each id give the score,
a one-line reason (under 25 words) naming what drove the score, and why_it_matters: one line, at most
{WHY_MAX_CHARS} characters, saying what this means for JFrog (e.g. "Puts Sonatype head-to-head with Artifactory on AI
model curation."). Answer only about the ids given, once each.

Items (JSON):
{json.dumps(payload, ensure_ascii=False, indent=1)}
"""

    def _llm_scores(self, pairs: list[tuple[dict, Classification]]) -> tuple[dict[str, tuple[int, str, str]], str]:
        """({id: (score, reason, why_it_matters)} for the usable answers, the error class when the whole batch
        failed)."""
        ids = [it["id"] for it, _ in pairs]
        try:
            answer = self.llm.complete(self.prompt(pairs), self.schema(ids))
            rows = answer.get("items") if isinstance(answer, dict) else None
            if not isinstance(rows, list):
                raise LLMError(f"no items list in answer: {str(answer)[:200]}")
        except Exception as e:  # one bad batch must not stop the run
            log.warning("ranker batch of %d failed: %s", len(pairs), e)
            return {}, type(e).__name__
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
            out[row["id"]] = (score, reason, why_line(row.get("why_it_matters"), reason))
        return out, ""

    def rank(self, items: list[dict], classifications: list[Classification]) -> list[Ranked]:
        """Ranked items, best first. classifications is matched to items by id."""
        by_id = {c.id: c for c in classifications}
        pairs = [(it, by_id[it["id"]]) for it in items]
        to_score = [(it, c) for it, c in pairs if not c.noise]
        scores: dict[str, tuple[int, str, str]] = {}
        errors: dict[str, str] = {}
        for start in range(0, len(to_score), self.batch_size):
            batch = to_score[start:start + self.batch_size]
            got, error = self._llm_scores(batch)
            scores.update(got)
            errors.update({it["id"]: error for it, _ in batch if error})
        ranked = []
        for it, c in pairs:
            common = {"id": it["id"], "confidence": c.confidence, "published_at": _as_datetime(it.get("published_at"))}
            if not c.noise and it["id"] not in scores:
                error = errors.get(it["id"], "InvalidAnswer")
                reasons = [f"ranker unavailable: {error}", *([c.review_reason] if c.degraded else [])]
                ranked.append(Ranked(**common, raw_score=None, degraded=True, score=None, needs_review=True,
                                     review_reasons=reasons, reason=""))
                continue
            raw, reason, why = (None, "classified as noise", NOISE_WHY) if c.noise else scores[it["id"]]
            score, notes = adjust(NOISE_SCORE if raw is None else raw, it, c)
            reasons = review_reasons(it, c, score)
            ranked.append(Ranked(**common, raw_score=raw, score=score, needs_review=bool(reasons),
                                 review_reasons=reasons, reason=reason or "(no reason given)", adjustments=notes,
                                 why_it_matters=why))
        return order(ranked)


def rank(items: list[dict], classifications: list[Classification], llm: JsonLLM) -> list[Ranked]:
    return Ranker(llm).rank(items, classifications)
