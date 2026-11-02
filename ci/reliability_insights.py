"""Insights marking sheet (D54, D55): the insights a daily run's Brief stored, exported exactly as stored and marked
field by field on the review page, like the item sheet.

    python -m ci.reliability_insights export --run 20261101T0400Z-e9cae4

The export (output/reviews/insights_<run>.json) holds the stored generation verbatim, with the sha256 of the stored
row, plus a snapshot of every cited item: title, link, score, and the text the generator saw, so the sheet doesn't
change when the store does. Marks go to insights_<run>.marks.json, next to it. Nothing here writes to the store, the
item review file or its marks. The page shows what was generated and never suggests an answer.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from ci.api import service as svc
from ci.reliability import REVIEW_DIR
from ci.store import STORE_PATH, Store

SEEN_TEXT_CHARS = 600  # ci.insights.PROMPT_TEXT_CHARS when 9ec366312774 generated: the excerpt the model saw
MARKS = ("right", "wrong")
NOTE_MAX_CHARS = 2000
INSIGHT_FIELDS = (("pattern", "Pattern type"), ("title", "Title"), ("summary", "Summary"),
                  ("why_it_matters", "Why it matters"))
CLAIM_FIELDS = (("claim", "Claim is supported by the cited items"), ("cited", "The right items are cited"),
                ("quote", "Quote is from the item and supports the claim"),
                ("jfrog_quote", "JFrog quote is on the capability sheet and fits"))


def export_path(run_id: str, out_dir: Path = REVIEW_DIR) -> Path:
    return out_dir / f"insights_{run_id}.json"


def marks_path(run_id: str, out_dir: Path = REVIEW_DIR) -> Path:
    return out_dir / f"insights_{run_id}.marks.json"


def export_runs(out_dir: Path = REVIEW_DIR) -> list[str]:
    files = sorted((p for p in out_dir.glob("insights_*.json") if not p.name.endswith(".marks.json")
                    and p.stem.removeprefix("insights_")[:8].isdigit()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.stem.removeprefix("insights_") for p in files]


def _stored_row(store_path: Path, brief_date: str, generated_at: str | None) -> tuple[str, dict]:
    """The raw stored row (text exactly as in the store) of the Brief's generation."""
    con = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    try:
        sql = "SELECT data FROM insights WHERE brief_date = ?"
        args: tuple = (brief_date,)
        if generated_at:
            sql, args = sql + " AND generated_at = ?", (brief_date, generated_at)
        row = con.execute(sql + " ORDER BY generated_at DESC LIMIT 1", args).fetchone()
    finally:
        con.close()
    if row is None:
        raise ValueError(f"no stored insights for the {brief_date} Brief")
    return row[0], json.loads(row[0])


def export(run_id: str, store_path: Path = STORE_PATH, out_dir: Path = REVIEW_DIR,
           generated_at: str | None = None) -> Path:
    """Write the export of the insights stored for the Brief this run anchors. Refuses to overwrite an export."""
    path = export_path(run_id, out_dir)
    if path.exists():
        raise FileExistsError(f"{path} exists: an export is written once, so marks always refer to it")
    with Store(store_path) as store:
        run = store.run(run_id)
        if run is None:
            raise ValueError(f"no run {run_id} in the store")
        brief = svc.israel_date(svc.parse_ts(run["started_at"]))
        raw, stored = _stored_row(store_path, brief, generated_at)
        items = {i["item_id"]: i for i in store.all_items()}
        outputs = {o["item_id"]: o for o in store.outputs()}
    cited = {}
    for ins in stored.get("insights", []):
        for c in ins.get("claims", []):
            for i in dict.fromkeys([*c.get("item_ids", []), c.get("quote_item_id")]):
                if not i or i in cited:
                    continue
                it, out = items.get(i), outputs.get(i) or {}
                raw_item = (it or {}).get("raw") or {}
                text = raw_item.get("text") or ""
                cited[i] = None if it is None else {
                    "title": it["title"], "url": it["url"], "source": it["source"],
                    "publisher": raw_item.get("publisher") or "", "competitor": (out.get("classification") or {})
                    .get("competitor"), "category": (out.get("classification") or {}).get("category"),
                    "score": (out.get("ranking") or {}).get("score"), "published_at": it.get("published_at"),
                    "text_seen": text[:SEEN_TEXT_CHARS], "text_chars": len(text)}
    body = {"run_id": run_id, "brief_date": brief, "exported_at": datetime.now(UTC).isoformat(),
            "source": {"table": "insights", "brief_date": brief, "generated_at": stored.get("generated_at"),
                       "fingerprint": stored.get("fingerprint"), "model": stored.get("model"),
                       "data_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()},
            "stored": stored, "cited_items": cited,
            "note": "stored: the generation exactly as stored (parsed from the row whose sha256 is source.data_sha256);"
                    " cited_items: a snapshot taken at export time; score is the ranker's stored score"}
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def sheet(run_id: str, out_dir: Path = REVIEW_DIR) -> dict:
    """The page's data, read from the export only."""
    data = json.loads(export_path(run_id, out_dir).read_text(encoding="utf-8"))
    stored, cited = data["stored"], data["cited_items"]
    insights = []
    for ins in stored.get("insights", []):
        claims = []
        for n, c in enumerate(ins.get("claims", []), 1):
            items = [{"id": i, **(cited.get(i) or {"missing": True}),
                      "quote_here": i == c.get("quote_item_id")} for i in c.get("item_ids", [])]
            claims.append({"id": f"{ins['insight_id']}/c{n}", "n": n, "text": c.get("text"), "items": items,
                           "quote": c.get("quote"), "quote_item_id": c.get("quote_item_id"),
                           "jfrog_quote": c.get("jfrog_quote") or "",
                           "fields": [{"key": k, "label": lb} for k, lb in CLAIM_FIELDS
                                      if k != "jfrog_quote" or c.get("jfrog_quote")]})
        insights.append({"id": ins["insight_id"], "pattern": ins.get("pattern"), "title": ins.get("title"),
                         "summary": ins.get("summary"), "why_it_matters": ins.get("why_it_matters"),
                         "fields": [{"key": k, "label": lb, "value": ins.get(k)} for k, lb in INSIGHT_FIELDS],
                         "claims": claims})
    return {"run_id": run_id, "brief_date": data["brief_date"], "source": data["source"],
            "exported_at": data["exported_at"], "status": stored.get("status"), "window": stored.get("window"),
            "rejected": stored.get("rejected") or [], "insights": insights,
            "targets": {t["id"]: [f["key"] for f in t["fields"]]
                        for x in insights for t in (x, *x["claims"])}}


def load_marks(run_id: str, out_dir: Path = REVIEW_DIR) -> dict:
    p = marks_path(run_id, out_dir)
    return json.loads(p.read_text(encoding="utf-8")).get("marks", {}) if p.exists() else {}


def save_mark(run_id: str, target: str, field_name: str, mark: str | None, note: str,
              out_dir: Path = REVIEW_DIR) -> dict:
    """One field of one insight (target = insight id) or claim (target = '<insight id>/c<n>')."""
    targets = sheet(run_id, out_dir)["targets"]
    if target not in targets:
        raise ValueError(f"{target} is not an insight or claim of this export")
    if field_name not in targets[target]:
        raise ValueError(f"field must be one of {targets[target]}")
    if mark is not None and mark not in MARKS:
        raise ValueError(f"mark must be right, wrong or null, got {mark!r}")
    marks = load_marks(run_id, out_dir)
    saved = {"mark": mark, "note": (note or "").strip()[:NOTE_MAX_CHARS], "at": datetime.now(UTC).isoformat()}
    marks.setdefault(target, {})[field_name] = saved
    p = marks_path(run_id, out_dir)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps({"run_id": run_id, "marks": marks}, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.reliability_insights", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--run", required=True)
    e.add_argument("--generated-at", help="pick one generation when the Brief has several (default: the latest)")
    args = ap.parse_args(argv)
    path = export(args.run, generated_at=args.generated_at)
    s = sheet(args.run, path.parent)
    print(f"wrote {path}: {len(s['insights'])} insights, {sum(len(x['claims']) for x in s['insights'])} claims, "
          f"fingerprint {s['source']['fingerprint']}, stored row sha256 {s['source']['data_sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
