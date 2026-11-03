"""Held-out coverage (D26, D84): of the events on the held-out list, how many did any of the daily runs capture.

    python -m ci.coverage_heldout [--events PATH] [--runs-dir DIR] [--out-dir DIR]

An event counts as captured when ANY item of ANY of the runs below, kept or dropped, matches it, by the same
rules as ci.coverage (URL or title keywords; see that module). One run alone undercounts: an event whose feed entry
rolled off before a later run is still captured by the run that saw it.

The runs are fixed here, before any event is marked, so the choice cannot follow the result. They are the four daily
runs that could see an event dated 31 Oct-2 Nov: 802913 (31 Oct), e9cae4 (1 Nov), bed018 (2 Nov, before 06:00 local)
and d03c41 (3 Nov, the rest of 2 Nov). 389e71 and 5d06a9 started on 30 Oct, before the period, and 5d06a9 never
entered the store (D79).

Recall is over the events dated inside the held-out period (calendar dates, both ends included); events outside it
are listed apart and left out of recall. "kept" means kept by at least one run; "dropped only" means every match was a
dropped item. The report has the shape of a ci.coverage report, so ci.health_summary coverage reads it as it is.

Measured once (D84): the report is written once and an existing one is never overwritten. No model call.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ci import config as ci_config
from ci import coverage
from ci.config import canonical_item
from config.settings import EVALS_DIR

EVENTS_PATH = EVALS_DIR / "coverage_events_heldout_20261031_20261102.yaml"
OUT_DIR = coverage.COVERAGE_DIR / "heldout"
REPORT_ID = "heldout-20261031_20261102"
PERIOD = (date(2026, 10, 31), date(2026, 11, 2))
RUNS = ("20261031T1345Z-802913", "20261101T0400Z-e9cae4", "20261102T0400Z-bed018", "20261103T0400Z-d03c41")


class AlreadyMeasured(RuntimeError):
    """The held-out report exists: it is measured once and never rewritten."""


def run_items(run_id: str, runs_dir: Path) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) items of one run, each tagged with its run id. A run without its kept file is an error."""
    kept_path = runs_dir / f"{run_id}.jsonl"
    if not kept_path.exists():
        raise FileNotFoundError(f"no kept items for run {run_id} in {runs_dir}")
    def tag(rows: list[dict]) -> list[dict]:
        return [{**canonical_item(r), "run_id": run_id} for r in rows]
    return (tag(coverage.read_jsonl(kept_path)),
            tag(coverage.read_jsonl(runs_dir / f"{run_id}.dropped.jsonl")))


def measure(events: list[coverage.Event], runs_dir: Path, runs: tuple[str, ...] | None = None,
            period: tuple[date, date] = PERIOD, cfg: ci_config.CIConfig | None = None) -> dict:
    runs = runs or RUNS
    kept, dropped, per_run = [], [], {}
    for run_id in runs:
        k, d = run_items(run_id, runs_dir)
        kept += k
        dropped += d
        per_run[run_id] = {"kept": len(k), "dropped": len(d)}
    report = coverage.evaluate(events, kept, dropped, period, cfg)
    by_event = {ev.id: ev for ev in events}
    for row in report["events"]:  # an item id can recur across runs (kept once, dropped as seen later): match again
        ev = by_event[row["id"]]
        row["captured_by_runs"] = sorted({it["run_id"] for it in kept + dropped if coverage.match_item(ev, it)})
    return {"run_id": REPORT_ID, "runs": list(runs), "items_per_run": per_run,
            "window_days": (period[1] - period[0]).days + 1, **report}


def run(events_path: Path = EVENTS_PATH, runs_dir: Path = coverage.RUNS_DIR, out_dir: Path = OUT_DIR,
        cfg: ci_config.CIConfig | None = None) -> tuple[dict, Path]:
    out = out_dir / f"{REPORT_ID}.json"
    if out.exists():
        raise AlreadyMeasured(f"{out} exists: the held-out coverage is measured once")
    if not events_path.exists():
        raise FileNotFoundError(f"no held-out events file at {events_path}")
    report = {**measure(coverage.load_events(events_path), runs_dir, cfg=cfg),
              "events_file": events_path.name}  # a name, not a local path (D59)
    out_dir.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:  # "x": never overwrite, even if another run wrote it meanwhile
        f.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report, out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--events", type=Path, default=EVENTS_PATH)
    ap.add_argument("--runs-dir", type=Path, default=coverage.RUNS_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    try:
        report, out = run(args.events, args.runs_dir, args.out_dir)
    except (AlreadyMeasured, FileNotFoundError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    print(coverage.format_report(report))
    print(f"\nruns: {', '.join(report['runs'])}\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
