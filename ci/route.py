"""Routing (PRD D9, D34, D36): hold reasons, the three autonomy levels, and an item's status.

The autonomy control is a level, not a confidence number. Each hold reason names the levels that hold an item for it:

    reason              strict  balanced  relaxed
    unvetted_source     held    score>=4  -        host not in config/vetted_sources.yaml (or trusted later, D34)
    low_confidence      held    held      -        classifier confidence below LOW_CONFIDENCE (D36 Q-A)
    teaser_high_score   held    held      -        snippet-only text and score >= 4 (D36 Q-B)
    junk_extraction     held    held      -        page text judged junk and score >= 4 (D36 Q-B)
    pricing             held    held      held     category Pricing & Packaging
    m_and_a             held    held      held     category Funding/M&A/Partnerships (the whole category)
    mentions_jfrog      held    held      held
    model_failure       held    held      held     classifier fallback or degraded ranking
    invalid_output      held    held      held     a D32 validation rejection
    changed_cell        held    held      held     a changed head-to-head cell (D13), see change_hold_reasons

Noise never reaches the queue: it is dropped to the Log (D9). Status is derived, never stored, so changing the level
re-routes at once; an analyst decision (later: item_state) overrides it.

python -m ci.route [--run RUN_ID]   prints the held/published counts per level over the stored outputs.
"""
import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ci import sources
from ci.rank import SNIPPET_REVIEW_MIN

LEVELS = ("strict", "balanced", "relaxed")
DEFAULT_LEVEL = "strict"
LOW_CONFIDENCE = 0.8  # D36 Q-A: below this is held at strict and balanced
ALL = LEVELS
STRICT_BALANCED = ("strict", "balanced")
PRICING, M_AND_A = "Pricing & Packaging", "Funding/M&A/Partnerships"
DECISIONS = ("approved", "dismissed", "flagged")  # analyst decisions; they override routing
STATUSES = ("auto_published", "awaiting_review", "approved", "dismissed", "flagged", "dropped")


@dataclass(frozen=True)
class HoldReason:
    code: str
    detail: str
    held_at: tuple[str, ...]


@dataclass(frozen=True)
class RouteInput:
    """What routing reads about one classified item (see from_output for the store row)."""
    item_id: str
    url: str
    noise: bool
    category: str | None
    mentions_jfrog: bool
    confidence: float
    score: int | None
    text_status: str
    classifier_degraded: bool = False
    ranker_degraded: bool = False
    rejections: tuple[str, ...] = ()  # D32 rejection reasons for this item


def from_output(row: dict, rejections: Iterable[str] = ()) -> RouteInput:
    """A RouteInput from a ci.store outputs() row."""
    c, r = row["classification"], row["ranking"]
    return RouteInput(item_id=row["item_id"], url=row["url"], noise=bool(c["noise"]), category=c.get("category"),
                      mentions_jfrog=bool(c["mentions_jfrog"]), confidence=float(c["confidence"]),
                      score=r.get("score"), text_status=row["raw"].get("text_status", ""),
                      classifier_degraded=bool(c.get("degraded")), ranker_degraded=bool(r.get("degraded")),
                      rejections=tuple(rejections))


def hold_reasons(x: RouteInput, vetted: Callable[[str], bool] = sources.is_vetted) -> list[HoldReason]:
    """Every reason that holds the item at some level. Noise has none: it never reaches the queue."""
    if x.noise:
        return []
    out = []
    if not vetted(x.url):
        balanced = ("balanced",) if x.score is not None and x.score >= 4 else ()
        out.append(HoldReason("unvetted_source", f"publisher host {sources.host(x.url)} is not on the vetted list",
                              ("strict", *balanced)))
    if x.confidence < LOW_CONFIDENCE:
        out.append(HoldReason("low_confidence", f"classifier confidence {x.confidence:.2f} < {LOW_CONFIDENCE}",
                              STRICT_BALANCED))
    if x.score is not None and x.score >= SNIPPET_REVIEW_MIN:
        if x.text_status == "snippet":
            out.append(HoldReason("teaser_high_score", f"score {x.score} rests on a teaser only", STRICT_BALANCED))
        elif x.text_status == "junk":
            out.append(HoldReason("junk_extraction", f"score {x.score} with page text judged junk", STRICT_BALANCED))
    if x.category == PRICING:
        out.append(HoldReason("pricing", "Pricing & Packaging is always reviewed", ALL))
    if x.category == M_AND_A:
        out.append(HoldReason("m_and_a", "Funding/M&A/Partnerships is always reviewed", ALL))
    if x.mentions_jfrog:
        out.append(HoldReason("mentions_jfrog", "the item mentions JFrog", ALL))
    if x.classifier_degraded or x.ranker_degraded:
        which = " and ".join(n for n, d in (("classifier", x.classifier_degraded), ("ranker", x.ranker_degraded)) if d)
        out.append(HoldReason("model_failure", f"{which} gave no usable answer", ALL))
    if x.rejections:
        out.append(HoldReason("invalid_output", "; ".join(x.rejections), ALL))
    return out


def change_hold_reasons() -> list[HoldReason]:
    """A changed head-to-head cell is reviewed at every level (D9, D13)."""
    return [HoldReason("changed_cell", "every changed head-to-head cell is reviewed", ALL)]


def is_held(reasons: Iterable[HoldReason], level: str) -> bool:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    return any(level in r.held_at for r in reasons)


def status(x: RouteInput, level: str = DEFAULT_LEVEL, decision: str | None = None,
           vetted: Callable[[str], bool] = sources.is_vetted) -> str:
    """dropped (noise), an analyst decision, else awaiting_review or auto_published at this level."""
    if x.noise:
        return "dropped"
    if decision is not None:
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of {DECISIONS}, got {decision!r}")
        return decision
    return "awaiting_review" if is_held(hold_reasons(x, vetted), level) else "auto_published"


def level_counts(inputs: Iterable[RouteInput], vetted: Callable[[str], bool] = sources.is_vetted) -> dict:
    """{level: {"held", "published", "n"}} over the non-noise inputs; n is the same for every level."""
    reasons = [hold_reasons(x, vetted) for x in inputs if not x.noise]
    n = len(reasons)
    out = {}
    for level in LEVELS:
        held = sum(is_held(r, level) for r in reasons)
        out[level] = {"held": held, "published": n - held, "n": n}
    return out


def reason_counts(inputs: Iterable[RouteInput], vetted: Callable[[str], bool] = sources.is_vetted) -> dict[str, int]:
    """Items per hold reason (an item can count under several)."""
    counts: dict[str, int] = {}
    for x in inputs:
        for r in hold_reasons(x, vetted):
            counts[r.code] = counts.get(r.code, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    from ci.store import Store

    ap = argparse.ArgumentParser(prog="python -m ci.route", description="Held/published per autonomy level.")
    ap.add_argument("--run", help="only items classified in this run")
    args = ap.parse_args(argv)
    with Store() as store:
        rejected = store.rejection_reasons()
        rows = [o for o in store.outputs() if not args.run or o["run_id"] == args.run]
    inputs = [from_output(o, rejected.get(o["item_id"], ())) for o in rows]
    counts = level_counts(inputs)
    n = next(iter(counts.values()))["n"]
    print(f"non-noise items: {n} (of {len(inputs)} classified){' in run ' + args.run if args.run else ''}")
    for level, c in counts.items():
        print(f"  {level:<9} held {c['held']:>4}  published {c['published']:>4}  (n={c['n']})")
    print("by reason:", ", ".join(f"{k} {v}" for k, v in sorted(reason_counts(inputs).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
