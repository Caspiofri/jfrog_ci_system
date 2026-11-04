"""D74: a run-metrics row rebuilt once, from the per-item log, for a run that ended before run_metrics existed.

    python -m ci.metrics_backfill --store PATH --run RUN_ID [--not-this-run OTHER_ID ...] [--write]

Without --write it prints the row and writes nothing. --store has no default, so the live store is only ever named on
purpose. Each number comes from one named source, recorded in the row's `reconstructed.sources`:
- item_log: kept (sightings), new (items first seen by the run), test_skip (skips), to_model and noise
  (classifications of the run), non_noise = to_model - noise
- run_report: collected, the count fetched before deduplication, which the item log cannot hold (duplicates are never
  stored); taken from the run's own runs.report, written when it ran
Left null, with the reason in `reconstructed.empty`: published, held, by_status, routed_n (no routing ran: ci.route
was added on 31 Oct at 14:32 UTC, after both runs) and the blocks no table keeps per run (extraction, lens, insights,
validation, steps). Nothing is estimated.

Refused: a run that already has a row (never overwritten), a run not in the store, and a run whose Israel date has
another run in the store or in output/runs (D74: list the run ids, do not choose or merge). A manual override, per run:
--not-this-run names each other run of the date that gets no row; it must name exactly those runs, and they are
recorded in `reconstructed.other_runs_same_date`. Decided on 3 Nov: 30 Oct belongs to the import 20261030T1312Z-389e71;
20261030T0836Z-5d06a9, a labelling collection never imported into the store, gets no row. The write is one INSERT into
run_metrics, under the collect run lock so no daily run is writing at the same time; no other table is touched.
"""
import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from ci.api import service as svc
from ci.pipeline import RUNS_DIR
from ci.runlock import RunLocked, run_lock

DECISION = "D74"
ITEM_LOG = "item_log"
RUN_REPORT = "run_report"
NO_ROUTING = "no routing ran at this run (ci.route was added on 31 Oct 2026 at 14:32 UTC)"
NOT_KEPT = "not kept per run by the store"


class Refused(Exception):
    pass


def _one(db: sqlite3.Connection, sql: str, *args) -> int:
    return db.execute(sql, args).fetchone()[0]


def same_day_runs(db: sqlite3.Connection, run: dict, runs_dir: Path) -> list[str]:
    """Every run id on the run's Israel date, from the store's runs and the run files in runs_dir."""
    day = svc.israel_date(svc.parse_ts(run["started_at"]))
    ids = {r for r, s in db.execute("SELECT run_id, started_at FROM runs")
           if svc.israel_date(svc.parse_ts(s)) == day}
    for p in runs_dir.glob("*.report.json") if runs_dir.exists() else ():
        rid = p.name.removesuffix(".report.json")
        try:
            started = datetime.strptime(rid.split("-")[0], "%Y%m%dT%H%MZ").replace(tzinfo=UTC)
        except ValueError:
            continue
        if svc.israel_date(started) == day:
            ids.add(rid)
    return sorted(ids)


def reconstruct(db: sqlite3.Connection, run_id: str, runs_dir: Path = RUNS_DIR, now: datetime | None = None,
                not_this_run: dict[str, str] | None = None) -> dict:
    """not_this_run: {other run id on the same date: why it gets no row}, the reviewer's override (D74)."""
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise Refused(f"run {run_id} is not in the store")
    run = dict(row)
    if _one(db, "SELECT count(*) FROM run_metrics WHERE run_id = ?", run_id):
        raise Refused(f"run {run_id} already has a metrics row; it is never overwritten")
    not_this_run = not_this_run or {}
    others = [r for r in same_day_runs(db, run, runs_dir) if r != run_id]
    if stray := sorted(set(not_this_run) - set(others)):
        raise Refused(f"--not-this-run names runs that are not on that date: {stray}")
    if sorted(not_this_run) != others:
        raise Refused(f"more than one run on that date, not choosing or merging: {sorted([run_id, *others])}")
    report = json.loads(run["report"] or "{}")
    to_model = _one(db, "SELECT count(*) FROM classifications WHERE run_id = ?", run_id)
    noise = _one(db, "SELECT count(*) FROM classifications WHERE run_id = ? AND noise = 1", run_id)
    collected = (report.get("funnel") or {}).get("totals", {}).get("collected")
    items = {
        "collected": collected,
        "kept": _one(db, "SELECT count(*) FROM sightings WHERE run_id = ?", run_id),
        "new": _one(db, "SELECT count(*) FROM items WHERE first_run_id = ?", run_id),
        "test_skip": _one(db, "SELECT count(*) FROM skips WHERE run_id = ?", run_id),
        "to_model": to_model, "noise": noise, "non_noise": to_model - noise,
        "published": None, "held": None, "routed_n": None, "by_status": None, "recovered": None,
    }
    sources = {f"items.{k}": ITEM_LOG for k in ("kept", "new", "test_skip", "to_model", "noise", "non_noise")}
    if collected is not None:
        sources["items.collected"] = RUN_REPORT
    empty = {f"items.{k}": NO_ROUTING for k in ("published", "held", "routed_n", "by_status")}
    empty["items.recovered"] = NOT_KEPT
    empty |= {k: NOT_KEPT for k in ("extraction", "lens", "insights", "validation", "steps", "metadata", "llm_calls")}
    if collected is None:
        empty["items.collected"] = "not in the run's report"
    return {
        "run_id": run_id, "kind": run["kind"], "status": run["status"], "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "fingerprints": {"classify_rank": run["fingerprint"], "lens": None, "insights": None},
        "model": run["model"], "llm_calls": None, "error": run["error"], "items": items, "extraction": None,
        "lens": None, "insights": None, "validation": None, "steps": [], "metadata": None,
        "reconstructed": {"decision": DECISION, "at": (now or datetime.now(UTC)).isoformat(),
                          "label": "Reconstructed from the item log", "sources": sources, "empty": empty,
                          "other_runs_same_date": [{"run_id": r, "note": n} for r, n in sorted(not_this_run.items())]},
    }


def write(db: sqlite3.Connection, m: dict) -> None:
    """One INSERT (not OR REPLACE): an existing row makes it fail rather than be overwritten."""
    fp = m["fingerprints"]
    with db:
        db.execute("INSERT INTO run_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (m["run_id"], m["kind"], m["status"], m["started_at"], m["finished_at"], fp.get("classify_rank"),
                    fp.get("lens"), fp.get("insights"), json.dumps(m, ensure_ascii=False)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--not-this-run", action="append", default=[], metavar="RUN_ID",
                    help="another run on the same date that gets no row (the reviewer's override, D74)")
    ap.add_argument("--note", default="never imported into the store; gets no metrics row (manual review, 3 Nov, D74)",
                    help="why the --not-this-run runs get no row")
    ap.add_argument("--lock-dir", type=Path, default=None, help="where the collect run lock lives (default: data/ci)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if not args.store.exists():
        print(f"no store at {args.store}", file=sys.stderr)
        return 2
    db = sqlite3.connect(args.store)
    try:
        m = reconstruct(db, args.run, args.runs_dir, not_this_run={r: args.note for r in args.not_this_run})
        print(json.dumps(m, indent=1, ensure_ascii=False))
        if args.write:
            with run_lock("collect", args.lock_dir):
                write(db, m)
            print(f"written: {args.run}", file=sys.stderr)
    except (Refused, RunLocked) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
