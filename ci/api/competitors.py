"""Competitors screen (D20, D31, D36) and the review of changed head-to-head cells (D9, D13).

- Cards count by **discovery** time (D31): today = the Brief window of D; 7d = discovered in (anchor - 7d, anchor];
  prev_7d = the 7 days before. Only published items count; held ones are pending_review.
- The activity chart is by **publication** day (Israel date), so a late discovery sits on the day it happened.
- Head-to-head: every axis for every tracked competitor, with JFrog's cell beside it. A cell is "value", "stale",
  "not_stated" (the page says nothing on the axis: a gap in what we know, not a value) or "not_tracked" (no page).
- Deals (D36 Q-D): the Funding/M&A/Partnerships items as they are (title, competitor, date, source, status). M&A is
  held at every level (D34), so most deals show as awaiting_review until an analyst approves them.
"""
import sqlite3
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ci import route
from ci.api import service as svc
from ci.changes.config import AXES, JFROG
from ci.changes.diff import Cell, CellStore
from ci.changes.extract import NOT_STATED
from ci.packet import INDUSTRY

DEALS = route.M_AND_A
TREND_FLAT = 1  # |delta| <= 1 is flat


class ChangeNote(BaseModel):
    note: str | None = None


class ChangeDismiss(BaseModel):
    reason: Literal["wrong_extraction", "cosmetic", "not_a_change"]
    note: str | None = None


class ChangeEdit(BaseModel):
    value: str
    note: str | None = None


def cell_state(c: Cell) -> str:
    if c.value.strip().lower() == NOT_STATED:
        return "not_stated"
    return "stale" if c.stale else "value"


def change_ref(item, state: dict) -> dict:
    return {"change_id": item.id, "old_value": item.old_value, "new_value": item.new_value,
            "tier_changes": item.tier_changes, "detected_at": svc.iso(item.new_as_of), "status": state["status"]}


def cell_out(c: Cell | None, change: dict | None) -> dict:
    if c is None:
        return {"state": "not_tracked", "value": None, "reason": "no tracked page for this axis", "change": None}
    state = cell_state(c)
    return {"state": state, "value": None if state == "not_stated" else c.value,
            "evidence": c.evidence, "tiers": [t.model_dump() for t in c.tiers], "source_url": c.source_url,
            "page_key": c.page_key, "as_of": svc.iso(c.as_of), "checked_at": svc.iso(c.checked_at),
            "confidence": c.confidence, "note": c.note, "stale_reason": c.stale_reason,
            "needs_review": c.needs_review, "review_reason": c.review_reason, "change": change}


def register(app, d) -> None:
    """d: ok, snap, item_out, page, ApiError, cfg, now, changes_path, store_path."""

    def cells() -> CellStore | None:
        return CellStore(d.changes_path) if Path(d.changes_path).exists() else None

    def recent_changes(cs: CellStore | None, anchor) -> dict[tuple[str, str], dict]:
        """(competitor, axis) -> the latest change detected in the 7 days to the anchor, or still awaiting review."""
        out: dict[tuple[str, str], dict] = {}
        for item, state in (cs.changes() if cs else []):
            recent = anchor - timedelta(days=7) < item.new_as_of <= anchor
            if recent or state["status"] == "awaiting_review":
                out[(item.competitor, item.axis)] = change_ref(item, state)
        return out

    def anchor_for(s: svc.Snapshot, date: str | None) -> dict:
        anchors = s.anchors()
        if not anchors:
            raise d.ApiError(404, "not_found", "no Brief yet: no successful daily run in the store")
        w = s.window(date or anchors[-1][0])
        if w is None:
            raise d.ApiError(404, "not_found", f"no Brief for {date}")
        return w

    def published_in(s: svc.Snapshot, start, end) -> list[str]:
        return [i for i in s.classified_ids() if start < svc.parse_ts(s.items[i]["discovered_at"]) <= end
                and s.status(i) in svc.PUBLISHED]

    def card(s: svc.Snapshot, key: str, name: str, w: dict, changes: dict) -> dict:
        a = w["anchor"]
        mine = {i for i in s.classified_ids() if s.item(i)["competitor"] == key}
        today = [i for i in s.brief_ids(w) if i in mine]
        week = [i for i in published_in(s, a - timedelta(days=7), a) if i in mine]
        prev = [i for i in published_in(s, a - timedelta(days=14), a - timedelta(days=7)) if i in mine]
        held = [i for i in mine if a - timedelta(days=7) < svc.parse_ts(s.items[i]["discovered_at"]) <= a
                and s.status(i) == "awaiting_review"]
        items = [s.item(i) for i in week]
        scores = [x["score"] for x in items if x["score"] is not None]
        top = max(items, key=lambda x: ((x["score"] or 0), x["published_at"] or ""), default=None)
        delta = len(week) - len(prev)
        industry = key == INDUSTRY
        mine_changes = [c for (comp, _), c in changes.items() if comp == key]
        return {
            "key": key, "name": name, "is_industry": industry,
            "items_today": len(today), "items_7d": len(week), "items_prev_7d": len(prev),
            "trend": {"delta": delta, "direction": "flat" if abs(delta) <= TREND_FLAT else
                      "up" if delta > 0 else "down"},
            "threat": max(scores) if scores else None,
            "pending_review": len(held),
            "pending_max_score": max((s.item(i)["score"] or 0 for i in held), default=None) if held else None,
            "tracked_changes": None if industry else sum(
                a - timedelta(days=7) < svc.parse_ts(c["detected_at"]) <= a for c in mine_changes),
            "head_to_head_changes": None if industry else len(mine_changes),
            "mentions_jfrog": sum(x["mentions_jfrog"] for x in items),
            "category_mix": [{"category": c, "count": n} for c, n in
                             Counter(x["category"] for x in items if x["category"]).most_common()],
            "top_item": {k: top[k] for k in ("item_id", "title", "score", "published_at")} if top else None,
            "last_activity_at": max((x["published_at"] for x in items if x["published_at"]), default=None),
            "summary": {"status": "not_built"},  # ❌ the "this week" summary needs the summary step
        }

    def deals(s: svc.Snapshot, key: str | None = None) -> list[dict]:
        rows = []
        for i in s.classified_ids():
            it = s.item(i)
            if it["noise"] or it["category"] != DEALS or (key and it["competitor"] != key):
                continue
            rows.append({k: it[k] for k in ("item_id", "title", "url", "competitor", "published_at", "source",
                                            "publisher", "status", "score")})
        return sorted(rows, key=lambda r: (r["published_at"] or "", r["item_id"]), reverse=True)

    @app.get("/api/v1/competitors")
    def list_competitors(date: str | None = None):
        store, s = d.snap()
        with store:
            w = anchor_for(s, date)
            cs = cells()
            try:
                changes = recent_changes(cs, w["anchor"])
            finally:
                if cs:
                    cs.close()
            items = [card(s, c.key, c.name, w, changes) for c in d.cfg.competitors]
            body = {"date": w["date"], "level": s.level,
                    "week": {"start": svc.iso(w["anchor"] - timedelta(days=7)), "end": svc.iso(w["anchor"])},
                    "counted_by": "discovered_at", "total": len(items), "items": items,
                    "deals": {"category": DEALS, **d.page(deals(s), 200, 0)}}
        return d.ok(body)

    @app.get("/api/v1/competitors/{key}")
    def get_competitor(key: str, date: str | None = None, limit: int = 10, offset: int = 0):
        names = {c.key: c.name for c in d.cfg.competitors}
        if key not in names:
            raise d.ApiError(404, "not_found", f"no competitor {key!r}")
        store, s = d.snap()
        with store:
            w = anchor_for(s, date)
            cs = cells()
            try:
                changes = recent_changes(cs, w["anchor"])
                h2h = None if key == INDUSTRY else {"jfrog_name": "JFrog", "axes": [
                    {"axis": axis, "label": label,
                     "competitor": cell_out(cs.get(key, axis) if cs else None, changes.get((key, axis))),
                     "jfrog": cell_out(cs.get(JFROG, axis) if cs else None, changes.get((JFROG, axis))),
                     "changed": (key, axis) in changes or (JFROG, axis) in changes}
                    for axis, label in AXES.items()]}
            finally:
                if cs:
                    cs.close()
            mine = [i for i in s.classified_ids() if s.item(i)["competitor"] == key and s.status(i) in svc.PUBLISHED]
            end = w["anchor"].astimezone(svc.TZ).date()
            series = {(end - timedelta(days=n)).isoformat(): {"items": 0, "max_score": None} for n in range(29, -1, -1)}
            for i in mine:
                published = svc.parse_ts(s.items[i]["published_at"])
                day = svc.israel_date(published) if published else None
                if day in series:
                    sc = s.item(i)["score"]
                    series[day]["items"] += 1
                    series[day]["max_score"] = max(series[day]["max_score"] or 0, sc or 0) or None
            latest = sorted((d.item_out(s, i) for i in mine), key=lambda x: x["published_at"] or "", reverse=True)
            body = {"key": key, "name": names[key], "date": w["date"], "card": card(s, key, names[key], w, changes),
                    "summary": {"status": "not_built"}, "head_to_head": h2h,
                    "activity": {"days": 30, "bucket": "published_date", "total": len(mine),
                                 "series": [{"date": k, **v} for k, v in series.items()]},
                    "deals": deals(s, key), "latest_items": d.page(latest, limit, offset)}
        return d.ok(body)

    @app.get("/api/v1/competitors/{key}/cells/{axis}/history")
    def cell_history(key: str, axis: str):
        if axis not in AXES or (key != JFROG and key not in {c.key for c in d.cfg.competitors}):
            raise d.ApiError(404, "not_found", f"no cell {key}/{axis}")
        cs = cells()
        rows = cs.history(key, axis) if cs else []
        if cs:
            cs.close()
        return d.ok({"competitor": key, "axis": axis, "total": len(rows), "items": rows})

    # ---- review of changed cells -----------------------------------------------------------------------------------

    def decide(change_id: str, decision: str, *, reason=None, note=None, value=None) -> dict:
        cs = cells()
        if cs is None:
            raise d.ApiError(404, "not_found", f"no change {change_id}")
        try:
            found = cs.change(change_id)
            if found is None:
                raise d.ApiError(404, "not_found", f"no change {change_id}")
            try:
                new = cs.decide(change_id, decision, now=d.now(), reason=reason, note=note, value=value)
            except ValueError as e:
                why = str(e)
                if why == "value":
                    raise d.ApiError(422, "validation_error", "an edit needs a non-empty value") from None
                msg = {"decided": f"change {change_id} was already decided",
                       "superseded": "the cell changed again since this change; review the newer one"}.get(why, why)
                raise d.ApiError(409, "conflict", msg, {"status": found[1]["status"]}) from None
            state = cs.change(change_id)[1]
        finally:
            cs.close()
        measures = {"approve": "confirmed change", "edit": "extraction fix"}.get(
            decision, "extraction or diff error")
        with d.store() as store:
            action_id = store.log_action("change", change_id, decision, reason, note,
                                         {"competitor": found[0].competitor, "axis": found[0].axis,
                                          "old_value": found[0].old_value, "new_value": found[0].new_value,
                                          "cell_value": new.value, "measures": measures})
        return d.ok({"action_id": action_id, "target_kind": "change", "target_id": change_id, "action": decision,
                     "reason": reason, "status": state["status"], "cell": cell_out(new, None), "measures": measures,
                     "at": state["decided_at"]})

    @app.post("/api/v1/changes/{change_id}/approve")
    def approve_change(change_id: str, body: ChangeNote | None = None):
        return decide(change_id, "approve", note=body.note if body else None)

    @app.post("/api/v1/changes/{change_id}/dismiss")
    def dismiss_change(change_id: str, body: ChangeDismiss):
        return decide(change_id, "dismiss", reason=body.reason, note=body.note)

    @app.patch("/api/v1/changes/{change_id}")
    def edit_change(change_id: str, body: ChangeEdit):
        return decide(change_id, "edit", value=body.value, note=body.note)


def awaiting_change_rows(changes_path) -> list[dict]:
    """The changed cells awaiting review, for the Review queue (every level holds them, D9)."""
    if not Path(changes_path).exists():
        return []
    try:
        cs = CellStore(changes_path)
    except sqlite3.Error:
        return []
    try:
        rows = []
        for item, state in cs.changes():
            if state["status"] != "awaiting_review":
                continue
            rows.append({"kind": "change", "change_id": item.id, "run_id": item.run_id, "competitor": item.competitor,
                         "axis": item.axis, "axis_label": item.axis_label, "old_value": item.old_value,
                         "new_value": item.new_value, "old_evidence": item.old_evidence,
                         "new_evidence": item.new_evidence, "tier_changes": item.tier_changes, "diff": item.diff,
                         "page_url": item.page_url, "note": item.note, "held_since": svc.iso(item.new_as_of),
                         "hold_reasons": [{"code": h.code, "detail": h.detail, "held_at": list(h.held_at)}
                                          for h in route.change_hold_reasons()]})
        return rows
    finally:
        cs.close()
