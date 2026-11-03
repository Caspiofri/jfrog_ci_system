"""The CI API v1 (docs/api-contract.md): Brief, Review and Log, plus meta and the item drawer.

    python -m ci.api [--port 8010]     binds 127.0.0.1 only (no auth in the demo, contract 2.1)

Competitors and Health come in the next step. Insights are served when stored; "Refresh insights" (D37) answers 409
until the setting insights_enabled is "true" (D37: not before Ofri's expected-insights file is saved).
"""
import json
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from ci import config as ci_config
from ci import coverage, eval_golden, insights, route, run_meta, sources
from ci import lens as lens_mod
from ci.api import competitors as competitors_api
from ci.api import health as health_api
from ci.api import service as svc
from ci.api.service import Snapshot
from ci.classify import CATEGORIES
from ci.csrf import CSRFMiddleware, TrustedHostMiddleware
from ci.pipeline import RUNS_DIR
from ci.store import STORE_PATH, Store
from config.settings import DATA_DIR, EVALS_DIR, OUTPUT_DIR

API_VERSION = "1"
CHANGES_PATH = DATA_DIR / "ci" / "changes.sqlite"
ANALYST_LABELS_PATH = EVALS_DIR / "analyst_labels.jsonl"  # candidates Ofri merges by hand (D31 Q4)
MAX_LIMIT = 200
Multi = Annotated[list[str] | None, Query()]  # a repeatable query filter (?competitor=a&competitor=b)
Badges = Annotated[list[Literal["new", "late"]] | None, Query()]
Kinds = Annotated[list[Literal["item", "change"]] | None, Query()]
Level = Literal["strict", "balanced", "relaxed"]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


class HoldReasonOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    detail: str
    held_at: list[str]


class ItemOut(BaseModel):
    """The contract's Item (§2). extra="forbid": a field that is not in the contract (article text) cannot leak."""
    model_config = ConfigDict(extra="forbid")
    item_id: str
    title: str
    url: str
    excerpt: str = Field(max_length=svc.EXCERPT_CHARS)
    source: str
    publisher: str
    publisher_host: str
    competitor: str
    classified: bool
    category: str | None
    noise: bool
    score: int | None
    urgency: str | None
    confidence: float | None
    mentions_jfrog: bool
    reason: str
    why_it_matters: str
    published_at: str | None
    date_precision: str
    published_at_source: str | None  # the source's own date when it was after our collection (else null)
    scheduled_for: str | None  # that date while it is still in the future: "scheduled for <date> per source"
    discovered_at: str | None
    discovery_lag_hours: float | None
    badge: Literal["new", "late"] | None
    status: str
    hold_reasons: list[HoldReasonOut]
    edited: dict | None
    flagged: bool
    version: int
    run_id: str | None
    fingerprint: str | None
    event_id: str | None
    lens: dict | None  # D42: {axis, capability_quote, relation, why_it_matters, why}; None when none passed its check
    lens_status: Literal["ok", "rejected", "failed"] | None  # the latest lens row's status; None when no lens row
    text_basis: "TextBasisOut"  # D39/D44
    jfrog_mention: "JfrogMentionOut | None"  # D77: None when mentions_jfrog is false


class JfrogMentionOut(BaseModel):
    """D77: where JFrog is mentioned, from the stored text with the mentions_jfrog pattern; a mention, not a
    comparison. snippet is at most 280 characters (D36); null when the mention is not in the stored text."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["found", "not_in_stored_text"]
    snippet: str | None = Field(max_length=280)
    found_in: Literal["title", "text"] | None


class TextBasisOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    source: str
    label: str
    reason: str | None
    reason_detail: list[str] | None
    chars_used_for_scoring: int


ItemOut.model_rebuild()

REFRESH_MARK = "insights_refreshing:"  # + Brief date -> the refresh's start time ("" when none is running)
REFRESH_STALE = timedelta(minutes=10)  # a mark older than this is a crashed refresh, not a running one


class Note(BaseModel):
    note: str | None = None


class Dismiss(BaseModel):
    reason: Literal["not_relevant", "wrong_competitor", "wrong_category", "duplicate"]
    note: str | None = None


EditField = Literal["competitor", "category", "score"]


class Edit(BaseModel):
    competitor: str | None = None
    category: str | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None  # for every changed field that has no note of its own in notes
    notes: dict[EditField, str] | None = None  # a note per changed field


class LevelBody(BaseModel):
    level: Literal["strict", "balanced", "relaxed"]


class TrustBody(BaseModel):
    host: str
    from_item_id: str | None = None
    note: str | None = None


def page(rows: list, limit: int, offset: int) -> dict:
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise ApiError(400, "bad_request", f"limit must be 1-{MAX_LIMIT} and offset >= 0")
    return {"total": len(rows), "limit": limit, "offset": offset, "items": rows[offset:offset + limit]}


def create_app(*, store_path: Path = STORE_PATH, runs_dir: Path = RUNS_DIR, changes_path: Path = CHANGES_PATH,
               labels_out: Path = ANALYST_LABELS_PATH, split_path: Path = eval_golden.SPLIT_ASSIGNMENTS_PATH,
               cfg: ci_config.CIConfig | None = None, now: Callable[[], datetime] = lambda: datetime.now(UTC),
               insights_llm: Callable[[], object] | None = None, embed_fn=None,
               evals_dir: Path = eval_golden.EVALS_OUT_DIR, coverage_dir: Path = coverage.COVERAGE_DIR,
               events_path: Path = coverage.EVENTS_PATH, changes_out_dir: Path = OUTPUT_DIR / "changes",
               labels_path: Path = eval_golden.LABELS_PATH, sheet_path: Path = lens_mod.SHEET_PATH,
               brief_config_path: Path = svc.BRIEF_CONFIG_PATH, demo: dict | None = None,
               trusted_hosts: frozenset[str] | None = None) -> FastAPI:
    """demo: a snapshot manifest from ci.demo.load(). The API then reads that snapshot read-only, refuses writes,
    calls no model and keeps its clock at the snapshot time (D34, D59)."""
    cfg = cfg or ci_config.load()
    min_score = svc.brief_min_score(brief_config_path)
    app = FastAPI(title="JFrog CI API", version=API_VERSION)
    app.add_middleware(CSRFMiddleware)  # no login, so a cross-site page must not change state
    app.add_middleware(TrustedHostMiddleware, hosts=trusted_hosts)  # outermost: DNS rebinding (D59)
    read_only = demo is not None
    if demo is not None:
        from ci import demo as demo_mod

        store_path, changes_path = demo["store_path"], demo["changes_path"]
        now, insights_llm, embed_fn = demo_mod.clock(demo), None, None
        app.add_middleware(demo_mod.ReadOnlyMiddleware, date=demo.get("date"))
    snapshot = None if demo is None else {k: demo.get(k) for k in ("date", "as_of", "label", "built_at", "commit")}

    def meta() -> dict:
        out = {"mode": "demo" if read_only else "live", "now": svc.iso(now()), "api_version": API_VERSION}
        return out | ({"snapshot": snapshot} if snapshot else {})

    def open_store() -> Store:
        return Store(store_path, read_only=read_only)

    def ok(body: dict) -> dict:
        return {**body, "meta": meta()}

    def snap() -> tuple[Store, Snapshot]:
        store = open_store()
        return store, Snapshot.read(store, cfg, now())

    def item_out(s: Snapshot, item_id: str, level: str | None = None, badge: str | None = None) -> dict:
        return ItemOut.model_validate(s.item(item_id, level, badge)).model_dump()

    @app.exception_handler(ApiError)
    async def api_error(_: Request, e: ApiError):
        return JSONResponse({"error": {"code": e.code, "message": e.message, "details": e.details}, "meta": meta()},
                            status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        return JSONResponse({"error": {"code": "validation_error", "message": "invalid request",
                                       "details": {"errors": json.loads(json.dumps(e.errors(), default=str))}},
                             "meta": meta()}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "error")
        return JSONResponse({"error": {"code": code, "message": str(e.detail), "details": {}}, "meta": meta()},
                            status_code=e.status_code)

    # ---- shared ------------------------------------------------------------------------------------------------

    @app.get("/api/v1/meta")
    def get_meta():
        store, s = snap()
        with store:
            anchors = s.anchors()
            runs = sorted(s.runs, key=lambda r: r["started_at"])
        return ok({**svc.meta_lists(cfg), "level": s.level, "latest_brief_date": anchors[-1][0] if anchors else None,
                   "latest_run_id": runs[-1]["run_id"] if runs else None,
                   "insights_enabled": insights_enabled()})

    @app.get("/api/v1/items/{item_id}")
    def get_item(item_id: str):
        store, s = snap()
        with store:
            if item_id not in s.items:
                raise ApiError(404, "not_found", f"no item {item_id}")
            out = s.outputs.get(item_id)
            body = {"item": item_out(s, item_id),
                    "classification": {k: out["classification"].get(k) for k in
                                       ("method", "reason", "degraded", "competitor_confirmed")} if out else None,
                    "ranking": {k: out["ranking"].get(k) for k in ("raw_score", "adjustments", "degraded")}
                    if out else None,
                    "sightings": [x for x in s.sightings if x["item_id"] == item_id],
                    "rejections": s.rejections.get(item_id, []),
                    "skip": s.skips.get(item_id),
                    "actions": store.actions(item_id)}
        return ok(body)

    # ---- Brief -------------------------------------------------------------------------------------------------

    def insights_enabled() -> bool:
        with open_store() as store:
            return store.setting("insights_enabled", "false") == "true"

    def brief_counts(s: Snapshot, w: dict) -> dict:
        ids = s.brief_ids(w)
        badges = Counter(s.badge(i, w) for i in ids)
        scores = [s.item(i)["score"] for i in ids]
        held = [i for i in s.classified_ids()
                if w["prev_anchor"] < svc.parse_ts(s.items[i]["discovered_at"]) <= w["anchor"]
                and s.status(i) == "awaiting_review"]
        return {"items": len(ids), "new": badges["new"], "found_late": badges["late"], "awaiting_review": len(held),
                "important": sum((x or 0) >= 4 for x in scores),
                "mentions_jfrog": sum(s.item(i)["mentions_jfrog"] for i in ids),
                "by_urgency": dict(Counter(svc.URGENCY.get(x) for x in scores if x))}

    def refreshing(store: Store, date: str) -> bool:
        started = svc.parse_ts(store.setting(REFRESH_MARK + date, "") or None)
        return started is not None and now() - started < REFRESH_STALE

    def insights_state(enabled: bool, stored: dict | None, kept: list, running: bool) -> str:
        """D44: disabled | refreshing | not_run | failed | none_passed | ok (no internal ids in what the UI shows)."""
        if not enabled:
            return "disabled"
        if running:
            return "refreshing"
        if stored is None:
            return "not_run"
        if stored.get("status") == "failed":
            return "failed"
        return "ok" if kept else "none_passed"

    @app.get("/api/v1/briefs")
    def list_briefs(limit: int = 50, offset: int = 0):
        store, s = snap()
        with store:
            rows = []
            for date, run in reversed(s.anchors()):
                w = s.window(date)
                c = brief_counts(s, w)
                _, summary = s.brief_summary(w, min_score)
                rows.append({"date": date, "anchor_run_id": run["run_id"], "anchor_kind": run["kind"],
                             "published": summary["published"], "published_high": summary["published_high"],
                             "held": summary["held"], "held_high": summary["held_high"],
                             "items": c["items"],  # deprecated (D44): every published item, whatever the score
                             "found_late": c["found_late"], "awaiting_review": c["awaiting_review"]})
        return ok(page(rows, limit, offset))

    @app.get("/api/v1/brief")
    def get_brief(date: str | None = None, competitor: Multi = None, category: Multi = None,
                  badge: Badges = None, limit: int = 50, offset: int = 0):
        store, s = snap()
        with store:
            anchors = s.anchors()
            if not anchors:
                raise ApiError(404, "not_found", "no Brief yet: no successful daily run in the store")
            date = date or anchors[-1][0]
            w = s.window(date)
            if w is None:
                return ok({"date": date, "status": "missing", "window": None, "brief_min_score": min_score,
                           "summary": None, "counts": None, "kpis": [],
                           "insights": {"status": "missing", "items": [], "rejected": 0}, "intensity": None,
                           "items": page([], limit, offset)})
            listed, summary = s.brief_summary(w, min_score)
            rows = [item_out(s, i, badge=s.badge(i, w)) for i in listed]
            rows = [r for r in rows if (not competitor or r["competitor"] in competitor)
                    and (not category or r["category"] in category) and (not badge or r["badge"] in badge)]
            rows.sort(key=svc.sort_key)
            counts = brief_counts(s, w)
            prev = brief_counts(s, s.window(w["prev_date"])) if w["prev_date"] else None
            kpis = [{"key": k, "value": counts[k], "prev": prev[k] if prev else None}
                    for k in ("items", "important", "found_late", "mentions_jfrog")]
            stored = store.latest_insights(date)
            enabled = insights_enabled()
            # D44: status is the state the UI shows; the generator's own status stays as generator_status, and the
            # rejection reasons stay in the stored generation (Health), the Brief carries only their count
            state = insights_state(enabled, stored, (stored or {}).get("insights") or [], refreshing(store, date))
            if stored:
                generated = [cite(s, x, set(listed)) for x in stored.pop("insights", [])]
                ins = {**stored, "generator_status": stored.get("status"), "status": state, "items": generated,
                       "enabled": enabled, "rejected": len(stored.get("rejected") or [])}
            else:
                ins = {"status": state, "generator_status": None, "items": [], "enabled": enabled, "rejected": 0}
            body = {"date": date, "status": "ok", "brief_min_score": min_score, "summary": summary,
                    "window": {"prev_anchor": svc.iso(w["prev_anchor"]), "anchor": svc.iso(w["anchor"]),
                               "anchor_run_id": w["anchor_run_id"], "anchor_kind": w["anchor_kind"],
                               "hours": round((w["anchor"] - w["prev_anchor"]).total_seconds() / 3600, 2),
                               "tz": "Asia/Jerusalem"},
                    "counts": counts, "kpis": kpis, "insights": ins, "intensity": intensity(s, w),
                    "level": s.level, "items": page(rows, limit, offset)}
        return ok(body)

    def cite(s: Snapshot, insight: dict, listed: set[str]) -> dict:
        """D50: an insight lists the items it cites, each with its score and a link, so a cited item that isn't in
        the Brief (scored 1-2, or held since) can still be opened."""
        rows = []
        for i in insight.get("item_ids") or []:
            if i not in s.items:
                continue
            x = s.item(i)
            rows.append({"item_id": i, "title": x["title"], "score": x["score"], "url": x["url"],
                         "status": s.status(i), "in_brief": i in listed})
        return {**insight, "cited_items": rows}

    def intensity(s: Snapshot, w: dict, days: int = 14) -> dict:
        """Per discovery day (Israel date, D36 Q-E): sum of scores and count of published non-noise items."""
        end = w["anchor"].astimezone(svc.TZ).date()
        series = {(end - timedelta(days=d)).isoformat(): {"score": 0, "items": 0} for d in range(days - 1, -1, -1)}
        for i in s.classified_ids():
            day = svc.israel_date(svc.parse_ts(s.items[i]["discovered_at"]))
            if day in series and s.status(i) in svc.PUBLISHED:
                series[day]["score"] += s.item(i)["score"] or 0
                series[day]["items"] += 1
        return {"days": days, "by": "discovery_day", "series": [{"date": d, **v} for d, v in series.items()]}

    @app.post("/api/v1/brief/{date}/insights/refresh")
    def refresh_insights(date: str):
        if not insights_enabled():
            raise ApiError(409, "insights_disabled", "insights are not enabled yet (they wait for the "
                                                     "expected-insights file)")
        store, s = snap()
        with store:
            w = s.window(date)
            if w is None:
                raise ApiError(404, "not_found", f"no Brief for {date}")
            rows = [insights.item_from_output(s.outputs[i]) for i in s.classified_ids()
                    if s.status(i) in svc.PUBLISHED]
            if insights_llm is None:
                raise ApiError(503, "llm_unavailable", "no insights model configured")
            if refreshing(store, date):
                raise ApiError(409, "refresh_running", f"insights for {date} are already being refreshed")
            store.set_setting(REFRESH_MARK + date, svc.iso(now()))  # the Brief shows insights_status "refreshing"
            try:
                llm_obj = insights_llm()
                try:
                    res = insights.generate(rows, llm_obj, embed_fn, anchor=w["anchor"],
                                            prev_anchor=w["prev_anchor"], level=s.level, trigger="refresh", now=now,
                                            sheet=lens_mod.load_sheet(sheet_path))
                except Exception as e:  # the earlier generation stays on the Brief
                    raise ApiError(502, "insights_failed", f"insights generation failed: {type(e).__name__}: "
                                                           f"{str(e)[:200]}") from e
                store.save_insights(date, {**res.to_json(), "metadata": run_meta.safe_collect(
                    model=getattr(llm_obj, "model", None))})
            finally:
                store.set_setting(REFRESH_MARK + date, "")
        return ok({"date": date, "status": res.status, "insights": len(res.insights), "rejected": len(res.rejected),
                   "generated_at": res.generated_at})

    # ---- Review ------------------------------------------------------------------------------------------------

    def in_dates(s: Snapshot, item_id: str, date_from: str | None, date_to: str | None) -> bool:
        day = svc.israel_date(svc.parse_ts(s.items[item_id]["discovered_at"]))
        return (not date_from or day >= date_from) and (not date_to or day <= date_to)

    def level_block(s: Snapshot, ids: list[str]) -> list[dict]:
        nonnoise = [i for i in ids if not s.outputs[i]["classification"]["noise"]]
        reasons = {i: s.reasons(i) for i in nonnoise}
        return [{"level": lv, "held": sum(route.is_held(r, lv) for r in reasons.values()),
                 "published": sum(not route.is_held(r, lv) for r in reasons.values()), "n": len(nonnoise)}
                for lv in route.LEVELS]

    def change_rows(competitor: list[str] | None) -> list[dict]:
        rows = competitors_api.awaiting_change_rows(changes_path, read_only=read_only)
        return [r for r in rows if not competitor or r["competitor"] in competitor]

    @app.get("/api/v1/review")
    def get_review(level: Level | None = None, reason: Multi = None,
                   competitor: Multi = None, date_from: str | None = None, date_to: str | None = None,
                   brief: str | None = None, kind: Kinds = None, limit: int = 50, offset: int = 0):
        store, s = snap()
        with store:
            lv = level or s.level
            w = s.window(brief) if brief else None
            if brief and w is None:
                raise ApiError(404, "not_found", f"no Brief for {brief}")
            base = s.window_ids(w) if w else s.classified_ids()  # D44: the Brief links to its own window's held items
            scope = [i for i in base if in_dates(s, i, date_from, date_to)
                     and (not competitor or s.item(i)["competitor"] in competitor)]
            held = [i for i in scope if s.status(i, lv) == "awaiting_review"]
            backlog_total = sum(s.status(i, lv) == "awaiting_review" for i in s.classified_ids())
            reasons_at = {i: [r for r in s.reasons(i) if lv in r.held_at] for i in held}
            if reason:
                held = [i for i in held if any(r.code in reason for r in reasons_at[i])]
            counts = Counter(r.code for i in held for r in reasons_at[i])
            rows = []
            for i in held:
                it = item_out(s, i, lv)
                forced = any(set(r.held_at) == set(route.LEVELS) for r in reasons_at[i])
                rows.append(({"kind": "item", "item": it, "held_since": it["discovered_at"],
                              "trust_source": s.trust_info(s.items[i]["url"])}, forced))
            rows.sort(key=lambda x: (not x[1], -(x[0]["item"]["score"] or 0), x[0]["held_since"] or ""))
            out = [r for r, _ in rows] if not kind or "item" in kind else []
            # changed cells belong to no Brief window: listed only in the unfiltered queue
            changes = change_rows(competitor) if (not kind or "change" in kind) and not w else []
            if changes:
                counts["changed_cell"] += len(changes)
            body = {"level": lv, "levels": level_block(s, scope),
                    "scope": {"brief": brief,
                              "window": {"prev_anchor": svc.iso(w["prev_anchor"]), "anchor": svc.iso(w["anchor"])}
                              if w else None,
                              "date_from": date_from, "date_to": date_to, "competitor": competitor},
                    "counts_by_reason": dict(counts), **page(changes + out, limit, offset),
                    "backlog_total": backlog_total}
        return ok(body)

    @app.get("/api/v1/settings/autonomy-level")
    def get_level(preview: Literal["strict", "balanced", "relaxed"] | None = None):
        store, s = snap()
        with store:
            body = {"level": s.level, "preview": preview, "levels": level_block(s, s.classified_ids()),
                    "default": route.DEFAULT_LEVEL}
        return ok(body)

    @app.put("/api/v1/settings/autonomy-level")
    def put_level(body: LevelBody):
        with open_store() as store:
            store.set_autonomy_level(body.level)
        return get_level()

    # ---- actions (D16) -------------------------------------------------------------------------------------------

    def act(item_id: str, action: str, allowed: tuple[str, ...], update: Callable[[dict, str], dict],
            if_match: str | None, reason: str | None = None, note: str | None = None,
            measures: Callable[[dict], str] = lambda it: "",
            extra: Callable[[dict, list[dict]], dict] = lambda before, history: {}) -> dict:
        """extra(item before, the item's actions so far): more payload for the action row, read in the same
        snapshot as the checks."""
        store, s = snap()
        with store:
            if item_id not in s.items:
                raise ApiError(404, "not_found", f"no item {item_id}")
            before = s.item(item_id)
            if before["status"] not in allowed:
                raise ApiError(409, "conflict", f"cannot {action} an item that is {before['status']}",
                               {"status": before["status"], "allowed_from": list(allowed)})
            try:
                expect = int(if_match) if if_match is not None else None
            except ValueError:
                raise ApiError(400, "bad_request", "If-Match must be the item version (an integer)") from None
            state = s.states.get(item_id) or {}
            more = extra(before, store.actions(item_id))
            try:
                res = store.apply_item_action(item_id, action, update(state, before["status"]), reason=reason,
                                              note=note, payload={"before": {k: before[k] for k in
                                                                            ("status", "competitor", "category",
                                                                             "score", "flagged")},
                                                                  # the stored decision and flag, so reopen can
                                                                  # restore them exactly
                                                                  "state_before": {
                                                                      "decision": state.get("decision"),
                                                                      "flagged": int(state.get("flagged") or 0)},
                                                                  "measures": measures(before), **more},
                                              expect_version=expect)
            except ValueError:
                raise ApiError(409, "conflict", "the item changed since you read it (If-Match)",
                               {"version": state.get("version", 0)}) from None
            after = Snapshot.read(store, cfg, now()).item(item_id)
        return ok({"action_id": res["action_id"], "target_kind": "item", "target_id": item_id, "action": action,
                   "reason": reason, "status": after["status"], "flagged": after["flagged"],
                   "version": after["version"], "measures": measures(before), "at": res["at"]})

    @app.post("/api/v1/items/{item_id}/approve")
    def approve(item_id: str, body: Note | None = None, if_match: str | None = Header(default=None)):
        return act(item_id, "approve", ("awaiting_review",), lambda st, _: {"decision": "approved"}, if_match,
                   note=body.note if body else None, measures=lambda it: "confirmed")

    @app.post("/api/v1/items/{item_id}/dismiss")
    def dismiss(item_id: str, body: Dismiss, if_match: str | None = Header(default=None)):
        stage = {"wrong_competitor": "classifier", "wrong_category": "classifier", "not_relevant": "noise_filter",
                 "duplicate": "dedupe"}[body.reason]
        return act(item_id, "dismiss", ("awaiting_review", "auto_published", "approved", "flagged"),
                   lambda st, _: {"decision": "dismissed", "flagged": 0}, if_match, reason=body.reason,
                   note=body.note, measures=lambda it: stage)

    def restore_before_dismiss(history: list[dict]) -> tuple[dict, dict]:
        """(item_state update, the dismiss action) from the item's latest dismiss. A dismiss logged with state_before
        is restored exactly; an older one from its before status (approved -> approved; flagged -> flagged;
        awaiting_review or auto_published -> no decision, so routing decides again)."""
        dismiss = next((a for a in reversed(history) if a["action"] == "dismiss"), None)
        if dismiss is None:
            raise ApiError(409, "conflict", "no dismiss action to reopen")
        sb = dismiss["payload"].get("state_before")
        if sb is not None:
            return {"decision": sb["decision"], "flagged": int(sb["flagged"])}, dismiss
        st = dismiss["payload"]["before"]["status"]
        return {"decision": "approved" if st == "approved" else None, "flagged": int(st == "flagged")}, dismiss

    @app.post("/api/v1/items/{item_id}/reopen")
    def reopen(item_id: str, body: Note | None = None, if_match: str | None = Header(default=None)):
        """Undo a dismiss: a new 'reopen' action (the dismiss stays in the history) puts the decision and flag back
        as they were before it. Edits are kept; nothing goes to the candidate-labels file."""
        found: dict = {}

        def extra(before: dict, history: list[dict]) -> dict:
            found["update"], found["dismiss"] = restore_before_dismiss(history)
            return {"reopens_action_id": found["dismiss"]["action_id"],
                    "status_before_dismiss": found["dismiss"]["payload"]["before"]["status"]}

        res = act(item_id, "reopen", ("dismissed",), lambda st, _: found["update"], if_match,
                  note=body.note if body else None, extra=extra)
        return {**res, "reopens_action_id": found["dismiss"]["action_id"],
                "status_before_dismiss": found["dismiss"]["payload"]["before"]["status"]}

    @app.post("/api/v1/items/{item_id}/flag")
    def flag(item_id: str, body: Note | None = None, if_match: str | None = Header(default=None)):
        return act(item_id, "flag", ("auto_published", "approved", "awaiting_review"),
                   lambda st, status: {"flagged": 1, **({"decision": "approved"} if status == "awaiting_review"
                                                        else {})}, if_match, note=body.note if body else None,
                   measures=lambda it: "ranking_miss" if (it["score"] or 0) <= 2 else "")

    @app.delete("/api/v1/items/{item_id}/flag")
    def unflag(item_id: str, if_match: str | None = Header(default=None)):
        return act(item_id, "unflag", ("flagged",), lambda st, _: {"flagged": 0}, if_match)

    @app.patch("/api/v1/items/{item_id}")
    def edit(item_id: str, body: Edit, if_match: str | None = Header(default=None)):
        fields = body.model_dump(exclude_none=True, exclude={"note", "notes"})
        if not fields:
            raise ApiError(400, "bad_request", "give at least one of competitor, category, score")
        notes = body.notes or {}
        if set(notes) - set(fields):
            raise ApiError(422, "validation_error", f"notes for fields not changed: {sorted(set(notes) - set(fields))}")
        if "competitor" in fields and fields["competitor"] not in svc.competitor_keys(cfg):
            raise ApiError(422, "validation_error", f"competitor {fields['competitor']!r} not in the config list")
        if "category" in fields and fields["category"] not in CATEGORIES:
            raise ApiError(422, "validation_error", f"category {fields['category']!r} not in the category list")
        if item_id in eval_golden.load_assignments(split_path) and \
                eval_golden.load_assignments(split_path)[item_id] == "test":
            raise ApiError(409, "conflict", "a golden-set test-split item: no edits until after the test eval")
        changes: list[dict] = []

        def extra(before: dict, history: list[dict]) -> dict:  # each field: old value, new value, its own note
            changes[:] = [{"field": k, "old": before[k], "new": v, "note": notes.get(k) or body.note}
                          for k, v in fields.items()]
            return {"changes": changes}

        res = act(item_id, "edit", ("awaiting_review", "auto_published", "approved", "flagged", "dismissed"),
                  lambda st, _: {f"edit_{k}": v for k, v in fields.items()}, if_match, note=body.note,
                  measures=lambda it: "label_candidate", extra=extra)
        labels_out.parent.mkdir(parents=True, exist_ok=True)
        with labels_out.open("a", encoding="utf-8") as f:  # candidates for Ofri to merge by hand, never labels
            for ch in changes:  # one entry per changed field, all from the same action
                f.write(json.dumps({"id": item_id, **ch, "source": "analyst", "action_id": res["action_id"],
                                    "at": res["at"]}, ensure_ascii=False) + "\n")
        return {**res, "changes": changes}

    # ---- Trust this source (D34) ----------------------------------------------------------------------------------

    def clean_host(host: str) -> str:
        h = host.strip().lower().removeprefix("www.")
        if not h or "/" in h or "." not in h or " " in h:
            raise ApiError(422, "validation_error", f"{host!r} is not a host name (e.g. gbhackers.com)")
        return h

    def held_ids(s: Snapshot) -> set[str]:
        return {i for i in s.classified_ids() if s.status(i) == "awaiting_review"}

    @app.post("/api/v1/sources/trust")
    def trust(body: TrustBody):
        h = clean_host(body.host)
        store, s = snap()
        with store:
            if h in sources.ORG_SCOPED_HOSTS:  # trusting the host would undo the per-org rule (D49, D53)
                key = sources.ORG_KEYS[h]
                raise ApiError(409, "conflict", f"{h} is vetted per org ({key} in config/vetted_sources.yaml)")
            if any(h == n or h.endswith("." + n) for n in sources.NEVER_VETTED):  # anyone can post there (D53)
                raise ApiError(409, "conflict", f"{h} is never vetted: anyone can publish there")
            if sources.is_vetted(f"https://{h}/"):
                raise ApiError(409, "conflict", f"{h} is already on the vetted list (config/vetted_sources.yaml)")
            if h in s.trusted:
                raise ApiError(409, "conflict", f"{h} is already trusted")
            before = held_ids(s)
            added = store.trust(h, body.note, body.from_item_id)
            after_snap = Snapshot.read(store, cfg, now())
            after = held_ids(after_snap)
            mine = {i for i in before if after_snap.trusted_match(s.items[i]["url"]) == h}
        return ok({"host": h, "group": "trusted", "added_at": added["added_at"], "action_id": added["action_id"],
                   "released": {"total": len(mine - after), "item_ids": sorted(mine - after)},
                   "still_held": {"total": len(mine & after), "item_ids": sorted(mine & after)}})

    @app.delete("/api/v1/sources/trust/{host}")
    def untrust(host: str):
        h = clean_host(host)
        with open_store() as store:
            if sources.is_vetted(f"https://{h}/") and h not in store.trusted_hosts():
                raise ApiError(409, "conflict", f"{h} is on the reviewed list in config/vetted_sources.yaml")
            if h not in store.trusted_hosts():
                raise ApiError(404, "not_found", f"{h} is not a trusted source")
            store.untrust(h)
        return ok({"host": h, "removed": True})

    @app.get("/api/v1/sources")
    def list_sources(kind: Literal["vetted", "unvetted", "suggested"] = "vetted", limit: int = 50, offset: int = 0):
        store, s = snap()
        with store:
            if kind == "vetted":
                rows = [{"host": h, "group": g} for g, hosts in s.vetted_lists.items() for h in sorted(hosts)]
                rows += [{"host": h, "group": "trusted", "added_at": t["added_at"]}
                         for h, t in sorted(s.trusted.items())]
            else:
                counts: dict[str, Counter] = {}
                for i in s.classified_ids():
                    url = s.items[i]["url"]
                    if s.outputs[i]["classification"]["noise"] or s.vetted(url):
                        continue
                    c = counts.setdefault(sources.host(url), Counter())
                    c["items"] += 1
                    c["held"] += s.status(i) == "awaiting_review"
                rows = [{"host": h, "items": c["items"], "held": c["held"],
                         **{k: v for k, v in s.trust_info(f"https://{h}/").items() if k in
                            ("approved", "dismissed", "suggest")}} for h, c in counts.items()]
                if kind == "suggested":
                    rows = [r for r in rows if r["suggest"]]
                rows.sort(key=lambda r: (-r["items"], r["host"]))
        return ok(page(rows, limit, offset))

    # ---- Log ---------------------------------------------------------------------------------------------------

    def log_rows(s: Snapshot, actions: list[dict] = ()) -> list[dict]:
        """actions: the analyst actions, oldest first; a dismissed item's row carries its latest dismiss reason."""
        dismissed_for = {a["target_id"]: a["reason"] for a in actions
                         if a["target_kind"] == "item" and a["action"] == "dismiss"}
        rows = []
        for sg in s.sightings:
            i = sg["item_id"]
            it = s.item(i)
            st = s.states.get(i) or {}
            if it["status"] == svc.HELD_OUT:
                stage, why = "test_skip", s.skips.get(i, "")
            elif it["status"] == "unclassified":
                stage, why = "pending", "not classified yet"
            elif it["noise"]:
                stage, why = "classify", s.outputs[i]["classification"].get("reason") or "classified as noise"
            elif st.get("decision") or st.get("flagged"):
                stage, why = "analyst", it["status"]
            elif s.rejections.get(i):
                stage, why = "validate", "; ".join(s.rejections[i])
            elif s.outputs[i]["ranking"].get("degraded"):
                stage, why = "rank", "ranker gave no usable score"
            else:
                held = [r["code"] for r in it["hold_reasons"] if s.level in r["held_at"]]
                stage, why = "route", (", ".join(held) if held else f"published at {s.level}")
            rows.append({"item_id": i, "run_id": sg["run_id"], "title": it["title"], "url": it["url"],
                         "source": it["source"], "publisher": it["publisher"], "competitor": it["competitor"],
                         "category": it["category"], "score": it["score"], "published_at": it["published_at"],
                         "collected_at": sg["seen_at"], "discovered_at": it["discovered_at"], "status": it["status"],
                         "stage": stage, "reason": why, "duplicate_of": None,
                         "dismiss_reason": dismissed_for.get(i) if it["status"] == "dismissed" else None,
                         "text_status": s.items[i]["raw"].get("text_status")})
        for d in svc.dropped_rows(runs_dir, [r["run_id"] for r in s.runs]):
            rows.append({"item_id": d.get("id"), "run_id": d.get("run_id"), "title": d.get("title") or "",
                         "url": d.get("url"), "source": d.get("source"),
                         "publisher": d.get("publisher") or sources.host(d.get("url") or ""),
                         "competitor": d.get("competitor"), "category": None, "score": None,
                         "published_at": d.get("published_at"), "collected_at": d.get("collected_at"),
                         "discovered_at": None, "status": "dropped", "stage": d.get("drop_stage"),
                         "reason": d.get("drop_reason") or "", "duplicate_of": d.get("duplicate_of"),
                         "dismiss_reason": None, "text_status": d.get("text_status")})
        return rows

    @app.get("/api/v1/log")
    def get_log(run_id: str | None = None, date_from: str | None = None, date_to: str | None = None,
                competitor: Multi = None, category: Multi = None,
                status: Multi = None, stage: Multi = None, source: Multi = None,
                q: str | None = None, sort: Literal["collected_at", "published_at", "score"] = "collected_at",
                limit: int = 50, offset: int = 0):
        store, s = snap()
        with store:
            rows = log_rows(s, store.actions())

        def day(r: dict) -> str:
            ts = svc.parse_ts(r["collected_at"])
            return svc.israel_date(ts) if ts else ""

        rows = [r for r in rows if (not run_id or r["run_id"] == run_id)
                and (not date_from or day(r) >= date_from) and (not date_to or day(r) <= date_to)
                and (not competitor or r["competitor"] in competitor) and (not category or r["category"] in category)
                and (not source or r["source"] in source) and (not q or q.lower() in (r["title"] or "").lower())]
        counts = {"status": dict(Counter(r["status"] for r in rows)), "stage": dict(Counter(r["stage"] for r in rows))}
        rows = [r for r in rows if (not status or r["status"] in status) and (not stage or r["stage"] in stage)]
        if sort == "score":
            rows.sort(key=lambda r: (-(r["score"] or 0), r["item_id"] or ""))
        else:
            rows.sort(key=lambda r: (r[sort] or "", r["item_id"] or ""), reverse=True)
        return ok({"counts": counts, **page(rows, limit, offset)})

    deps = SimpleNamespace(ok=ok, snap=snap, item_out=item_out, page=page, ApiError=ApiError, cfg=cfg, now=now,
                           changes_path=changes_path, store_path=store_path, runs_dir=runs_dir,
                           store=open_store, evals_dir=evals_dir, coverage_dir=coverage_dir,
                           events_path=events_path, changes_out_dir=changes_out_dir, labels_path=labels_path,
                           read_only=read_only,
                           demo_dir=None if demo is None else Path(demo["store_path"]).parent)  # D83: Health summaries
    competitors_api.register(app, deps)
    health_api.register(app, deps)
    return app
