"""Output validation for the daily run (PRD D32).

Two checks, both against the config lists:
- check_answer: every row of a model answer, against the schema the code sent (item ids of the batch, competitor and
  category enums from the config, score 1-5, noise a boolean, required fields). Invented, duplicate and missing ids
  are rejected too. ValidatingLLM runs it on every call and passes the answer through unchanged: the classifier and
  ranker already turn an unusable row into a degraded output, and this records which item it was and why.
- check_outputs: the final classifications and rankings: existing item ids only, competitor and category from the
  config lists, score 1-5 or noise (noise has no score), one classification and one ranking per item sent.

Every rejection is logged with the item id and the reason, stored by the daily run, and its item is routed to review.
"""
import logging
from dataclasses import dataclass

from ci.classify import CATEGORIES, Classification
from ci.config import CIConfig
from ci.llm import JsonLLM
from ci.packet import NON_COMPETITOR
from ci.rank import MAX_SCORE, MIN_SCORE, Ranked

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Rejection:
    item_id: str
    stage: str  # classifier | ranker | output
    reason: str


def _row_problems(row: dict, props: dict, required: list[str]) -> list[str]:
    problems = [f"{k} missing" for k in required if k not in row]
    for key, spec in props.items():
        if key == "id" or key not in row:
            continue
        value = row[key]
        if "enum" in spec and value not in spec["enum"]:
            where = "the config list" if key in ("competitor", "category") else "the allowed list"
            problems.append(f"{key} {value!r} not in {where}")
        elif spec.get("type") == "boolean" and not isinstance(value, bool):
            problems.append(f"{key} {value!r} is not true/false")
        elif spec.get("type") == "integer":
            if isinstance(value, bool) or not isinstance(value, int | float):
                problems.append(f"{key} {value!r} is not an integer")
            elif isinstance(value, float) and not value.is_integer():
                problems.append(f"{key} {value!r} is not an integer")
            elif not spec.get("minimum", value) <= value <= spec.get("maximum", value):
                problems.append(f"{key} {value!r} outside {spec.get('minimum')}-{spec.get('maximum')}")
    return problems


def check_answer(schema: dict, answer, stage: str) -> list[Rejection]:
    """Rejections for one model answer, judged against the schema it was asked to follow."""
    item_schema = schema["properties"]["items"]["items"]
    props, required = item_schema["properties"], item_schema.get("required", [])
    ids = list(props["id"]["enum"])
    rows = answer.get("items") if isinstance(answer, dict) else None
    if not isinstance(rows, list):
        return [Rejection(i, stage, f"no items list in the answer: {str(answer)[:80]}") for i in ids]
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            out.append(Rejection("?", stage, f"answer row is not an object: {str(row)[:80]}"))
            continue
        item_id = row.get("id")
        if item_id not in ids:
            out.append(Rejection(str(item_id), stage, "unknown item id (not in this batch)"))
            continue
        if item_id in seen:
            out.append(Rejection(item_id, stage, "duplicate answer for this id"))
            continue
        seen.add(item_id)
        problems = _row_problems(row, props, required)
        if problems:
            out.append(Rejection(item_id, stage, "; ".join(problems)))
    return out + [Rejection(i, stage, "no answer for this id") for i in ids if i not in seen]


class ValidatingLLM:
    """Checks every answer against its schema and records the rejections; returns the answer unchanged."""

    def __init__(self, inner: JsonLLM):
        self.inner = inner
        self.model = getattr(inner, "model", type(inner).__name__)
        self.rejections: list[Rejection] = []

    def complete(self, prompt: str, schema: dict) -> dict:
        answer = self.inner.complete(prompt, schema)
        props = schema["properties"]["items"]["items"]["properties"]
        stage = "ranker" if "score" in props else "classifier"
        found = check_answer(schema, answer, stage)
        for r in found:
            log.warning("rejected %s output for item %s: %s", r.stage, r.item_id, r.reason)
        self.rejections += found
        return answer


def check_outputs(sent_ids: set[str], cfg: CIConfig, classifications: list[Classification],
                  ranked: list[Ranked]) -> list[Rejection]:
    """Rejections for the final outputs of one run. Degraded outputs are already in review with their own reason."""
    competitors = {c.key for c in cfg.competitors} | {NON_COMPETITOR}
    out: list[Rejection] = []
    for c in classifications:
        if c.id not in sent_ids:
            out.append(Rejection(c.id, "output", "unknown item id (not sent to the model in this run)"))
            continue
        if c.degraded:
            continue
        if c.competitor not in competitors:
            out.append(Rejection(c.id, "output", f"competitor {c.competitor!r} not in the config list"))
        if not c.noise and c.category not in CATEGORIES:
            out.append(Rejection(c.id, "output", f"category {c.category!r} not in the category list"))
    noise = {c.id for c in classifications if c.noise}
    for r in ranked:
        if r.id not in sent_ids:
            if r.id not in {c.id for c in classifications}:
                out.append(Rejection(r.id, "output", "unknown item id (not sent to the model in this run)"))
            continue
        if r.degraded:
            continue
        if r.id in noise or r.noise:
            if r.score is not None:
                out.append(Rejection(r.id, "output", f"noise item has score {r.score}; noise has no score"))
        elif r.score is None or not MIN_SCORE <= r.score <= MAX_SCORE:
            out.append(Rejection(r.id, "output", f"score {r.score} is neither {MIN_SCORE}-{MAX_SCORE} nor noise"))
    have_c, have_r = {c.id for c in classifications}, {r.id for r in ranked}
    for i in sorted(sent_ids):
        if i not in have_c:
            out.append(Rejection(i, "output", "no classification"))
        if i not in have_r:
            out.append(Rejection(i, "output", "no ranking"))
    for r in out:
        log.warning("rejected output for item %s: %s", r.item_id, r.reason)
    return out


def route_to_review(rejections: list[Rejection], classifications: list[Classification],
                    ranked: list[Ranked]) -> tuple[list[Classification], list[Ranked]]:
    """Mark every output of a rejected item as needing review, with the rejection as its reason."""
    by_id: dict[str, list[Rejection]] = {}
    for r in rejections:
        by_id.setdefault(r.item_id, []).append(r)

    def why(item_id: str) -> list[str]:
        return [f"invalid output ({r.stage}): {r.reason}" for r in by_id[item_id]]

    cls = [c.model_copy(update={"needs_review": True, "review_reason": "; ".join(why(c.id))})
           if c.id in by_id else c for c in classifications]
    rk = [r.model_copy(update={"needs_review": True, "review_reasons": [*r.review_reasons, *why(r.id)]})
          if r.id in by_id else r for r in ranked]
    return cls, rk
