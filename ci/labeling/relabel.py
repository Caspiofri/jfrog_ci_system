"""Cross-run relabel queue: the reviewer re-reviews older golden labels by hand under rubric v2.

The queue lists existing labels, not items: every label saved before a cutoff plus named extras, as
{id, run_id} pairs in a fixed order. Each card's item comes from its own run file, and saves go to that run.
The queue lives in output/relabel/<queue_id>.json, never in output/runs, so nothing that globs run files
(ci.eval_golden.story_keys, the run list) sees it. The server only reads it; this CLI writes it.

    python -m ci.labeling.relabel --cutoff 2026-10-30T15:30:00Z --first "<title>" ... --include-title "<title>"

No system predictions reach the page: items are reduced to what the source gave (ITEM_FIELDS).
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from config.settings import DATA_DIR, EVALS_DIR, OUTPUT_DIR

RELABEL_DIR = OUTPUT_DIR / "relabel"
CHANGES_DB = DATA_DIR / "ci" / "changes.sqlite"  # the head-to-head store (ci.changes.run: CI_DATA_DIR / DB_NAME)
QUEUE_VERSION = 1
JFROG = "jfrog"

# what the source gave; everything else on a packet (mentions, extraction verdicts, prefilter or classifier
# output, the query's competitor guess) is a system prediction and stays off the relabel cards
ITEM_FIELDS = ("id", "run_id", "source", "origin", "title", "url", "original_url", "url_resolved", "published_at",
               "date_precision", "publisher", "in_24h", "text", "text_status")
# label fields compared to decide whether a save changed the label (and so needs a reason)
COMPARED_FIELDS = ("competitor", "category", "score", "noise", "mentions_jfrog", "basis", "bad_extraction", "note")
# JFrog's head-to-head axes per label category, shown on score-3/4 cards
CATEGORY_AXES = {
    "Security": ["security_scanning", "curation_gating"],
    "AI & Agents": ["ai_mcp"],
    "Pricing & Packaging": ["pricing_model"],
}
PRODUCT = "Product & Features"  # many axes could apply: list their names only


def _utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _find(labels: dict[str, dict], ref: str) -> str:
    """The label id for a title (exact) or an "id:<id>" reference; ambiguity or no match is an error."""
    if ref.startswith("id:"):
        if ref[3:] not in labels:
            raise SystemExit(f"no label with id {ref[3:]}")
        return ref[3:]
    hits = [i for i, lab in labels.items() if (lab.get("item") or {}).get("title") == ref]
    if len(hits) != 1:
        raise SystemExit(f"title {ref!r} matches {len(hits)} labels {hits}; use id:<id>")
    return hits[0]


def build(labels_path: Path, runs_dir: Path, cutoff: str, first: list[str], include: list[str],
          include_reason: str, queue_id: str) -> dict:
    from ci.labeling.app import latest_labels, read_jsonl  # the app imports this module

    labels = latest_labels(labels_path)
    cut = _utc(cutoff)
    chosen = {i: "labeled before the cutoff" for i, lab in labels.items() if _utc(lab["labeled_at"]) < cut}
    for ref in include:
        i = _find(labels, ref)
        chosen.setdefault(i, f"included: {include_reason}")
    first_ids = [_find(labels, ref) for ref in first]
    for i in first_ids:
        if i not in chosen:
            raise SystemExit(f"--first {i} is not in the queue; add it with --include-title")
    run_ids = {labels[i]["run_id"] for i in chosen}
    in_runs = {(r, row.get("id")) for r in run_ids for row in read_jsonl(runs_dir / f"{r}.jsonl")}
    missing = [i for i in chosen if (labels[i]["run_id"], i) not in in_runs]
    if missing:
        raise SystemExit(f"labels whose item is not in its run file: {missing}")

    def key(i: str):  # by competitor, then score high to low; noise after everything
        lab = labels[i]
        return (lab["noise"], lab["competitor"] or "", -(lab.get("score") or 0), lab["item"].get("title") or "", i)

    order = first_ids + sorted((i for i in chosen if i not in first_ids), key=key)
    return {"version": QUEUE_VERSION, "queue_id": queue_id, "built_at": datetime.now(UTC).isoformat(),
            "cutoff": cut.isoformat(), "first": first, "include": include, "include_reason": include_reason,
            "entries": [{"id": i, "run_id": labels[i]["run_id"], "reason": chosen[i]} for i in order]}


def write(queue: dict, out_dir: Path, force: bool = False) -> Path:
    path = out_dir / f"{queue['queue_id']}.json"
    if path.exists() and not force:  # built_at decides progress: a rebuild would reset it
        raise SystemExit(f"{path} exists; pass --force to replace it (progress restarts)")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def list_queues(relabel_dir: Path) -> list[str]:
    return sorted(p.stem for p in relabel_dir.glob("*.json") if not p.name.startswith(".")) \
        if relabel_dir.is_dir() else []


def load(relabel_dir: Path, queue_id: str) -> dict | None:
    if queue_id not in list_queues(relabel_dir):  # also guards against path tricks
        return None
    try:
        q = json.loads((relabel_dir / f"{queue_id}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return q if isinstance(q, dict) and q.get("version") == QUEUE_VERSION else None


def queues_holding(relabel_dir: Path, item_id: str) -> list[dict]:
    return [q for q in (load(relabel_dir, qid) for qid in list_queues(relabel_dir))
            if q and any(e["id"] == item_id for e in q["entries"])]


def is_done(label: dict | None, queue: dict) -> bool:
    """Reviewed in this queue: a label line saved after the queue was built (a change or a confirmation)."""
    return bool(label) and _utc(label["labeled_at"]) > _utc(queue["built_at"])


def changed_fields(previous: dict, new: dict, unset: frozenset[str] | set[str] = frozenset()) -> list[str]:
    """Fields the save changes. Filling a field the old label never had (basis, bad_extraction, an empty note, or
    any field in `unset`, e.g. a bad_extraction that was only the page default) is no change."""
    out = []
    for f in COMPARED_FIELDS:
        old, val = previous.get(f), new.get(f)
        if f in unset or (f in ("basis", "bad_extraction") and old is None) or (f == "note" and not old):
            continue
        if f == "note":
            old, val = old or "", val or ""
        if old != val:
            out.append(f)
    return out


def jfrog_cells(db_path: Path) -> dict[str, dict] | None:
    """JFrog's head-to-head cells by axis, read-only; None when the store is missing or unreadable."""
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as con:
            rows = con.execute("SELECT axis, value, evidence, as_of FROM cells WHERE competitor = ?", (JFROG,))
            return {a: {"axis": a, "value": v, "quote": q, "as_of": t} for a, v, q, t in rows.fetchall()}
    except sqlite3.Error:
        return None


def jfrog_baseline(label: dict | None, cells: dict[str, dict] | None) -> dict | None:
    """What a score-3/4 card shows about JFrog for the label's category; None for every other card."""
    if not label or label.get("noise") or label.get("score") not in (3, 4):
        return None
    category = label.get("category")
    if category != PRODUCT and category not in CATEGORY_AXES:
        return None
    if cells is None:
        return {"category": category, "missing": True}
    if category == PRODUCT:
        return {"category": category, "axes": sorted(cells)}
    return {"category": category, "cells": [cells[a] for a in CATEGORY_AXES[category] if a in cells]}


def card_item(item: dict) -> dict:
    return {k: item[k] for k in ITEM_FIELDS if k in item}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build a cross-run relabel queue from the golden set")
    ap.add_argument("--cutoff", required=True, help="every label saved before this UTC time, e.g. 2026-10-30T15:30:00Z")
    ap.add_argument("--first", action="append", default=[],
                    help="title (or id:<id>) to put first; repeatable, in order")
    ap.add_argument("--include-title", action="append", default=[], dest="include",
                    help="title (or id:<id>) to add although saved after the cutoff; repeatable")
    ap.add_argument("--include-reason", default="requested in a manual review")
    ap.add_argument("--queue-id", default="rubric-v2")
    ap.add_argument("--labels", type=Path, default=EVALS_DIR / "golden_set.jsonl")
    ap.add_argument("--runs-dir", type=Path, default=OUTPUT_DIR / "runs")
    ap.add_argument("--out-dir", type=Path, default=RELABEL_DIR)
    ap.add_argument("--force", action="store_true", help="replace an existing queue (its progress restarts)")
    args = ap.parse_args(argv)
    q = build(args.labels, args.runs_dir, args.cutoff, args.first, args.include, args.include_reason, args.queue_id)
    path = write(q, args.out_dir, args.force)
    print(f"{path}: {len(q['entries'])} cards", file=sys.stderr)


if __name__ == "__main__":
    main()
