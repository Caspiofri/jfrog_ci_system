"""Label audit: does each golden label meet the current standard (rubric v2 plus the fields added since)?

The checks read only Ofri's own label, never a system prediction. `issues` is the one definition of the standard;
the labeling page, its API, this CLI and the golden-set eval all use it.

    python -m ci.labeling.audit [--labels evals/golden_set.jsonl]
"""
import argparse
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from ci.labeling import relabel, stratified
from config.settings import EVALS_DIR, OUTPUT_DIR

STANDARD = "rubric-v2"  # the stamp every relabel-queue save carries

# issue code -> the plain name the page shows, in display order
ISSUES = {
    "not_reviewed_v2": "not reviewed under v2",
    "bad_extraction_unanswered": "bad extraction not answered",
    "no_basis": "no basis",
    "no_note": "no note",
    "score1_pre_v2": "score 1 from before v2",
    "noise_fields": "noise with a category or score",
    "missing_score_or_category": "missing score or category",
}


def _utc(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def bad_extraction_explicit(label: dict, topup_required: bool = False) -> bool:
    """An explicit Yes/No answer: stamped by a relabel-queue save, or required by the top-up queue the item is in.
    An old False without either may be the page's default, so it does not count."""
    if not isinstance(label.get("bad_extraction"), bool):
        return False
    return label.get("bad_extraction_explicit") is True or topup_required


def issues(label: dict, queue_built_at: str | None, topup_required: bool = False) -> list[str]:
    """Issue codes for one label under the current standard; [] means complete. queue_built_at is the relabel
    queue's build time (rubric v2 starts there); None skips the score-1 check."""
    out = []
    if label.get("standard") != STANDARD:
        out.append("not_reviewed_v2")
    if not bad_extraction_explicit(label, topup_required):
        out.append("bad_extraction_unanswered")
    if label.get("basis") not in ("full", "partial"):
        out.append("no_basis")
    if not (label.get("note") or "").strip():
        out.append("no_note")
    noise = label.get("noise") is True
    built = _utc(queue_built_at)
    saved = _utc(label.get("labeled_at"))
    if not noise and label.get("score") == 1 and built and saved and saved < built:
        out.append("score1_pre_v2")  # v1's 1 meant noise-level; v2's 1 means routine
    if noise and (label.get("category") is not None or label.get("score") is not None):
        out.append("noise_fields")
    if not noise and (label.get("category") is None or label.get("score") is None):
        out.append("missing_score_or_category")
    return out


class Context:
    """What `issues` needs beyond the label: the relabel queue's build time and the top-up queues' required ids."""

    def __init__(self, runs_dir: Path, relabel_dir: Path):
        built = [q["built_at"] for q in (relabel.load(relabel_dir, i) for i in relabel.list_queues(relabel_dir)) if q]
        self.queue_built_at = min(built, key=_utc) if built else None
        self.runs_dir = runs_dir
        self._topup: dict[str, set[str]] = {}

    def topup_required(self, label: dict) -> bool:
        run_id = label.get("run_id") or ""
        if run_id not in self._topup:
            self._topup[run_id] = stratified.requires_bad_extraction(self.runs_dir, run_id) if run_id else set()
        return label.get("id") in self._topup[run_id]

    def issues(self, label: dict | None) -> list[str]:
        return issues(label, self.queue_built_at, self.topup_required(label)) if label else []


def summarize(per_label: list[list[str]]) -> dict:
    counts = Counter(code for found in per_label for code in found)
    attention = sum(bool(found) for found in per_label)
    return {"total": len(per_label), "needs_attention": attention, "complete": len(per_label) - attention,
            "per_issue": {code: counts.get(code, 0) for code in ISSUES}}


def audit_labels(labels: list[dict], ctx: Context) -> dict:
    return summarize([ctx.issues(lab) for lab in labels])


def table(summary: dict) -> str:
    width = max(len(code) for code in ISSUES)
    lines = [f"{'issue'.ljust(width)}  count"]
    lines += [f"{code.ljust(width)}  {n:>5}" for code, n in summary["per_issue"].items()]
    lines.append(f"complete under current standard: {summary['complete']} of {summary['total']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    from ci.labeling.app import latest_labels  # the app imports this module

    ap = argparse.ArgumentParser(description="Audit the golden labels against the current standard (read-only)")
    ap.add_argument("--labels", type=Path, default=EVALS_DIR / "golden_set.jsonl")
    ap.add_argument("--runs-dir", type=Path, default=OUTPUT_DIR / "runs")
    ap.add_argument("--relabel-dir", type=Path, default=relabel.RELABEL_DIR)
    args = ap.parse_args(argv)
    ctx = Context(args.runs_dir, args.relabel_dir)
    print(table(audit_labels(list(latest_labels(args.labels).values()), ctx)))


if __name__ == "__main__":
    main()
