"""Demo snapshot for a chosen Brief day (D34, D59): the store as it stood before the next daily run, through ci.demo.

Usage: .venv/bin/python tools/demo_snapshot.py --day 2026-11-01 --out <new dir> [--label "why this day"]

Copies data/ci/ci.sqlite to a temporary file (the live store is only read), removes the runs that started after the
chosen day's daily run and every row they produced (items, sightings, classifications, rankings, skips, rejections,
lens, run_metrics), the insights of later Brief days, and analyst actions, item states and trusted sources recorded
after the next daily run started. Nothing is added or rewritten. ci.demo.build then applies the D34 allowlist, puts the
280-character excerpt in place of article text, checks the result and writes the manifest. changes.sqlite is copied
as is (ci.demo clears its local page paths).
"""
import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ci import demo  # noqa: E402
from ci.api import service as svc  # noqa: E402
from ci.store import STORE_PATH  # noqa: E402

RUN_TABLES = ("sightings", "classifications", "rankings", "skips", "rejections", "lens", "run_metrics")
TIMED = (("analyst_actions", "at"), ("item_state", "updated_at"), ("trusted_sources", "added_at"))


def cut(db: sqlite3.Connection, day: str) -> dict:
    """Cut a copy of the store back to the end of `day`'s Brief; return what was removed, per table."""
    runs = db.execute("SELECT run_id, kind, started_at, status FROM runs ORDER BY started_at").fetchall()
    daily = [(r, k, s, st) for r, k, s, st in runs if k == "daily"]
    anchors = [r for r in daily if svc.israel_date(svc.parse_ts(r[2])) == day and r[3] in svc.BRIEF_RUN_STATUSES]
    if not anchors:
        raise SystemExit(f"no ok or degraded daily run on {day}; daily runs: "
                         f"{[(svc.israel_date(svc.parse_ts(s)), r, st) for r, _, s, st in daily]}")
    anchor_start = anchors[0][2]
    later = [r for r in daily if r[2] > anchor_start and svc.israel_date(svc.parse_ts(r[2])) > day]
    cutoff = later[0][2] if later else None
    gone = [r for r, _, s, _ in runs if cutoff and s >= cutoff]
    removed = {}
    if gone:
        marks = ",".join("?" * len(gone))
        for t in RUN_TABLES:
            removed[t] = db.execute(f"DELETE FROM {t} WHERE run_id IN ({marks})", gone).rowcount
        removed["items"] = db.execute(f"DELETE FROM items WHERE first_run_id IN ({marks})", gone).rowcount
        removed["runs"] = db.execute(f"DELETE FROM runs WHERE run_id IN ({marks})", gone).rowcount
    removed["insights"] = db.execute("DELETE FROM insights WHERE brief_date > ?", (day,)).rowcount
    if cutoff:
        for t, col in TIMED:
            removed[t] = db.execute(f"DELETE FROM {t} WHERE {col} >= ?", (cutoff,)).rowcount
    db.commit()
    return {"day": day, "anchor_run": anchors[0][0], "cutoff": cutoff, "removed_runs": gone, "removed": removed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day", required=True, help="the Brief day, YYYY-MM-DD (Asia/Jerusalem)")
    ap.add_argument("--out", type=Path, required=True, help="a new directory; an existing snapshot is never overwritten")
    ap.add_argument("--store", type=Path, default=STORE_PATH)
    ap.add_argument("--changes", type=Path, default=STORE_PATH.parent / demo.CHANGES_FILE)
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / demo.STORE_FILE
        demo._copy(args.store, copy)
        db = sqlite3.connect(copy)
        try:
            info = cut(db, args.day)
        finally:
            db.close()
        label = args.label or f"Brief day {args.day}"
        m = demo.build(args.out, copy, args.changes, label=f"{label} (cut before {info['cutoff'] or 'nothing'})")
    if m["date"] != args.day:
        raise SystemExit(f"snapshot date {m['date']} is not the chosen day {args.day}")
    print(f"cut: anchor {info['anchor_run']}, cutoff {info['cutoff']}, removed runs {info['removed_runs']}, "
          f"rows {info['removed']}")
    print(f"wrote {args.out}: demo snapshot {m['date']}, {m['items']} items, runs {', '.join(m['runs'])}, "
          f"commit {m['commit'][:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
