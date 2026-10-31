"""Daily run: collect, store every kept item with its discovery time, classify and rank what is new, store the output.

    python -m ci.daily                     the scheduled run (cron, 06:00 Asia/Jerusalem, ci/daily_cron.sh)
    python -m ci.daily --from-run RUN_ID   no collection: import an existing run from output/runs/; its items keep
                                           that run's started_at as their discovery time

Every kept item goes into data/ci/ci.sqlite (ci.store). The items with no classification yet are classified and
ranked, and the output is stored with this run's id and the prompts+config fingerprint (ci.eval_golden.fingerprint,
the same one the eval logs, so a daily run and an eval with one fingerprint used the same prompts and config).

Items in the golden-set test split (evals/split_assignments.json, written by ci.eval_golden) skip the classifier and
the ranker until after the test eval (PRD D23, D31): they are stored, with a skip row, and no prediction is made for
them. Without the split file the run stops before any LLM call.

Every model answer and every final output is validated (ci.validate, D32): score 1-5 or noise, competitor and
category from the config lists, existing item ids. A rejection is logged with the item id and the reason, stored in
the rejections table, and its item is routed to review.

Exit codes: 0 ok; 1 failed (collection failed, the split file is missing, or a stage raised); 2 another collection
run holds the lock; 3 finished, but some classifier or ranker batches fell back, outputs were rejected, or a history
write failed.
"""
import argparse
import json
import logging
import sys
import traceback
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ci import config as ci_config
from ci import eval_golden, validate
from ci.classify import Classifier
from ci.dedupe import EmbeddingDeduper, SeenUrls
from ci.llm import GeminiLLM, JsonLLM
from ci.packet import Packet
from ci.pipeline import CI_DATA_DIR, NO_EMBEDDING_DEDUPE, RUNS_DIR, RunResult
from ci.pipeline import run as collect_run
from ci.rank import Ranker
from ci.runlock import RunLocked, run_lock
from ci.store import STORE_PATH, Store
from ci.validate import ValidatingLLM

log = logging.getLogger(__name__)

LOCK_NAME = "collect"  # shared with ci.run: one collection at a time
SPLIT_PATH = eval_golden.SPLIT_ASSIGNMENTS_PATH
TEST_SKIP = "golden-set test split: no prediction until after the test eval"
EXIT_OK, EXIT_FAILED, EXIT_LOCKED, EXIT_DEGRADED = 0, 1, 2, 3
FUNNEL_COLUMNS = ["collected", "dup_url", "dup_embedding", "kept", "known", "new", "test_skip", "to_model",
                  "rules", "llm", "fallback", "noise", "scored", "rank_degraded", "rejected"]


class SplitMissing(RuntimeError):
    """The test-split file does not exist, so test items cannot be kept away from the model."""


@dataclass
class DailyResult:
    run_id: str
    status: str  # ok | degraded | failed
    report: dict
    errors: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {"ok": EXIT_OK, "degraded": EXIT_DEGRADED}.get(self.status, EXIT_FAILED)


def held_out_ids(path: Path = SPLIT_PATH) -> set[str]:
    """Item ids on the test side of the frozen split. Item ids are the hash of the resolved URL (packet_id)."""
    if not path.exists():
        raise SplitMissing(f"{path} is missing: run ci.eval_golden once to freeze the split")
    return {i for i, side in eval_golden.load_assignments(path).items() if side == "test"}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_run(run_id: str, runs_dir: Path = RUNS_DIR) -> tuple[list[dict], dict]:
    """(kept rows, report) of a collection run already on disk."""
    report = json.loads((runs_dir / f"{run_id}.report.json").read_text(encoding="utf-8"))
    return _read_jsonl(runs_dir / f"{run_id}.jsonl"), report


def remember_history(rows: list[dict], data_dir: Path, embed_fn=None) -> list[str]:
    """Add imported items to the dedupe history (seen URLs, embeddings), so later runs drop them as already seen.
    Returns the errors; a failed write does not undo the import."""
    packets = [Packet.model_validate(r) for r in rows]
    errors = []
    seen = SeenUrls(data_dir / "seen_urls.sqlite")
    try:
        seen.add(packets)
    except Exception as e:
        errors.append(f"history write failed (seen URLs): {type(e).__name__}: {e}")
    finally:
        seen.close()
    try:
        EmbeddingDeduper(data_dir / "chroma", embed_fn).remember(
            [p for p in packets if p.source not in NO_EMBEDDING_DEDUPE])
    except Exception as e:
        errors.append(f"history write failed (embeddings): {type(e).__name__}: {e}")
    return errors


def funnel(rows: list[dict], report: dict, new: set[str], skips: dict[str, str], to_model: list[dict],
           classifications: list, ranked: list, rejections: list | None = None) -> dict:
    """Items per source per stage, from collection to the ranker; every count is an item count."""
    cls_by = {c.id: c for c in classifications}
    rank_by = {r.id: r for r in ranked}
    rejected = {r.item_id for r in rejections or []}
    by_source: dict[str, dict] = {}
    names = list(report.get("sources", {})) + sorted({r["source"] for r in rows} - set(report.get("sources", {})))
    for name in names:
        src = report.get("sources", {}).get(name, {})
        mine = [r for r in rows if r["source"] == name]
        sent = [r for r in to_model if r["source"] == name]
        cls = [cls_by[r["id"]] for r in sent if r["id"] in cls_by]
        rk = [rank_by[r["id"]] for r in sent if r["id"] in rank_by]
        methods = Counter(c.method for c in cls)
        by_source[name] = {
            "collected": src.get("collected", len(mine)), "dup_url": src.get("dup_url", 0),
            "dup_embedding": src.get("dup_embedding", 0), "kept": len(mine),
            "known": sum(r["id"] not in new for r in mine), "new": sum(r["id"] in new for r in mine),
            "test_skip": sum(r["id"] in skips for r in mine), "to_model": len(sent),
            "rules": methods["rules"], "llm": methods["llm"], "fallback": methods["fallback"],
            "noise": sum(c.noise for c in cls), "scored": sum(r.score is not None for r in rk),
            "rank_degraded": sum(r.degraded for r in rk), "rejected": sum(r["id"] in rejected for r in sent),
            "errors": list(src.get("errors", [])),
        }
    totals = {c: sum(s[c] for s in by_source.values()) for c in FUNNEL_COLUMNS}
    return {"sources": by_source, "totals": totals}


def format_funnel(report: dict) -> str:
    f = report["funnel"]
    header = ["source"] + FUNNEL_COLUMNS
    rows = [[n] + [s[c] for c in FUNNEL_COLUMNS] for n, s in f["sources"].items()]
    rows.append(["TOTAL"] + [f["totals"][c] for c in FUNNEL_COLUMNS])
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows, strict=True)]

    def line(cells: list) -> str:
        return "  ".join(str(c).rjust(w) if i else str(c).ljust(w)
                         for i, (c, w) in enumerate(zip(cells, widths, strict=True)))

    out = [f"daily {report['run_id']} ({report['kind']}) status={report['status']} "
           f"fingerprint={report['fingerprint']} model={report['model']} llm_calls={report['llm_calls']}",
           line(header), "-" * len(line(header)), *[line(r) for r in rows]]
    out += [f"  ! {n}: {e}" for n, s in f["sources"].items() for e in s["errors"]]
    out += [f"  !! {e}" for e in report["errors"]]
    return "\n".join(out)


class CountingLLM:
    """Counts the calls made through it, so the report says what the run cost."""

    def __init__(self, inner: JsonLLM):
        self.inner, self.calls = inner, 0
        self.model = getattr(inner, "model", type(inner).__name__)

    def complete(self, prompt: str, schema: dict) -> dict:
        self.calls += 1
        return self.inner.complete(prompt, schema)


def run_daily(*, from_run: str | None = None, cfg: ci_config.CIConfig | None = None, llm: JsonLLM | None = None,
              store_path: Path = STORE_PATH, runs_dir: Path = RUNS_DIR, data_dir: Path = CI_DATA_DIR,
              split_path: Path = SPLIT_PATH, collect: Callable[..., RunResult] = collect_run,
              embed_fn=None, days: int | None = None, fingerprint: str | None = None) -> DailyResult:
    cfg = cfg or ci_config.load()
    test_ids = held_out_ids(split_path)  # before any collection or LLM call
    errors: list[str] = []
    if from_run:
        rows, report = load_run(from_run, runs_dir)
        run_id, kind = from_run, "import"
    else:
        result = collect(cfg, days=days, runs_dir=runs_dir, data_dir=data_dir)
        report, run_id, kind = result.report, result.run_id, "daily"
        if result.failed:  # recorded in the store too, so a missed day is visible there and not only in the log
            reason = report.get("status_reason") or "collection failed"
            out = {"run_id": run_id, "kind": kind, "status": "failed", "error": reason, "collection": report}
            with Store(store_path) as store:
                store.start_run(run_id, kind, report["started_at"], "", "")
                store.finish_run(run_id, "failed", out, reason)
            return DailyResult(run_id, "failed", out, [reason])
        rows = [p.model_dump(mode="json") for p in result.kept]
        errors += report.get("pipeline_errors", [])
    started_at = report["started_at"]
    counting = CountingLLM(llm or GeminiLLM())
    fp = fingerprint or eval_golden.fingerprint(cfg)
    with Store(store_path) as store:
        store.start_run(run_id, kind, started_at, fp, counting.model)
        try:
            new = set(store.add_items(rows, run_id, started_at))
            if from_run:
                errors += remember_history(rows, data_dir, embed_fn)
            pending = set(store.unclassified(r["id"] for r in rows))
            skips = {r["id"]: TEST_SKIP for r in rows if r["id"] in pending and r["id"] in test_ids}
            to_model = [r for r in rows if r["id"] in pending and r["id"] not in skips]
            store.save_skips(run_id, skips)
            checked = ValidatingLLM(counting)  # D32: every answer row checked against the config lists
            classifications = Classifier(checked, cfg, runs_dir=runs_dir).classify(to_model) if to_model else []
            ranked = Ranker(checked).rank(to_model, classifications) if to_model else []
            sent = {r["id"] for r in to_model}
            rejections = checked.rejections + validate.check_outputs(sent, cfg, classifications, ranked)
            # an output for an id we never sent is not stored; every rejected item goes to review with its reason
            classifications = [c for c in classifications if c.id in sent]
            ranked = [r for r in ranked if r.id in sent]
            classifications, ranked = validate.route_to_review(rejections, classifications, ranked)
            store.save_outputs(run_id, fp, classifications, ranked)
            store.save_rejections(run_id, rejections)
        except Exception as e:
            out = {"run_id": run_id, "kind": kind, "status": "failed", "error": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()}
            store.finish_run(run_id, "failed", out, out["error"])
            return DailyResult(run_id, "failed", out, [out["error"]])
        fallbacks = sum(c.method == "fallback" for c in classifications) + sum(r.degraded for r in ranked)
        if fallbacks:
            errors.append(f"{fallbacks} classifier/ranker outputs fell back or are degraded (see the funnel)")
        if rejections:
            errors.append(f"{len(rejections)} model outputs rejected for {len({r.item_id for r in rejections})}"
                          " items (routed to review; see the rejections table)")
        status = "degraded" if errors else "ok"
        out = {"run_id": run_id, "kind": kind, "status": status, "started_at": started_at,
               "finished_at": datetime.now(UTC).isoformat(), "fingerprint": fp, "model": counting.model,
               "llm_calls": counting.calls, "errors": errors,
               "rejections": [vars(r) for r in rejections],
               "funnel": funnel(rows, report, new, skips, to_model, classifications, ranked, rejections)}
        store.finish_run(run_id, status, out, "; ".join(errors))
    (runs_dir / f"{run_id}.daily.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return DailyResult(run_id, status, out, errors)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.daily", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-run", help="import this run from output/runs/ instead of collecting")
    ap.add_argument("--days", type=int, help="collection window in days (overrides window_days in config)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        with run_lock(LOCK_NAME):
            result = run_daily(from_run=args.from_run, days=args.days)
    except RunLocked as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return EXIT_LOCKED
    except Exception as e:  # the split file, the store, a bad run id: visible in the log, non-zero exit
        print(f"FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        return EXIT_FAILED
    if "funnel" in result.report:
        print(format_funnel(result.report))
    if result.status != "ok":
        print(f"{result.status.upper()}: {'; '.join(result.errors)}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
