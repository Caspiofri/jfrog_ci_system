"""Per-run quality metrics: one row per daily run in the store's run_metrics table, written when the run ends.

Every number comes with its n. A row is written for ok, degraded and failed runs alike, so Health can see
where a run stopped (steps[].status) and how long each step took. A run stopped before the store opened (lock
held, missing split file) has no row; its exit code and message are only in output/logs/ci_daily.log.

metrics (the JSON column):
- items: collected, kept, new, test_skip, to_model, noise, non_noise; published / held at the level of the run's
  end (held = awaiting_review), with n = items classified in this run
- extraction: per source, extracted (text full or partial) of n kept, and the fetch statuses
- lens: ok / rejected / failed of n; quote_check passed / failed of n (n = items whose relation needs a quote);
  relations counted over the ok lenses
- insights: status, produced, rejected, the rejection reasons
- validation (D32): rejected outputs and items, by stage, with the reasons
- steps: per step, seconds, LLM calls and status (ok | degraded | failed | skipped) with the error and item ids
"""
import time
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime

EXTRACTED = ("full", "partial")
QUOTE_REASON = "capability quote"  # ci.lens.check: the reasons of a failed quote check start with this
ERROR_CHARS = 300


class Steps:
    """Wall time, LLM calls and outcome of each step of a run, in the order the steps ran."""

    def __init__(self, llm=None):
        self._llm = llm  # anything with .calls (daily.CountingLLM)
        self.steps: dict[str, dict] = {}

    def _calls(self) -> int:
        return getattr(self._llm, "calls", 0) if self._llm is not None else 0

    @contextmanager
    def step(self, name: str):
        t0, c0 = time.monotonic(), self._calls()
        entry = self.steps.setdefault(name, {"step": name, "status": "ok", "seconds": 0.0, "llm_calls": 0})
        try:
            yield entry
        except Exception as e:
            self.fail(name, f"{type(e).__name__}: {e}")
            raise
        finally:
            entry["seconds"] = round(entry["seconds"] + time.monotonic() - t0, 2)
            entry["llm_calls"] += self._calls() - c0

    def fail(self, name: str, error: str, item_ids: list[str] | None = None, status: str = "failed") -> None:
        entry = self.steps.setdefault(name, {"step": name, "status": "ok", "seconds": 0.0, "llm_calls": 0})
        if entry["status"] != "failed":
            entry["status"] = status
        entry.setdefault("errors", []).append(str(error)[:ERROR_CHARS])
        if item_ids:
            entry["item_ids"] = sorted(set(entry.get("item_ids", [])) | set(item_ids))

    def skip(self, name: str, reason: str) -> None:
        self.steps[name] = {"step": name, "status": "skipped", "seconds": 0.0, "llm_calls": 0, "reason": reason}

    def to_list(self) -> list[dict]:
        return list(self.steps.values())


def items_block(totals: dict, routed: list[str]) -> dict:
    """totals: the daily funnel totals; routed: the routing status of each item classified in this run."""
    c = Counter(routed)
    published = c["auto_published"] + c["approved"] + c["flagged"]
    to_model, noise = totals.get("to_model", 0), totals.get("noise", 0)
    return {k: totals.get(k, 0) for k in ("collected", "kept", "new", "test_skip", "to_model")} | {
        "noise": noise, "non_noise": to_model - noise,
        "published": published, "held": c["awaiting_review"], "routed_n": len(routed), "by_status": dict(c)}


def extraction_block(rows: list[dict]) -> dict:
    """Text extraction per source over the items this run kept: extracted (full or partial) of n."""
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r.get("source") or "?", {"extracted": 0, "n": 0, "fetch": Counter()})
        b["n"] += 1
        b["extracted"] += r.get("text_status") in EXTRACTED
        b["fetch"][r.get("fetch_status") or "not_recorded"] += 1
    out = {s: {"extracted": b["extracted"], "n": b["n"], "fetch": dict(b["fetch"].most_common())}
           for s, b in sorted(by.items())}
    return {"definition": "extracted = page text full or partial; n = items kept by this run",
            "extracted": sum(b["extracted"] for b in out.values()), "n": len(rows), "by_source": out}


def lens_block(rows: list[dict], status: str) -> dict:
    """rows: this run's lens rows (status, relation, reason). n of the quote check = items whose relation needs a
    quote: the ok ones with a relation other than not_related, plus the ones rejected by the quote check."""
    c = Counter(r["status"] for r in rows)
    ok = [r for r in rows if r["status"] == "ok"]
    passed = sum(r.get("relation") not in (None, "not_related") for r in ok)
    failed = sum(r["status"] == "rejected" and (r.get("reason") or "").startswith(QUOTE_REASON) for r in rows)
    return {"status": status, "n": len(rows), "ok": c["ok"], "rejected": c["rejected"], "failed": c["failed"],
            "quote_check": {"passed": passed, "failed": failed, "n": passed + failed},
            "relations": dict(Counter(r.get("relation") or "none" for r in ok).most_common()), "relations_n": len(ok),
            "rejected_reasons": [r.get("reason") for r in rows if r["status"] == "rejected"]}


def insights_block(report: dict) -> dict:
    x = report or {}
    return {"status": x.get("status", "disabled"), "produced": x.get("insights", 0), "rejected": x.get("rejected", 0),
            "rejected_reasons": x.get("rejected_reasons", []), "brief_date": x.get("brief_date"),
            "error": x.get("error") or None}


def validation_block(rejections: list) -> dict:
    """D32 rejections of this run (objects or dicts with item_id, stage, reason)."""
    rows = [r if isinstance(r, dict) else vars(r) for r in rejections]
    return {"outputs": len(rows), "items": len({r["item_id"] for r in rows}),
            "by_stage": dict(Counter(r["stage"] for r in rows).most_common()),
            "reasons": [{"item_id": r["item_id"], "stage": r["stage"], "reason": r["reason"]} for r in rows]}


def build(*, run_id: str, kind: str, status: str, started_at: str, fingerprints: dict, model: str | None,
          llm_calls: int, steps: Steps, items: dict | None = None, extraction: dict | None = None,
          lens: dict | None = None, insights: dict | None = None, validation: dict | None = None,
          error: str | None = None) -> dict:
    """The metrics row. Blocks a failed run never reached are None."""
    return {"run_id": run_id, "kind": kind, "status": status, "started_at": started_at,
            "finished_at": datetime.now(UTC).isoformat(), "fingerprints": fingerprints, "model": model,
            "llm_calls": llm_calls, "error": error, "items": items, "extraction": extraction, "lens": lens,
            "insights": insights, "validation": validation, "steps": steps.to_list()}
