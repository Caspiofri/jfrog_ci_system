"""Thin runner around the frozen golden-set eval (D53): python -m ci.eval_run [--split train|test|all] [--live].

It runs ci.eval_golden.run unchanged, with LangSmith tracing off (D51), and writes <report>.inputs.json next to the
report: what the eval ran with (ci.run_meta: the three fingerprints, sheet_sha, models, call settings, the combined
fingerprint and the commit), plus the split, n and the report's own fingerprint. eval_golden.py is not edited, so
the runner leaves the classify_rank fingerprint untouched. The report itself is written exactly as before.
"""
import argparse
import json
import sys
from pathlib import Path

from ci import eval_golden, run_meta, tracing


def inputs_path(report_path: str | Path) -> Path:
    p = Path(report_path)
    return p.with_name(p.stem + ".inputs.json")


def write_inputs(report: dict, meta: dict) -> Path | None:
    """<report>.inputs.json for a report that was written; None when the eval wrote none (nothing labeled)."""
    if not report.get("path"):
        return None
    body = {"report": Path(report["path"]).name, "split": report.get("split"), "live": report.get("live"),
            "n": report.get("n"), "report_fingerprint": report.get("fingerprint"), "metadata": meta}
    path = inputs_path(report["path"])
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def run(**kwargs) -> dict:
    """eval_golden.run(**kwargs) with tracing off; adds report["inputs_path"] when the report was written."""
    with tracing.off_for_eval():
        report = eval_golden.run(**kwargs)
    model = report.get("model") if report.get("live") else None
    meta = run_meta.safe_collect(fingerprints={"classify_rank": report.get("fingerprint")}, model=model,
                                 cfg=kwargs.get("cfg"))
    path = write_inputs(report, meta)
    report["inputs_path"] = str(path) if path else None
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.eval_run", description=__doc__.split("\n")[0])
    ap.add_argument("--split", choices=eval_golden.SPLITS, default="train")
    ap.add_argument("--live", action="store_true", help="call Gemini (needs GOOGLE_API_KEY)")
    ap.add_argument("--allow-fallback", action="store_true", help="debugging only, as in ci.eval_golden")
    args = ap.parse_args(argv)
    report = run(split=args.split, live=args.live, allow_fallback=args.allow_fallback)
    print(eval_golden.format_report(report))
    if report.get("inputs_path"):
        print(f"Wrote {report['inputs_path']}")
    return 2 if report["aborted"] else 0


if __name__ == "__main__":
    sys.exit(main())
