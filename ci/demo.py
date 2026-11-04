"""Demo mode (D34, D59): the existing API serves a read-only snapshot of the real store, built with a field allowlist.

    python -m ci.demo build --out data/demo [--store data/ci/ci.sqlite] [--changes data/ci/changes.sqlite]
    python -m ci.api --demo data/demo

The snapshot has the live store's own format (ci.sqlite and changes.sqlite, same tables), so the API code is the
same; only these differ:
- items keep an allowlist of fields (ALLOWED_RAW). Full article text never goes in: `text` holds the 280-character
  excerpt the API would show anyway, and the number of characters the ranker read is kept as a count; the JFrog
  mention snippet (D77, at most 280 characters) is computed from the full text before the cut;
- local file paths (page snapshot files) are cleared;
- a manifest (snapshot.json) names the snapshot's date, its source runs and the commit it was built from.
The API in demo mode makes no LLM call (Refresh insights answers 403 insights_frozen_demo), freezes its clock at
the snapshot time, and says "demo" with the snapshot date in every meta block. No value is invented: everything in a
snapshot comes from a real run.

Writable demo (D111, the default): each start copies the snapshot stores into a new temporary folder (prepare()) and
every action writes only there, so a restart resets every action and the snapshot itself is never written. A guard
proves that opening the copy (the schema step and the store's repairs) changed 0 rows; if it cannot, or with
CI_DEMO_READ_ONLY=1, the demo serves the snapshot read-only (immutable) and refuses every write with 403
demo_read_only. Health, evaluation and run numbers always read the untouched snapshot, so actions never move them.
"""
import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ci import jfrog_mention, run_meta
from ci.api import service as svc
from ci.pipeline import CI_DATA_DIR

STORE_FILE, CHANGES_FILE, MANIFEST_FILE = "ci.sqlite", "changes.sqlite", "snapshot.json"
DEMO_DIR = CI_DATA_DIR.parent / "demo"
# D34: title, URL, dates, source, competitor, category, score, status, reason, our summary, a short excerpt. Category,
# score, status, reason and the summary live in their own tables; these are the item's own fields the API reads.
ALLOWED_RAW = ("id", "run_id", "url", "title", "source", "origin", "competitor", "publisher", "published_at",
               "published_at_source", "date_precision", "collected_at", "url_resolved", "text_status",
               "text_source", "fetch_status", "fetch_http_status", "extraction_reasons", "mentions_jfrog")
UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
COPY_PREFIX = "jessi-demo-"  # the per-start temporary copy: <tmp>/jessi-demo-XXXX/{ci,changes}.sqlite
LABELS_FILE = "analyst_labels.jsonl"  # Edit's candidate labels, inside the copy (live: evals/analyst_labels.jsonl)
READ_ONLY_ENV = "CI_DEMO_READ_ONLY"  # "1" / "true": serve the snapshot read-only, as before D111
# D111: the only writes a writable demo lets through. Each writes the temporary copy only (store, changes store or
# the copy's candidate-labels file); any other write answers 403 demo_read_only before a route runs.
WRITE_ROUTES = (
    ("POST", r"/api/v1/items/[^/]+/(approve|dismiss|reopen|flag)"),
    ("DELETE", r"/api/v1/items/[^/]+/flag"),
    ("PATCH", r"/api/v1/items/[^/]+"),
    ("PUT", r"/api/v1/settings/autonomy-level"),
    ("POST", r"/api/v1/sources/trust"),
    ("DELETE", r"/api/v1/sources/trust/[^/]+"),
    ("POST", r"/api/v1/changes/[^/]+/(approve|dismiss)"),
    ("PATCH", r"/api/v1/changes/[^/]+"),
)
INSIGHTS_REFRESH = re.compile(r"/api/v1/brief/[^/]+/insights/refresh")
INSIGHTS_FROZEN_MESSAGE = ("Insights are frozen in this demo: generating new ones needs a live LLM connection and API "
                           "key. They do not reflect changes made here.")
log = logging.getLogger("ci.demo")


def snapshot_raw(raw: dict) -> dict:
    """An item's raw fields as they go into a snapshot: the allowlist, the excerpt in place of the article."""
    out = {k: raw[k] for k in ALLOWED_RAW if k in raw}
    excerpt = svc.excerpt(raw)
    out["text"] = out["teaser"] = excerpt  # what content_text reads, whatever the text status
    out["chars_used_for_scoring"] = svc.text_basis(raw)["chars_used_for_scoring"]
    out[jfrog_mention.RAW_KEY] = jfrog_mention.find(raw)  # D77: from the full text, before the cut; <= 280 chars
    return out


def _copy(src: Path, dst: Path) -> None:
    a = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()


def build(out_dir: Path, store_path: Path, changes_path: Path | None = None, label: str | None = None) -> dict:
    """Write <out_dir>/ci.sqlite, changes.sqlite (when given) and snapshot.json; return the manifest. Refuses to
    overwrite an existing snapshot, so a frozen one stays frozen."""
    if (out_dir / MANIFEST_FILE).exists():
        raise FileExistsError(f"{out_dir} already holds a snapshot; build into a new directory")
    out_dir.mkdir(parents=True, exist_ok=True)
    store = out_dir / STORE_FILE
    _copy(store_path, store)
    db = sqlite3.connect(store)
    try:
        rows = db.execute("SELECT item_id, raw FROM items").fetchall()
        db.executemany("UPDATE items SET raw = ? WHERE item_id = ?",
                       [(json.dumps(snapshot_raw(json.loads(r)), ensure_ascii=False), i) for i, r in rows])
        cols = ("run_id", "kind", "started_at", "finished_at", "status")
        runs = [dict(zip(cols, r, strict=True))
                for r in db.execute(f"SELECT {', '.join(cols)} FROM runs ORDER BY started_at")]
        db.commit()
        db.execute("VACUUM")  # no freed page may still hold the old article text
    finally:
        db.close()
    if changes_path is not None and changes_path.exists():
        _copy(changes_path, out_dir / CHANGES_FILE)
        cdb = sqlite3.connect(out_dir / CHANGES_FILE)
        try:
            cdb.execute("UPDATE snapshots SET path = NULL")
            cdb.commit()
            cdb.execute("VACUUM")
        finally:
            cdb.close()
    ok = [r for r in runs if r["status"] in svc.BRIEF_RUN_STATUSES]
    latest = max(ok, key=lambda r: r["started_at"]) if ok else None
    as_of = (latest or {}).get("finished_at") or (latest or {}).get("started_at")
    manifest = {"date": svc.israel_date(svc.parse_ts(as_of)) if as_of else None, "as_of": as_of,
                "label": label or "", "built_at": datetime.now(UTC).isoformat(),
                "runs": [r["run_id"] for r in runs], "items": len(rows),
                "commit": run_meta.git_commit()["sha"], "allowlist": list(ALLOWED_RAW),
                "excerpt_chars": svc.EXCERPT_CHARS}
    (out_dir / MANIFEST_FILE).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    check(out_dir)
    return manifest


def check(snapshot_dir: Path) -> None:
    """Raise if any item in the snapshot carries a field off the allowlist or more text than the excerpt."""
    db = sqlite3.connect(f"file:{snapshot_dir / STORE_FILE}?mode=ro", uri=True)
    try:
        allowed = {*ALLOWED_RAW, "text", "teaser", "chars_used_for_scoring", jfrog_mention.RAW_KEY}
        for item_id, raw in db.execute("SELECT item_id, raw FROM items"):
            r = json.loads(raw)
            extra = set(r) - allowed
            if extra:
                raise ValueError(f"{item_id}: fields off the allowlist {sorted(extra)}")
            if len(r.get("text") or "") > svc.EXCERPT_CHARS or len(r.get("teaser") or "") > svc.EXCERPT_CHARS:
                raise ValueError(f"{item_id}: text longer than the excerpt")
            match = r.get(jfrog_mention.RAW_KEY)
            if match is not None and (set(match) != {"snippet", "found_in"}
                                      or len(match["snippet"]) > jfrog_mention.SNIPPET_CHARS):
                raise ValueError(f"{item_id}: JFrog mention snippet off its shape or longer than 280 characters")
    finally:
        db.close()


def load(snapshot_dir: Path) -> dict:
    """The manifest, with the snapshot's file paths, for create_app(demo=...)."""
    manifest = json.loads((snapshot_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    return {**manifest, "store_path": snapshot_dir / STORE_FILE, "changes_path": snapshot_dir / CHANGES_FILE}


def read_only_requested(env: dict[str, str] | None = None) -> bool:
    v = (os.environ if env is None else env).get(READ_ONLY_ENV, "")
    return v.strip().lower() in ("1", "true", "yes")


def table_digest(path: Path) -> dict[str, dict]:
    """Every table of a sqlite file: {table: {"rows": n, "sha256": hash of its rows, order-free}}. Opened
    immutable, so reading never writes the file."""
    db = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE "
                                          "'sqlite_%' ORDER BY name")]
        out = {}
        for t in names:
            cur = db.execute(f'SELECT * FROM "{t}"')
            cols = [c[0] for c in cur.description]
            rows = sorted(json.dumps([cols, list(r)], default=repr) for r in cur)
            out[t] = {"rows": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
        return out
    finally:
        db.close()


def changed_tables(before: dict[str, dict], after: dict[str, dict]) -> list[str]:
    """Tables whose rows differ; a table the schema step created counts only when it holds rows."""
    return sorted([t for t in before if after.get(t) != before[t]] +
                  [t for t in after if t not in before and after[t]["rows"]])


def guard(store_path: Path, changes_path: Path) -> dict:
    """D111: open the copy writable exactly as the API does (Store: schema + _repair_future_published(); CellStore:
    schema + legacy-key migrations) and prove it changed 0 rows. Returns {"ok", "tables", "rows", "changed"}."""
    from ci.changes.diff import CellStore
    from ci.store import Store

    files = [(store_path, lambda p: Store(p))]
    if changes_path.exists():
        files.append((changes_path, lambda p: CellStore(p)))
    report = {"ok": True, "tables": 0, "rows": 0, "changed": []}
    for path, opener in files:
        before = table_digest(path)
        opener(path)._db.close()
        after = table_digest(path)
        bad = changed_tables(before, after)
        report["tables"] += len(before)
        report["rows"] += sum(t["rows"] for t in before.values())
        report["changed"] += [f"{path.name}:{t}" for t in bad]
    report["ok"] = not report["changed"]
    return report


def prepare(snapshot_dir: Path, read_only: bool | None = None, tmp_root: Path | None = None) -> dict:
    """The demo manifest for create_app(demo=...). Writable (D111, default): a fresh copy of the snapshot stores in a
    new temporary folder, proven unchanged by guard(); the snapshot is only ever read. Read-only when asked
    (CI_DEMO_READ_ONLY=1) or when the copy or the guard fails: then it serves the snapshot itself, immutable."""
    m = load(snapshot_dir)
    m["snapshot_dir"] = Path(snapshot_dir)
    if read_only is None:
        read_only = read_only_requested()
    if read_only:
        log.info("demo: read-only, as set by %s", READ_ONLY_ENV)
        return m | {"writable": False, "read_only_reason": "setting"}
    try:
        root = Path(tmp_root or tempfile.gettempdir())
        for old in root.glob(COPY_PREFIX + "*"):  # earlier starts of this container: never reused
            shutil.rmtree(old, ignore_errors=True)
        copy_dir = Path(tempfile.mkdtemp(prefix=COPY_PREFIX, dir=root))
        store_copy, changes_copy = copy_dir / STORE_FILE, copy_dir / CHANGES_FILE
        shutil.copyfile(m["store_path"], store_copy)  # a byte copy: the source is opened for reading only
        if Path(m["changes_path"]).exists():
            shutil.copyfile(m["changes_path"], changes_copy)
        report = guard(store_copy, changes_copy)
    except Exception as e:  # noqa: BLE001 -- any failure falls back to the read-only demo, said in the log
        log.warning("demo: READ-ONLY, the writable copy failed: %s: %s", type(e).__name__, e)
        return m | {"writable": False, "read_only_reason": f"copy_failed: {type(e).__name__}"}
    if not report["ok"]:
        log.warning("demo: READ-ONLY, the startup guard found rows changed on the copy: %s", report["changed"])
        shutil.rmtree(copy_dir, ignore_errors=True)
        return m | {"writable": False, "read_only_reason": "guard_failed", "guard": report}
    log.info("demo: writable copy in %s; guard: 0 rows changed in %d tables (%d rows); restart resets every action",
             copy_dir, report["tables"], report["rows"])
    return m | {"writable": True, "read_only_reason": None, "guard": report, "copy_dir": copy_dir,
                "store_path": store_copy, "changes_path": changes_copy, "labels_out": copy_dir / LABELS_FILE}


def clock(manifest: dict):
    """Demo time stands still at the snapshot: the latest Brief is 'today', and Health shows no overdue run."""
    frozen = svc.parse_ts(manifest["as_of"]) if manifest.get("as_of") else datetime.now(UTC)
    return lambda: frozen


def allowed_write(method: str, path: str) -> bool:
    return any(m == method and re.fullmatch(p, path) for m, p in WRITE_ROUTES)


class ReadOnlyMiddleware:
    """Demo mode, before any route runs: Refresh insights answers 403 insights_frozen_demo (no LLM call, D111); any
    other write answers 403 demo_read_only, except, in a writable demo, the WRITE_ROUTES (they write the copy)."""

    def __init__(self, app: ASGIApp, date: str | None = None, writable: bool = False):
        self.app, self.date, self.writable = app, date, writable

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        method = scope.get("method", "GET").upper()
        if scope["type"] == "http" and method in UNSAFE:
            path = scope.get("path", "")
            if INSIGHTS_REFRESH.fullmatch(path):
                code, msg = "insights_frozen_demo", INSIGHTS_FROZEN_MESSAGE
            elif self.writable and allowed_write(method, path):
                await self.app(scope, receive, send)
                return
            else:
                code, msg = "demo_read_only", f"Demo snapshot {self.date}: read-only, writes are disabled"
            body = {"error": {"code": code, "message": msg, "details": {}}}
            await JSONResponse(body, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.demo", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build a snapshot from a store (no LLM call)")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--store", type=Path, default=CI_DATA_DIR / STORE_FILE)
    b.add_argument("--changes", type=Path, default=CI_DATA_DIR / CHANGES_FILE)
    b.add_argument("--label", help="a note kept in the manifest, e.g. why this day was chosen")
    c = sub.add_parser("check", help="check a snapshot against the allowlist")
    c.add_argument("dir", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        m = build(args.out, args.store, args.changes, args.label)
        print(f"wrote {args.out}: demo snapshot {m['date']}, {m['items']} items, runs {', '.join(m['runs'])}")
    else:
        check(args.dir)
        print(f"{args.dir}: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
