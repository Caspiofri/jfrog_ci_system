"""Health screen (D17, D21): the run funnel, silent sources, eval cards with n, coverage and change detection.

- Funnel: per source, from collection to routing, for one run (the latest by default): the daily funnel stored with the
  run, plus published / held_for_review at the current level for the items classified in that run.
- Silent sources: per source, the last item and the hours since, and "n runs so far". A source is "critical" when the
  latest run collected nothing from it and reported an error, "silent" when the latest MIN_RUNS_FOR_SILENT runs
  collected nothing from it; with fewer runs than that it is "healthy" or "critical" only, and says so.
- Extraction: per source and per publisher, the items whose page text was extracted (text_status full or partial)
  over the items kept, with n: for the run and for every stored item. snippet = only a teaser or nothing (the fetch
  failed or gave less than the teaser); junk = the page text was not the article. Why a fetch failed (e.g. HTTP 403
  from a Cloudflare challenge, a timeout, an empty page) is recorded per item from Oct 31 (fetch_status) and counted
  per row; earlier items show "not_recorded".
- Eval cards: every metric with its n. "untested" when n = 0; "weak" when n < WEAK_N, and always for the
  important-item metrics (few labels at score 4-5): the coverage check is the main evidence for not missing important
  events. Coverage is reported as counts with their n, never as a rate.
"""
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from ci import coverage, eval_golden, health_summary
from ci.api import service as svc

WEAK_N = 10
STALE_AFTER_H = 1.0  # D48: a run still "running" after this long was killed or hung
OVERDUE_AFTER_H = 26.0  # D48: the daily run is due every 24 h; no daily run for this long means one was missed
DAILY_KINDS = ("daily",)
MIN_RUNS_FOR_SILENT = 2
EVAL_REPORT_NAME = re.compile(r"\d{8}T\d{6}Z\.json")  # ci.eval_golden reports; not insights_*.json beside them
DEALS_CATEGORY = "Funding/M&A/Partnerships"
IMPORTANT_NOTE = ("few important labels ({important} of {n} non-noise labels score 4-5); the coverage check is the "
                  "main evidence for not missing important events")


def card(metric: str, value, n: int, note: str = "", always_weak: bool = False) -> dict:
    return {"metric": metric, "value": value, "n": n, "untested": n == 0, "weak": n == 0 or n < WEAK_N or always_weak,
            "note": note}


def label_summary(labels_path: Path) -> dict:
    """Counts from the golden set (read only): the n behind the weak / untested markers."""
    if not labels_path.exists():
        return {"total": 0, "non_noise": 0, "important": 0, "funding_m_and_a": 0}
    rows = list(eval_golden.latest_labels(labels_path).values())
    nn = [r for r in rows if not r.get("noise")]
    return {"total": len(rows), "non_noise": len(nn),
            "important": sum((eval_golden.label_score(r) or 0) >= eval_golden.IMPORTANT_MIN for r in nn),
            "funding_m_and_a": sum(r.get("category") == DEALS_CATEGORY for r in nn)}


def eval_cards(report: dict, labels: dict) -> list[dict]:
    m = report.get("metrics") or {}
    out = []
    for key in ("competitor", "category"):
        x = m.get(key) or {}
        out.append(card(f"{key}_accuracy", x.get("accuracy"), x.get("n", 0)))
    noise = m.get("noise") or {}
    out.append(card("noise_precision", noise.get("precision"), noise.get("tp", 0) + noise.get("fp", 0)))
    out.append(card("noise_recall", noise.get("recall"), noise.get("tp", 0) + noise.get("fn", 0)))
    score = m.get("score") or {}
    out.append(card("score_exact", score.get("exact"), score.get("n", 0)))
    out.append(card("score_within_1", score.get("within_1"), score.get("n", 0)))
    imp = m.get("important") or {}
    note = IMPORTANT_NOTE.format(important=labels["important"], n=labels["non_noise"])
    out.append(card("important_precision", imp.get("precision"), imp.get("precision_n", 0), note, always_weak=True))
    out.append(card("important_recall", imp.get("recall"), imp.get("recall_n", 0), note, always_weak=True))
    jf = m.get("mentions_jfrog") or {}
    out.append(card("mentions_jfrog_precision", jf.get("precision"), jf.get("tp", 0) + jf.get("fp", 0)))
    out.append(card("mentions_jfrog_recall", jf.get("recall"), jf.get("tp", 0) + jf.get("fn", 0)))
    out.append(card("funding_m_and_a", None, labels["funding_m_and_a"],
                    "untested: no Funding/M&A/Partnerships labels" if not labels["funding_m_and_a"] else ""))
    return out


EXTRACTED = ("full", "partial")
TEXT_STATUSES = ("full", "partial", "snippet", "junk")


def extraction_rows(raws: list[dict], key) -> list[dict]:
    """fetch: why the page text is or isn't there (ci.packet fetch_status); "not_recorded" before Oct 31."""
    groups: dict[str, Counter] = {}
    fetches: dict[str, Counter] = {}
    for r in raws:
        groups.setdefault(key(r), Counter())[r.get("text_status") or "snippet"] += 1
        fetches.setdefault(key(r), Counter())[r.get("fetch_status") or "not_recorded"] += 1
    rows = []
    for k, c in groups.items():
        n = sum(c.values())
        extracted = sum(c[x] for x in EXTRACTED)
        rows.append({"key": k, "extracted": extracted, "n": n, "rate": round(extracted / n, 3) if n else None,
                     "by_status": {x: c[x] for x in TEXT_STATUSES}, "fetch": dict(fetches[k].most_common())})
    return sorted(rows, key=lambda r: (-r["n"], r["key"]))


def extraction_block(raws: list[dict]) -> dict:
    extracted = sum((r.get("text_status") in EXTRACTED) for r in raws)
    return {"extracted": extracted, "n": len(raws), "rate": round(extracted / len(raws), 3) if raws else None,
            "fetch": dict(Counter(r.get("fetch_status") or "not_recorded" for r in raws).most_common()),
            "by_source": extraction_rows(raws, lambda r: r.get("source") or "?"),
            "by_publisher": extraction_rows(raws, lambda r: r.get("publisher") or svc.sources.host(r.get("url") or ""))}


def eval_reports(evals_dir) -> list[Path]:
    return [p for p in Path(evals_dir).glob("*.json") if EVAL_REPORT_NAME.fullmatch(p.name)]


def is_test_eval(report: dict) -> bool:
    return report.get("split") == "test" and bool(report.get("live")) and not report.get("aborted")


def newest(paths: list[Path]) -> Path | None:
    return max(paths, key=lambda p: (p.stat().st_mtime, p.name)) if paths else None  # ties: the timestamped name


# ---- the eval, test-split eval and change-detection blocks, from the saved reports (also what ci.health_summary
# copies into a demo snapshot, D83); each carries measured_on -------------------------------------------------------

def eval_summary_block(evals_dir, labels_path) -> dict:
    path = newest(eval_reports(evals_dir))
    labels = label_summary(Path(labels_path))
    if path is None:
        return {"status": "none", "labels": labels, "cards": eval_cards({}, labels), "measured_on": None}
    report = json.loads(path.read_text(encoding="utf-8"))
    return {"status": "ok", "report": path.name, "created_at": report.get("created_at"),
            "split": report.get("split"), "live": report.get("live"), "fingerprint": report.get("fingerprint"),
            "model": report.get("model"), "n": report.get("n"), "labels": labels,
            "test_eval_run": report.get("split") == "test" and bool(report.get("live")),
            "cards": eval_cards(report, labels), "measured_on": report.get("created_at")}


def test_eval_summary_block(evals_dir, labels_path) -> dict:
    """D23: the newest live test-split eval report; "none" until the one test eval has run."""
    tests = []
    for p in eval_reports(evals_dir):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if is_test_eval(r):
            tests.append((r.get("created_at") or "", p, r))
    if not tests:
        return {"status": "none", "note": "the test-split eval has not run (it runs once, on a frozen fingerprint)",
                "measured_on": None}
    _, path, r = max(tests, key=lambda t: t[0])
    return {"status": "ok", "report": path.name, "created_at": r.get("created_at"), "split": "test",
            "fingerprint": r.get("fingerprint"), "model": r.get("model"), "n": r.get("n"),
            "split_counts": r.get("split_counts"), "fallbacks": r.get("fallbacks"),
            "test_runs": len(tests), "metrics": r.get("metrics"),
            "cards": eval_cards(r, label_summary(Path(labels_path))), "measured_on": r.get("created_at")}


def change_summary_block(changes_out_dir) -> dict:
    """The newest change-detection report; age_hours is added when served (it depends on the clock)."""
    path = newest(list(Path(changes_out_dir).glob("*.report.json")))
    if path is None:
        return {"status": "none", "measured_on": None}
    r = json.loads(path.read_text(encoding="utf-8"))
    return {k: r.get(k) for k in ("run_id", "started_at", "live", "status", "pages", "fetched", "changes",
                                  "failures", "unconfirmed", "needs_review")} | {"measured_on": r.get("started_at")}


def _hours(now, ts: str | None) -> float | None:
    t = svc.parse_ts(ts) if ts else None
    return round((now - t).total_seconds() / 3600, 1) if t else None


def marker(run: dict, now) -> str:
    """ok | degraded | failed | stale: a run still marked running after STALE_AFTER_H is stale (killed or hung)."""
    if run["status"] == "running":
        age = _hours(now, run.get("processed_at") or run["started_at"])
        return "stale" if age is not None and age > STALE_AFTER_H else "running"
    return run["status"]


def liveness(runs: list[dict], now) -> dict:
    """D48: is the daily run alive? state = none | overdue | stale | failed | degraded | running | ok, worst first:
    overdue when the latest daily run started more than OVERDUE_AFTER_H ago, otherwise the latest run's marker.
    A run that never started at all leaves no row; overdue is how it shows."""
    daily = sorted((r for r in runs if r["kind"] in DAILY_KINDS), key=lambda r: r["started_at"])
    if not daily:
        return {"state": "none", "latest_run_id": None, "hours_since_latest": None, "stale_run_ids": [],
                "stale_after_hours": STALE_AFTER_H, "overdue_after_hours": OVERDUE_AFTER_H}
    latest = daily[-1]
    since = _hours(now, latest["started_at"])
    stale = [r["run_id"] for r in runs if marker(r, now) == "stale"]
    state = "overdue" if since is not None and since > OVERDUE_AFTER_H else marker(latest, now)
    return {"state": state, "latest_run_id": latest["run_id"], "latest_status": marker(latest, now),
            "hours_since_latest": since, "stale_run_ids": stale,
            "stale_after_hours": STALE_AFTER_H, "overdue_after_hours": OVERDUE_AFTER_H}


def register(app, d) -> None:
    """d: ok, snap, ApiError, now, runs_dir, evals_dir, coverage_dir, changes_out_dir, labels_path, events_path."""

    def pick_run(s: svc.Snapshot, run_id: str | None) -> dict:
        runs = sorted(s.runs, key=lambda r: r["started_at"])
        if not runs:
            raise d.ApiError(404, "not_found", "no runs in the store")
        if run_id is None:
            return runs[-1]
        found = next((r for r in runs if r["run_id"] == run_id), None)
        if found is None:
            raise d.ApiError(404, "not_found", f"no run {run_id}")
        return found

    def funnel(s: svc.Snapshot, run: dict) -> dict:
        report = json.loads(run["report"] or "{}")
        base = (report.get("funnel") or {}).get("sources", {})
        mine = [i for i, o in s.outputs.items() if o["run_id"] == run["run_id"]]
        routed: dict[str, Counter] = {}
        for i in mine:
            status = s.status(i)
            c = routed.setdefault(s.items[i]["source"], Counter())
            c["published"] += status in svc.PUBLISHED
            c["held_for_review"] += status == "awaiting_review"
        rows = []
        for source in sorted(set(base) | set(routed)):
            b = {k: v for k, v in base.get(source, {}).items() if k != "errors"}
            rows.append({"source": source, **b, "published": routed.get(source, Counter())["published"],
                         "held_for_review": routed.get(source, Counter())["held_for_review"],
                         "errors": base.get(source, {}).get("errors", [])})
        numeric = {k for r in rows for k, v in r.items() if isinstance(v, int)}
        totals = {k: sum(r.get(k, 0) for r in rows) for k in sorted(numeric)}
        return {"run_id": run["run_id"], "level": s.level, "sources": rows, "totals": totals}

    def silent(s: svc.Snapshot) -> dict:
        runs = sorted((r for r in s.runs if r["kind"] in svc.BRIEF_RUN_KINDS), key=lambda r: r["started_at"])
        per_run = []
        for r in runs:
            src = ((json.loads(r["report"] or "{}").get("funnel") or {}).get("sources")) or {}
            per_run.append((r, src))
        sources = sorted({k for _, src in per_run for k in src} | {i["source"] for i in s.items.values()})
        now = d.now()
        rows = []
        for source in sources:
            seen = [svc.parse_ts(sg["seen_at"]) for sg in s.sightings if s.items[sg["item_id"]]["source"] == source]
            last = max(seen) if seen else None
            recent = [src.get(source, {}) for _, src in per_run[-MIN_RUNS_FOR_SILENT:]]
            latest = recent[-1] if recent else {}
            if latest and not latest.get("collected") and latest.get("errors"):
                status = "critical"
            elif len(per_run) >= MIN_RUNS_FOR_SILENT and all(not x.get("collected") for x in recent):
                status = "silent"
            else:
                status = "healthy"
            rows.append({"source": source, "last_item": svc.iso(last),
                         "hours_silent": round((now - last).total_seconds() / 3600, 1) if last else None,
                         "collected_last_run": latest.get("collected"), "errors_last_run": latest.get("errors", []),
                         "status": status})
        n = len(per_run)
        return {"runs_so_far": n, "label": f"{n} run{'s' if n != 1 else ''} so far",
                "insufficient_history": n < MIN_RUNS_FOR_SILENT,
                "rule": f"silent = nothing collected in the last {MIN_RUNS_FOR_SILENT} runs; critical = nothing "
                        "collected and an error in the latest run", "items": rows}

    # D83: in demo mode every block below comes from the snapshot's saved summaries, never from output/
    demo_dir = getattr(d, "demo_dir", None)

    def eval_block() -> dict:
        if demo_dir is not None:
            return health_summary.served(demo_dir, "eval")
        return eval_summary_block(d.evals_dir, d.labels_path)

    def test_eval_block() -> dict:
        if demo_dir is not None:
            return health_summary.served(demo_dir, "test_eval")
        return test_eval_summary_block(d.evals_dir, d.labels_path)

    def coverage_block() -> dict:
        """Live: recomputed from the current events list (no file written) on the run of the newest coverage report.
        Demo: the saved summary, with the list label it was written with (D83)."""
        if demo_dir is not None:
            return health_summary.served(demo_dir, "coverage")
        path = newest(list(Path(d.coverage_dir).glob("*.json")))
        if path is None or not Path(d.events_path).exists():
            return {"status": "none"}
        run_id = path.stem
        kept_path = Path(d.runs_dir) / f"{run_id}.jsonl"
        if not kept_path.exists():
            return {"status": "none", "run_id": run_id}
        first, last, _ = coverage.run_window(run_id, Path(d.runs_dir))
        kept = [coverage.canonical_item(r) for r in coverage.read_jsonl(kept_path)]
        dropped_path = Path(d.runs_dir) / f"{run_id}.dropped.jsonl"
        dropped = [coverage.canonical_item(r) for r in coverage.read_jsonl(dropped_path)]
        rep = coverage.evaluate(coverage.load_events(Path(d.events_path)), kept, dropped, (first, last), None)

        def count(x: dict) -> dict:
            return {"captured": x.get("captured", 0), "n": x.get("events", 0)}

        return {"status": "ok", "run_id": run_id, "list": "dev (misses were found and fixed on it, so optimistic)",
                "measured_on": svc.iso(datetime.fromtimestamp(path.stat().st_mtime, UTC)),
                "window": rep.get("window"), "overall": count(rep["overall"]),
                "important": {**count(rep["high_importance"]), "min_score": rep["high_importance"].get("min")},
                "by_source_kind": {k: count(v) for k, v in rep.get("by_source_kind", {}).items()},
                "missed": rep.get("missed", [])}

    def change_block() -> dict:
        r = health_summary.served(demo_dir, "change_detection") if demo_dir is not None else \
            change_summary_block(d.changes_out_dir)
        if r.get("status") in ("none", "not_in_snapshot"):
            return r
        started = svc.parse_ts(r.get("started_at"))
        return r | {  # on the demo clock this can be negative: the UI then shows no age (D83)
            "age_hours": round((d.now() - started).total_seconds() / 3600, 1) if started else None}

    def with_after_actions(s: svc.Snapshot, row: dict) -> dict:
        """D74: the row as the run wrote it, plus items_after_actions, read now: the routing status of the items this
        run classified, at today's level and with analyst decisions (approve, dismiss, flag) applied. The row's own
        items.published / held stay the values at the end of the run. Null when the run had no routing (a
        reconstructed row leaves published and held empty), so no today's-rules number stands in for one."""
        items = row.get("items") or {}
        if items.get("published") is None:
            return {**row, "items_after_actions": None}
        c = Counter(s.status(i) for i, o in s.outputs.items() if o["run_id"] == row["run_id"])
        return {**row, "items_after_actions": {
            "published": sum(c[k] for k in svc.PUBLISHED), "held": c["awaiting_review"], "by_status": dict(c),
            "n": sum(c.values()), "level": s.level, "as_of": d.now().isoformat()}}

    @app.get("/api/v1/health")
    def get_health(run_id: str | None = None):
        store, s = d.snap()
        with store:
            run = pick_run(s, run_id)
            report = json.loads(run["report"] or "{}")
            body = {"run": {k: run[k] for k in ("run_id", "kind", "started_at", "finished_at", "status", "fingerprint",
                                                "model", "error")} | {"llm_calls": report.get("llm_calls"),
                                                                     "errors": report.get("errors", [])},
                    "funnel": funnel(s, run), "silent_sources": silent(s),
                    "extraction": {
                        "definition": "extracted = page text full or partial; n = items kept",
                        "run": {"run_id": run["run_id"], **extraction_block(
                            [s.items[sg["item_id"]]["raw"] for sg in s.sightings if sg["run_id"] == run["run_id"]])},
                        "all": extraction_block([i["raw"] for i in s.items.values()])}}
            metrics = store.run_metrics(run["run_id"])
        body |= {"liveness": liveness(s.runs, d.now()),
                 "run_metrics": with_after_actions(s, metrics[0]) if metrics else None, "eval": eval_block(),
                 "test_eval": test_eval_block(),
                 "coverage": coverage_block(), "change_detection": change_block()}
        return d.ok(body)

    @app.get("/api/v1/run-metrics")
    def list_run_metrics(limit: int = 50, offset: int = 0):
        """Per-run quality metrics (ci.run_metrics), newest run first."""
        store, s = d.snap()
        with store:
            rows = store.run_metrics()
        return d.ok(d.page([with_after_actions(s, r) for r in rows], limit, offset))

    @app.get("/api/v1/run-metrics/{run_id}")
    def get_run_metrics(run_id: str):
        store, s = d.snap()
        with store:
            rows = store.run_metrics(run_id)
        if not rows:
            raise d.ApiError(404, "not_found", f"no metrics for run {run_id}")
        return d.ok(with_after_actions(s, rows[0]))

    @app.get("/api/v1/evals/test")
    def get_test_eval():
        return d.ok(test_eval_block())

    @app.get("/api/v1/runs")
    def list_runs(limit: int = 50, offset: int = 0):
        store, s = d.snap()
        with store:
            rows = [{k: r[k] for k in ("run_id", "kind", "started_at", "finished_at", "status", "fingerprint", "model")}
                    | {"llm_calls": json.loads(r["report"] or "{}").get("llm_calls"), "marker": marker(r, d.now())}
                    for r in sorted(s.runs, key=lambda r: r["started_at"], reverse=True)]
        return d.ok(d.page(rows, limit, offset))
