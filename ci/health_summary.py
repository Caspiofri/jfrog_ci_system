"""Health summaries for the demo snapshot (D80, D83): saved copies of what Health shows, read in demo mode.

    python -m ci.health_summary write --out demo/snapshot [--evals-dir DIR] [--labels PATH] [--changes-dir DIR]
    python -m ci.health_summary coverage --report output/coverage/<run_id>.json --list "held-out ..." \\
        --measured-on YYYY-MM-DD --out demo/snapshot

Each summary is one file, <out>/health/<block>.json, with the live Health block's own shape plus measured_on. `write`
copies the eval, test-split eval and change-detection blocks from the saved reports; `coverage` copies a saved coverage
report. Nothing is rerun and no model is called. Every block passes an explicit field allowlist, and the result is
checked: no local path, no `matches`, article text, golden labels or per-item test predictions. In demo mode Health
reads only these files (ci.api.health) and never output/; a missing file reads "not included in this snapshot".
"""
import argparse
import json
import sys
from pathlib import Path

DIR = "health"
BLOCKS = ("eval", "test_eval", "change_detection", "coverage")
NOT_IN_SNAPSHOT = "not included in this snapshot"

EVAL_KEYS = ("status", "report", "created_at", "split", "live", "fingerprint", "model", "n", "labels",
             "test_eval_run", "cards", "measured_on")
TEST_EVAL_KEYS = ("status", "note", "report", "created_at", "split", "fingerprint", "model", "n", "split_counts",
                  "fallbacks", "test_runs", "metrics", "cards", "measured_on")
CHANGE_KEYS = ("run_id", "started_at", "live", "status", "pages", "fetched", "changes", "failures",
               "unconfirmed", "needs_review", "measured_on")  # age_hours is computed when served, on the demo clock
COVERAGE_KEYS = ("status", "run_id", "list", "window", "overall", "important", "by_source_kind", "missed",
                 "measured_on")
MISSED_KEYS = ("id", "title", "competitor", "expected_importance", "official_url")
FORBIDDEN_KEYS = {"matches", "text", "teaser", "items", "misses", "runs_dir", "events_file", "path", "labels_path",
                  "predictions", "stories", "label_audit"}
METRICS_DROP = {"extraction_detector": ("misses",)}  # per-item ids with their labels


class Unsafe(ValueError):
    pass


def _pick(block: dict, keys: tuple) -> dict:
    return {k: block[k] for k in keys if k in block}


def check(block: dict, where: str = "") -> dict:
    """Raise on a forbidden key or a value that looks like a local path, anywhere in the block."""
    def walk(x, at):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in FORBIDDEN_KEYS:
                    raise Unsafe(f"{where}{at}.{k}: field not allowed in a snapshot summary")
                walk(v, f"{at}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{at}[{i}]")
        elif isinstance(x, str) and (x.startswith(("/", "~")) or "/home/" in x or ":\\" in x):
            raise Unsafe(f"{where}{at}: looks like a local path: {x[:60]!r}")
    walk(block, "")
    return block


def eval_summary(block: dict) -> dict:
    return check({**_pick(block, EVAL_KEYS), "measured_on": block.get("created_at")}, "eval")


def test_eval_summary(block: dict) -> dict:
    out = _pick(block, TEST_EVAL_KEYS)
    if isinstance(out.get("metrics"), dict):
        out["metrics"] = {k: ({kk: vv for kk, vv in v.items() if kk not in METRICS_DROP.get(k, ())}
                              if isinstance(v, dict) else v) for k, v in out["metrics"].items()}
    return check({**out, "measured_on": block.get("created_at")}, "test_eval")


def change_summary(block: dict) -> dict:
    return check({**_pick(block, CHANGE_KEYS), "measured_on": block.get("started_at")}, "change_detection")


def coverage_summary(report: dict, list_label: str, measured_on: str) -> dict:
    """The live coverage block's shape, from a saved ci.coverage report; the list label comes from the caller."""
    def count(x: dict) -> dict:
        return {"captured": x.get("captured", 0), "n": x.get("events", 0)}

    hi = report.get("high_importance") or {}
    return check({
        "status": "ok", "run_id": report.get("run_id"), "list": list_label, "window": report.get("window"),
        "overall": count(report.get("overall") or {}), "important": {**count(hi), "min_score": hi.get("min")},
        "by_source_kind": {k: count(v) for k, v in (report.get("by_source_kind") or {}).items()},
        "missed": [_pick(m, MISSED_KEYS) for m in report.get("missed", [])],
        "measured_on": measured_on}, "coverage")


def save(out_dir: Path, name: str, block: dict) -> Path:
    if name not in BLOCKS:
        raise ValueError(f"block must be one of {BLOCKS}")
    path = out_dir / DIR / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(check(block, name), ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def served(snapshot_dir: Path, name: str) -> dict:
    """What demo-mode Health serves for a block: the saved summary, or a not-included marker. Never output/."""
    path = Path(snapshot_dir) / DIR / f"{name}.json"
    if not path.exists():
        return {"status": "not_in_snapshot", "note": f"{name.replace('_', ' ')}: {NOT_IN_SNAPSHOT}",
                "measured_on": None}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    from ci.api import health
    from ci.eval_golden import EVALS_OUT_DIR, LABELS_PATH
    from config.settings import OUTPUT_DIR

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write", help="eval, test-split eval and change-detection summaries from the saved reports")
    w.add_argument("--out", type=Path, required=True)
    w.add_argument("--evals-dir", type=Path, default=EVALS_OUT_DIR)
    w.add_argument("--labels", type=Path, default=LABELS_PATH)
    w.add_argument("--changes-dir", type=Path, default=OUTPUT_DIR / "changes")
    c = sub.add_parser("coverage", help="the coverage summary from one saved coverage report")
    c.add_argument("--report", type=Path, required=True)
    c.add_argument("--list", required=True, dest="list_label", help='e.g. "held-out (31 Oct-2 Nov, measured once)"')
    c.add_argument("--measured-on", required=True)
    c.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "write":
            for name, block in (("eval", eval_summary(health.eval_summary_block(args.evals_dir, args.labels))),
                                ("test_eval", test_eval_summary(health.test_eval_summary_block(args.evals_dir,
                                                                                               args.labels))),
                                ("change_detection", change_summary(health.change_summary_block(args.changes_dir)))):
                print(save(args.out, name, block))
        else:
            report = json.loads(args.report.read_text(encoding="utf-8"))
            print(save(args.out, "coverage", coverage_summary(report, args.list_label, args.measured_on)))
    except Unsafe as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
