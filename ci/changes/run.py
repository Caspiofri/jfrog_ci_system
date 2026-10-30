"""One change-detection run over the tracked pages (PRD D13): fetch -> hash -> (on change) extract -> diff -> items.

Per page:
- same hash as the last snapshot -> unchanged, the LLM is not called;
- no snapshot yet -> baseline: cells are extracted and stored, no Changes item;
- hash changed -> extract; every axis whose normalized value differs from its cell becomes a Changes item
  (needs_review, D9), and the cell and its history are updated. Equal fields -> no item ("cosmetic").
The new snapshot is stored only after extraction succeeded, so a failed LLM call is retried on the next run.
Each page fails in isolation.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ci.changes.config import JFROG, TrackedPage, TrackedPages
from ci.changes.diff import Cell, CellStore, ChangeItem, make_change, same_field, section_diff
from ci.changes.extract import AxisField, extract_fields, quote_in_text
from ci.changes.snapshot import Fetch, FetchError, SnapshotStore, content_hash, http_fetch, normalize_text
from ci.llm import JsonLLM
from config.settings import DATA_DIR, OUTPUT_DIR

log = logging.getLogger(__name__)

CHANGES_DIR = OUTPUT_DIR / "changes"
CI_DATA_DIR = DATA_DIR / "ci"
DB_NAME = "changes.sqlite"
EVIDENCE_GONE = "evidence gone, value repeated"


@dataclass
class PageResult:
    competitor: str
    page_key: str
    url: str
    status: str  # baseline | unchanged | same_fields | changed | failed | would_extract (dry run)
    hash: str = ""
    items: list[ChangeItem] = field(default_factory=list)
    unconfirmed: list[str] = field(default_factory=list)  # axes whose new value was unstated or unverified
    reasons: dict[str, str] = field(default_factory=dict)  # axis -> why it was unconfirmed
    review: dict[str, str] = field(default_factory=dict)  # axis -> why the cell was flagged needs_review
    reworded: list[str] = field(default_factory=list)  # axes whose value differed only in wording (no item)
    cells: int = 0  # cells stored or confirmed for this page
    fetched: bool = False  # the page was fetched and had text (a later LLM failure still fails the page)
    error: str = ""


@dataclass
class ChangesRun:
    run_id: str
    pages: list[PageResult]
    report: dict
    paths: dict[str, Path]
    items: list[ChangeItem]  # written to <run_id>.jsonl: this run's, plus any an earlier run stored but never wrote


def new_run_id(now: datetime) -> str:
    return f"{now.strftime('%Y%m%dT%H%MZ')}-{uuid.uuid4().hex[:6]}"


def _cell(competitor: str, page: TrackedPage, f: AxisField, now: datetime) -> Cell:
    return Cell(competitor=competitor, axis=f.axis, value=f.value, evidence=f.evidence, confidence=f.confidence,
                tiers=f.tiers, source_url=page.url, page_key=page.key, as_of=now, checked_at=now, note=page.note)


def _usable(f: AxisField) -> bool:
    return f.stated and f.confidence > 0


def _unconfirmed_reason(new: AxisField, old: Cell | None) -> str:
    """Why the new value cannot be trusted, or "". A value the page does not state is a legitimate answer, unless
    the cell had a usable value (then the model may have missed it)."""
    if new.stated and new.confidence <= 0:
        return new.unverified_reason or "confidence 0"
    if not new.stated and old is not None and _usable(AxisField(axis=old.axis, value=old.value,
                                                                 confidence=old.confidence)):
        return "not stated on the page any more"
    return ""


def _reworded(old: Cell, new: AxisField, prev_text: str, text: str) -> bool:
    if new.axis == "pricing_model" and old.tiers and new.tiers:
        return False  # tiers are compared structurally; there is no wording to differ
    quotes = [old.evidence, new.evidence]
    return bool(prev_text) and all(quotes) and all(quote_in_text(q, t) for q in quotes for t in (prev_text, text))


def check_page(res: PageResult, name: str, page: TrackedPage, *, fetch: Fetch, llm: JsonLLM | None,
               snapshots: SnapshotStore, cells: CellStore, run_id: str, now: datetime) -> PageResult:
    """Fills in `res` (status "failed" until it succeeds); raises on a fetch, extraction or store failure."""
    competitor = res.competitor
    text = normalize_text(fetch(page.url))
    if not text:
        raise FetchError("no extractable text")
    res.fetched = True
    res.hash = content_hash(text)
    prev = snapshots.latest(competitor, page.key)
    stored = [c for a in page.axes if (c := cells.get(competitor, a))]
    if prev and prev.hash == res.hash and len(stored) == len(page.axes):
        if llm is not None:
            cells.touch(competitor, page.axes, now)
        res.status, res.cells = "unchanged", len(stored)
        return res
    if llm is None:  # dry run: report only
        res.status = "would_extract"
        return res

    previous = {c.axis: c.value for c in stored if _usable(AxisField(axis=c.axis, value=c.value,
                                                                     confidence=c.confidence))}
    fields = extract_fields(llm, name, page, text, previous)
    baseline = prev is None
    try:
        prev_text = prev.text() if prev else ""
    except OSError:
        prev_text = ""
    for axis in page.axes:
        new, old = fields[axis], cells.get(competitor, axis)
        cell = _cell(competitor, page, new, now)
        reason = _unconfirmed_reason(new, old)
        if reason:  # never overwrites a cell; the snapshot is not stored, so the next run re-extracts
            res.unconfirmed.append(axis)
            res.reasons[axis] = reason
            if old is None:
                cells.put(cell.model_copy(update={"stale": True, "stale_reason": reason}), run_id, "baseline")
            else:
                cells.mark_stale(competitor, axis, reason)
        elif old is None:  # first value for this cell, also when the axis was added to the page later
            cells.put(cell, run_id, "baseline")
            res.cells += 1
        elif same_field(old, new):
            if old.evidence and not quote_in_text(old.evidence, text):
                # the model repeated the anchored value, but what it rested on is gone from the page
                cells.put(cell.model_copy(update={"needs_review": True, "review_reason": EVIDENCE_GONE}), run_id,
                          "review")
                res.review[axis] = EVIDENCE_GONE
            else:
                cells.put(cell, run_id, "")
            res.cells += 1
        elif not baseline and _reworded(old, new, prev_text, text):
            # both quotes are on both page versions: the facts did not move, only the model's wording. The cell
            # keeps its wording (so later anchored extractions stay stable) and is re-confirmed.
            cells.put(old.model_copy(update={"checked_at": now, "stale": False, "stale_reason": ""}), run_id, "")
            res.reworded.append(axis)
            res.cells += 1
        elif baseline or not _usable(AxisField(axis=axis, value=old.value, confidence=old.confidence)):
            cells.put(cell, run_id, "filled")  # the old cell had no usable value: nothing to compare against
            res.cells += 1
        else:
            diff = section_diff(prev_text, text, [old.evidence, new.evidence])
            item = make_change(run_id, page.page_type, old, new, page.url, now, diff, page.note)
            cells.put(cell, run_id, "changed", item)
            res.items.append(item)
            res.cells += 1
    if not res.unconfirmed:
        snapshots.add(competitor, page.key, page.url, text, now)
    res.status = "baseline" if baseline else "changed" if res.items else "same_fields"
    return res


def build_report(run_id: str, results: list[PageResult], live: bool, started: datetime) -> dict:
    by = {s: [r for r in results if r.status == s]
          for s in ("baseline", "unchanged", "same_fields", "changed", "failed", "would_extract")}
    ok = [r for r in results if r.status != "failed"]
    status = "failed" if results and not ok else "ok"
    fetched = [r for r in results if r.fetched]
    return {
        "run_id": run_id, "started_at": started.isoformat(), "live": live, "status": status,
        "pages": len(results), "fetched": len(fetched),
        "baseline": len(by["baseline"]), "unchanged_by_hash": len(by["unchanged"]),
        "changed_hash_same_fields": len(by["same_fields"]), "changed_pages": len(by["changed"]),
        "changes": sum(len(r.items) for r in results), "would_extract": len(by["would_extract"]),
        "failures": [{"competitor": r.competitor, "page": r.page_key, "url": r.url, "error": r.error}
                     for r in by["failed"]],
        "unconfirmed": [{"competitor": r.competitor, "page": r.page_key, "axes": r.unconfirmed, "reasons": r.reasons}
                        for r in results if r.unconfirmed],
        "needs_review": [{"competitor": r.competitor, "page": r.page_key, "axes": r.review}
                         for r in results if r.review],
        "reworded": [{"competitor": r.competitor, "page": r.page_key, "axes": r.reworded}
                     for r in results if r.reworded],
        "per_page": [{"competitor": r.competitor, "page": r.page_key, "status": r.status, "cells": r.cells,
                      "changes": len(r.items)} for r in results],
    }


def format_report(report: dict) -> str:
    mode = "live" if report["live"] else "dry run (fetch + hash only, nothing stored)"
    out = [f"changes run {report['run_id']}  ({mode}, status {report['status']})",
           f"  pages {report['pages']}  fetched {report['fetched']}  baseline {report['baseline']}  "
           f"unchanged by hash {report['unchanged_by_hash']}  changed hash, same fields "
           f"{report['changed_hash_same_fields']}  real changes {report['changes']} "
           f"(on {report['changed_pages']} pages)  failures {len(report['failures'])}"]
    if report.get("recovered"):
        out.append(f"  published {report['recovered']} items stored by an earlier run that did not finish")
    if not report["live"]:
        out.append(f"  would extract {report['would_extract']} pages (new or changed hash)")
    out += [f"  FAILED {f['competitor']}/{f['page']}: {f['error']}" for f in report["failures"]]
    out += [f"  unconfirmed {u['competitor']}/{u['page']}: {', '.join(u['axes'])}" for u in report["unconfirmed"]]
    out += [f"  needs review {r['competitor']}/{r['page']}: {', '.join(f'{a} ({why})' for a, why in r['axes'].items())}"
            for r in report["needs_review"]]
    return "\n".join(out)


def run(pages: TrackedPages, *, llm: JsonLLM | None, fetch: Fetch = http_fetch, names: dict[str, str] | None = None,
        competitors: list[str] | None = None, data_dir: Path = CI_DATA_DIR, out_dir: Path = CHANGES_DIR,
        now: datetime | None = None, keep: int | None = None) -> ChangesRun:
    """llm=None is a dry run: pages are fetched and hashed against the stored snapshots, nothing is written."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    run_id = new_run_id(now)
    names = {JFROG: "JFrog", **(names or {})}
    kw = {"keep": keep} if keep else {}
    snapshots = SnapshotStore(data_dir / DB_NAME, data_dir / "snapshots", **kw)
    cells = CellStore(data_dir / DB_NAME)
    results: list[PageResult] = []
    paths: dict[str, Path] = {}
    items: list[ChangeItem] = []
    report: dict = {}
    try:
        for competitor, page in pages.pages(competitors):
            res = PageResult(competitor, page.key, page.url, "failed")
            try:
                check_page(res, names.get(competitor, competitor), page, fetch=fetch, llm=llm,
                           snapshots=snapshots, cells=cells, run_id=run_id, now=now)
            except Exception as e:  # one page failing never stops the run
                log.warning("%s/%s failed: %s", competitor, page.key, e)
                res.status, res.error = "failed", f"{type(e).__name__}: {e}"
            results.append(res)

        report = build_report(run_id, results, llm is not None, now)
        if llm is not None:
            # the items file is built from the changes table, so items stored by a run that died before this point
            # are published now, under their original run_id
            items = cells.unpublished()
            report["recovered"] = sum(1 for i in items if i.run_id != run_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            paths = {"items": out_dir / f"{run_id}.jsonl", "report": out_dir / f"{run_id}.report.json"}
            paths["items"].write_text("".join(i.model_dump_json() + "\n" for i in items), encoding="utf-8")
            paths["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
            cells.mark_published([i.id for i in items], run_id)
    finally:
        snapshots.close()
        cells.close()
    return ChangesRun(run_id, results, report, paths, items)
