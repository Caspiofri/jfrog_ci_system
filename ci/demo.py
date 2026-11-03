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
The API in demo mode opens both files read-only, refuses every write with 403 demo_read_only, makes no LLM call,
freezes its clock at the snapshot time, and says "demo" with the snapshot date in every meta block. No value is
invented: everything in a snapshot comes from a real run.
"""
import argparse
import json
import sqlite3
import sys
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


def clock(manifest: dict):
    """Demo time stands still at the snapshot: the latest Brief is 'today', and Health shows no overdue run."""
    frozen = svc.parse_ts(manifest["as_of"]) if manifest.get("as_of") else datetime.now(UTC)
    return lambda: frozen


class ReadOnlyMiddleware:
    """Demo mode: every write answers 403 demo_read_only, before any route runs."""

    def __init__(self, app: ASGIApp, date: str | None = None):
        self.app, self.date = app, date

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method", "GET").upper() in UNSAFE:
            body = {"error": {"code": "demo_read_only", "message": f"Demo snapshot {self.date}: read-only, writes are "
                              "disabled", "details": {}}}
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
