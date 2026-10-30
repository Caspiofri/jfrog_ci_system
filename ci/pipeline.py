"""CI run pipeline: collect -> stamp -> URL dedupe -> full text -> embedding dedupe -> JSONL + quality report."""
import importlib
import json
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from ci import contamination, extraction_quality
from ci.classify import MentionCounter
from ci.config import CIConfig
from ci.dedupe import Drop, EmbeddingDeduper, EmbedFn, SeenUrls, resolve_duplicates, url_dedupe
from ci.packet import CollectorResult, Packet, packet_id, utc_now, window_start
from config.settings import DATA_DIR, OUTPUT_DIR
from modules.reader import FULL_TEXT_MIN_CHARS, fetch_text

# source name -> collector module; imported lazily so one broken collector can't stop the others
COLLECTORS = {
    "google_news": "ci.collectors.google_news",
    "vendor_feed": "ci.collectors.vendor_feeds",
    "github_releases": "ci.collectors.github_releases",
    "hackernews": "ci.collectors.hackernews",
}
RUNS_DIR = OUTPUT_DIR / "runs"
CI_DATA_DIR = DATA_DIR / "ci"
COLLECTOR_TIMEOUT_S = 300
TEXT_MAX_CHARS = 6000
FETCH_WORKERS = 8
# distinct tags of one repo read as near-identical; their URLs are unique per tag, so URL dedupe is enough
NO_EMBEDDING_DEDUPE = {"github_releases"}
REPORT_COLUMNS = ["collected", "in_24h", "unresolved_urls", "dup_url", "dup_embedding", "kept",
                  "full", "partial", "snippet", "junk", "contaminated", "errors", "duration_s"]


@dataclass
class RunResult:
    run_id: str
    kept: list[Packet]
    dropped: list[dict]
    report: dict
    paths: dict[str, Path] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.report.get("status") == "failed"


def all_sources_failed(collected: dict[str, tuple[CollectorResult, float]]) -> bool:
    """Nothing collected and every source reported an error: an outage, not a quiet day."""
    return bool(collected) and all(res.errors and not res.packets for res, _ in collected.values())


def new_run_id(now: datetime | None = None) -> str:
    return f"{(now or utc_now()).strftime('%Y%m%dT%H%MZ')}-{uuid.uuid4().hex[:6]}"


def run_collectors(names: list[str], cfg: CIConfig, since: datetime, registry: dict[str, str],
                   timeout: float = COLLECTOR_TIMEOUT_S) -> dict[str, tuple[CollectorResult, float]]:
    """Each collector in its own daemon thread (a hung one is abandoned, never joined); failures become errors."""
    results: dict[str, tuple[CollectorResult, float]] = {}

    def work(name: str) -> None:
        start = time.monotonic()
        try:
            module = importlib.import_module(registry[name])
            res = module.collect(cfg, since)
        except Exception as e:  # missing module or a crash: isolated to this source
            res = CollectorResult(source=name, errors=[f"collector failed: {type(e).__name__}: {e}"])
        results[name] = (res, time.monotonic() - start)

    threads = {n: threading.Thread(target=work, args=(n,), daemon=True, name=f"ci-{n}") for n in names}
    for t in threads.values():
        t.start()
    deadline = time.monotonic() + timeout
    for name, t in threads.items():
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            results[name] = (CollectorResult(source=name, errors=[f"collector timed out after {timeout:g}s"]), timeout)
    return {n: results[n] for n in names}


def stamp(p: Packet, run_id: str, now: datetime) -> Packet:
    published = p.published_at
    if published and published.tzinfo is None:
        published = published.replace(tzinfo=UTC)
    in_24h = bool(published and published >= now - timedelta(hours=24))
    return p.model_copy(update={"id": packet_id(p.url), "run_id": run_id, "collected_at": now, "in_24h": in_24h,
                                "published_at": published})


def _skip_fetch(p: Packet) -> bool:
    unresolved_gnews = not p.url_resolved and (urlsplit(p.url).hostname or "").endswith("news.google.com")
    return p.text_status == "full" or unresolved_gnews


Counter = Callable[[str], tuple[dict[str, int], bool]]  # page text -> (mentions, mentions_jfrog); title excluded


def read_full_text(p: Packet, fetch: Callable[[str], str | None], count: Counter | None = None) -> Packet:
    """Replace the teaser with the page text when the page gives more; a failed fetch keeps the teaser.
    Mentions are counted over the whole page (or the teaser) before the text is capped at TEXT_MAX_CHARS.
    Page text that is not the article (ci.extraction_quality) is kept for inspection but marked "junk", with its
    reasons; mentions then come from the teaser, since nav menus name competitors."""
    text = None if _skip_fetch(p) else fetch(p.url)
    if not text or len(text) <= len(p.text):
        update = {"text": p.text[:TEXT_MAX_CHARS]}
        page = p.text
    else:
        status = "full" if len(text) >= FULL_TEXT_MIN_CHARS else "partial"
        update = {"text": text[:TEXT_MAX_CHARS], "text_status": status, "text_source": "page", "teaser": p.text}
        page = text
        quality = extraction_quality.assess(p.title, text)
        if not quality.ok:
            update |= {"text_status": "junk", "extraction_reasons": quality.reasons}
            page = p.text
    if count is not None:
        update["mentions"], update["mentions_jfrog"] = count(page)
        update["mentions_config"] = getattr(count, "config_hash", "")
    return p.model_copy(update=update)


def read_all(packets: list[Packet], fetch: Callable[[str], str | None], workers: int = FETCH_WORKERS,
             count: Counter | None = None) -> list[Packet]:
    if not packets:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: read_full_text(p, fetch, count), packets))


def _drop_rows(drops: list[Drop], stage: str) -> list[dict]:
    return [{**p.model_dump(mode="json"), "drop_stage": stage, "drop_reason": reason, "duplicate_of": dup}
            for p, reason, dup in drops]


def build_report(run_id: str, collected: dict[str, tuple[CollectorResult, float]], stamped: list[Packet],
                 kept: list[Packet], dropped: list[dict], meta: dict) -> dict:
    rows = {}
    dirty = contamination.by_source([p.model_dump(include={"id", "source", "title", "text"}) for p in kept],
                                    extra_titles=dropped)
    for name, (res, duration) in collected.items():
        mine = [p for p in stamped if p.source == res.source]
        k = [p for p in kept if p.source == res.source]
        d = [r for r in dropped if r["source"] == res.source]
        rows[name] = {
            "collected": len(mine),
            "in_24h": sum(p.in_24h for p in mine),
            "unresolved_urls": sum(not p.url_resolved for p in mine),
            "dup_url": sum(r["drop_stage"] == "url_dedupe" for r in d),
            "dup_embedding": sum(r["drop_stage"] == "embedding_dedupe" for r in d),
            "kept": len(k),
            **{s: sum(p.text_status == s for p in k) for s in ("full", "partial", "snippet", "junk")},
            # items whose text contains another item's title from this run: the extractor pulled in a neighbour
            "contaminated": dirty.get(res.source, {}).get("contaminated", 0),
            "contaminated_ids": dirty.get(res.source, {}).get("worst", []),
            "errors": list(res.errors),
            "duration_s": round(duration, 1),
        }
    totals = {c: sum(r[c] for r in rows.values()) for c in REPORT_COLUMNS if c not in ("errors", "duration_s")}
    totals["errors"] = sum(len(r["errors"]) for r in rows.values())
    totals["duration_s"] = round(meta.pop("duration_s"), 1)
    return {"run_id": run_id, **meta, "sources": rows, "totals": totals}


def format_report(report: dict) -> str:
    """The report as a fixed-width table, then each source's errors."""
    header = ["source"] + REPORT_COLUMNS
    rows = [[name] + [len(r[c]) if c == "errors" else r[c] for c in REPORT_COLUMNS]
            for name, r in report["sources"].items()]
    rows.append(["TOTAL"] + [report["totals"][c] for c in REPORT_COLUMNS])
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows, strict=True)]

    def line(cells: list) -> str:  # source name left-aligned, numbers right-aligned
        pairs = enumerate(zip(cells, widths, strict=True))
        return "  ".join(str(c).rjust(w) if i else str(c).ljust(w) for i, (c, w) in pairs)

    status = "  FAILED: " + report["status_reason"] if report.get("status") == "failed" else ""
    out = [f"run {report['run_id']}  (window {report['window_days']}d, fresh={report['fresh']}){status}",
           line(header), "-" * len(line(header))] + [line(r) for r in rows]
    for name, r in report["sources"].items():
        out += [f"  ! {name}: {e}" for e in r["errors"]]
        if r.get("contaminated_ids"):
            out.append(f"  ~ {name}: text holds another item's title: {', '.join(r['contaminated_ids'])}")
    out += [f"  !! pipeline: {e}" for e in report.get("pipeline_errors", [])]
    return "\n".join(out)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def run(cfg: CIConfig, *, sources: list[str] | None = None, fresh: bool = False, days: int | None = None,
        registry: dict[str, str] = COLLECTORS, runs_dir: Path = RUNS_DIR, data_dir: Path = CI_DATA_DIR,
        embed_fn: EmbedFn | None = None, fetch: Callable[[str], str | None] = fetch_text,
        collector_timeout: float = COLLECTOR_TIMEOUT_S) -> RunResult:
    started, t0 = utc_now(), time.monotonic()
    run_id = new_run_id(started)
    window = days if days is not None else cfg.window_days
    names = sources or list(registry)
    unknown = [n for n in names if n not in registry]
    if unknown:
        raise ValueError(f"unknown source(s) {unknown}; known: {list(registry)}")

    collected = run_collectors(names, cfg, window_start(window, started), registry, collector_timeout)
    stamped = [stamp(p, run_id, started) for res, _ in collected.values() for p in res.packets]
    errors: list[str] = []  # pipeline-stage failures (not a collector's); shown in the report

    seen = SeenUrls(data_dir / "seen_urls.sqlite")
    try:
        url_kept, url_drops = url_dedupe(stamped, None if fresh else seen)
        read = read_all(url_kept, fetch, count=MentionCounter(cfg))
        deduper = EmbeddingDeduper(data_dir / "chroma", embed_fn)
        embed_kept, emb_drops, embed_ok = _embedding_stage(deduper, read, fresh, errors)
        kept = embed_kept + [p for p in read if p.source in NO_EMBEDDING_DEDUPE]
        drops = resolve_duplicates(url_drops + emb_drops, {p.id for p in kept})
        n = len(url_drops)
        dropped = _drop_rows(drops[:n], "url_dedupe") + _drop_rows(drops[n:], "embedding_dedupe")

        runs_dir.mkdir(parents=True, exist_ok=True)
        failed = all_sources_failed(collected)
        # a failed run writes only its report: an empty <run_id>.jsonl would look like a good, quiet run
        outputs = (("report", ".report.json"),) if failed else \
            (("kept", ".jsonl"), ("dropped", ".dropped.jsonl"), ("report", ".report.json"))
        paths = {k: runs_dir / f"{run_id}{suffix}" for k, suffix in outputs}
        if not failed:
            _write_jsonl(paths["kept"], [p.model_dump(mode="json") for p in kept])
            _write_jsonl(paths["dropped"], dropped)
        meta = {"started_at": started.isoformat(), "window_days": window, "fresh": fresh,
                "status": "failed" if failed else "ok",
                "status_reason": "every source failed and nothing was collected" if failed else "",
                "pipeline_errors": errors}

        def write_report() -> dict:
            report = build_report(run_id, collected, stamped, kept, dropped,
                                  meta | {"duration_s": time.monotonic() - t0})
            paths["report"].write_text(json.dumps(report, indent=2), encoding="utf-8")
            return report

        report = write_report()
        # history only after every output exists; when the embedding stage failed, no embeddings are stored
        if _write_history(seen, url_kept, deduper, embed_kept if embed_ok else None, errors):
            report = write_report()  # again, now carrying the history error
    finally:
        seen.close()
    return RunResult(run_id, kept, dropped, report, paths)


def _embedding_stage(deduper: EmbeddingDeduper, packets: list[Packet], fresh: bool,
                     errors: list[str]) -> tuple[list[Packet], list[Drop], bool]:
    """Embedding dedupe; if it fails (model download, chromadb, embed_fn) every item is kept and the run goes on."""
    todo = [p for p in packets if p.source not in NO_EMBEDDING_DEDUPE]
    try:
        return *deduper.dedupe(todo, use_history=not fresh), True
    except Exception as e:
        errors.append(f"embedding dedupe failed: {type(e).__name__}: {e}; all {len(todo)} items kept")
        return todo, [], False


def _write_history(seen: SeenUrls, url_kept: list[Packet], deduper: EmbeddingDeduper,
                   embed_kept: list[Packet] | None, errors: list[str]) -> bool:
    """Seen URLs (including embedding-dropped items, so they don't resurface), then embeddings. True if one failed."""
    steps = [("seen URLs", lambda: seen.add(url_kept))]
    if embed_kept is not None:
        steps.append(("embeddings", lambda: deduper.remember(embed_kept)))
    failed = False
    for what, write in steps:
        try:
            write()
        except Exception as e:  # the run's outputs are already written; report, don't crash
            errors.append(f"history write failed ({what}): {type(e).__name__}: {e}")
            failed = True
    return failed
