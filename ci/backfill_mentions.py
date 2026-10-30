"""Backfill full-page mention counts for a run made before packets carried them.

    python -m ci.backfill_mentions <run_id> [--runs-dir DIR] [--workers 8]

Re-fetches each item's URL (reader.fetch_text, its own timeout) except where the stored text is already what
production counted (full items under the 6000-char cap) or production cannot fetch (unresolved news.google.com
redirects); those count their stored text. counts each tracked competitor's
names and JFrog's over the page (or the stored text when the fetch fails or gives less), and writes
<runs_dir>/<run_id>.mentions.json. The counts reflect the pages as re-fetched on the backfill date, not as they were
at run time. The run JSONL is only read, never modified.
"""
import argparse
import json
import sys
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from ci import config as ci_config
from ci.classify import MentionCounter
from ci.mentions import side_path, write_atomic
from ci.packet import Packet
from ci.pipeline import TEXT_MAX_CHARS, _skip_fetch
from config.settings import OUTPUT_DIR

RUNS_DIR = OUTPUT_DIR / "runs"
WORKERS = 8


def _default_fetch(url: str) -> str | None:
    """reader.fetch_text: the same extraction as the pipeline (related blocks stripped, then trafilatura)."""
    from modules.reader import fetch_text  # requests + trafilatura, only when actually fetching

    return fetch_text(url)


def _read_run(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("id"):
                rows.append(row)
    return rows


def production_skips(row: dict) -> bool:
    """Whether the stored text is already what production counted, so there is nothing to fetch.

    The pipeline's own rule (pipeline._skip_fetch) skips unresolved Google News redirects and items that are
    already full. But a stored row carries its status after the fetch, and production counts the page before the
    6000-char cap: a full item whose stored text reaches the cap was cut, so it is re-fetched to see the rest.
    """
    try:
        packet = Packet.model_validate(row)
    except Exception:  # a row that no longer validates is simply fetched
        return False
    if packet.text_status == "full" and len(packet.text) >= TEXT_MAX_CHARS:
        return False
    return _skip_fetch(packet)


def backfill(run_id: str, runs_dir: Path = RUNS_DIR, fetch: Callable[[str], str | None] = _default_fetch,
             cfg: ci_config.CIConfig | None = None, workers: int = WORKERS, now: datetime | None = None) -> dict:
    """Write the side file and return a summary, including how many items gained a competitor mention that the
    stored (capped) text did not have."""
    out_path = side_path(runs_dir, run_id)
    run_path = runs_dir / f"{run_id}.jsonl"
    if out_path is None or not run_path.exists():
        raise FileNotFoundError(f"no run file {run_path}")
    rows = _read_run(run_path)
    count = MentionCounter(cfg or ci_config.load())
    counted_on = (now or datetime.now(UTC)).date().isoformat()

    def one(row: dict) -> tuple[str, dict, list[str], bool]:
        stored = row.get("text") or ""
        skipped = production_skips(row)
        try:
            page = None if skipped else fetch(row.get("url") or "")
        except Exception:  # a fetch must never stop the backfill
            page = None
        fetched = bool(page) and len(page) > len(stored)
        mentions, jfrog = count(page if fetched else stored)
        before, jfrog_before = count(stored)
        gained = [k for k, n in mentions.items() if n and not before.get(k)]
        entry = {"mentions": mentions, "mentions_jfrog": jfrog, "fetched": fetched, "skipped": skipped,
                 "config": count.config_hash, "counted_on": counted_on}
        return row["id"], entry, gained, \
            jfrog and not jfrog_before

    with ThreadPoolExecutor(max_workers=workers) as pool:
        # rows whose text is the feed's own body are left out: production counted the whole body, the stored text
        # is capped, and their page would only add neighbouring entries; the pipeline's counts stand
        from_feed = [r for r in rows if r.get("text_source") == "feed"]
        results = list(pool.map(one, [r for r in rows if r.get("text_source") != "feed"]))
    side = {item_id: entry for item_id, entry, _, _ in results}
    write_atomic(out_path, json.dumps(side, ensure_ascii=False, indent=1) + "\n")
    gained = {item_id: keys for item_id, _, keys, _ in results if keys}
    return {"run_id": run_id, "items": len(rows), "counted_on": counted_on, "left_out_feed": len(from_feed),
            "skipped": sum(e["skipped"] for e in side.values()),
            "fetched": sum(e["fetched"] for e in side.values()),
            "gained_items": len(gained), "gained": gained,
            "gained_by_competitor": dict(Counter(k for keys in gained.values() for k in keys)),
            "jfrog_gained": sum(g for *_, g in results), "path": str(out_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args(argv)
    s = backfill(args.run_id, args.runs_dir, workers=args.workers)
    print(f"{s['run_id']}: {s['items']} items; {s['skipped']} not fetched (production skips them: stored text"
          f" counted), {s['fetched']} re-fetched with more text than stored")
    print(f"counts come from pages re-fetched on {s['counted_on']}, not as they were at run time")
    if s["left_out_feed"]:
        print(f"{s['left_out_feed']} feed-body items left out: the pipeline's own counts over the full body stand")
    print(f"{s['gained_items']} items gained a competitor mention missing from their stored text"
          f" {s['gained_by_competitor']}; {s['jfrog_gained']} gained a JFrog mention")
    print(f"wrote {s['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
