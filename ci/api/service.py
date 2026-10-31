"""What the API computes from the store: items with status and hold reasons, Brief windows, the queue, Log rows.

Everything is derived at request time from ci.sqlite (and the runs' .dropped.jsonl files for the Log), so changing the
autonomy level or trusting a source re-routes at once. Article text never leaves here: an item carries a 280-char
excerpt (D32, D34, D36 Q-F).
"""
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ci import config as ci_config
from ci import route, sources
from ci.classify import CATEGORIES, content_text
from ci.packet import INDUSTRY
from ci.store import Store

TZ = ZoneInfo("Asia/Jerusalem")
EXCERPT_CHARS = 280
PUBLISHED = ("auto_published", "approved", "flagged")
BRIEF_RUN_KINDS = ("daily", "import")  # an imported collection run anchors the Brief of its day, like a daily run
BRIEF_RUN_STATUSES = ("ok", "degraded")
DISMISS_REASONS = ("not_relevant", "wrong_competitor", "wrong_category", "duplicate")
HELD_OUT = "held_out"  # status of a golden-set test-split item: stored, no prediction until after the test eval
SUGGEST_APPROVALS = 3  # D36 Q-C: suggest trusting a host after 3+ approvals and 0 dismissals
URGENCY = {5: "act_now", 4: "this_week", 3: "monitor", 2: "fyi", 1: "fyi"}


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def israel_date(dt: datetime) -> str:
    return dt.astimezone(TZ).date().isoformat()


def excerpt(raw: dict) -> str:
    text = " ".join(content_text(raw).split())
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS - 1].rstrip() + "…"


@dataclass
class Snapshot:
    """One consistent read of the store for a request."""
    outputs: dict[str, dict]  # item_id -> latest classification + ranking row
    items: dict[str, dict]  # item_id -> items row (every stored item, classified or not)
    rejections: dict[str, list[str]]
    states: dict[str, dict]
    trusted: dict[str, dict]
    skips: dict[str, str]
    runs: list[dict]
    sightings: list[dict]
    level: str
    cfg: ci_config.CIConfig
    vetted_lists: dict = field(default_factory=dict)
    lens: dict = field(default_factory=dict)  # item_id -> latest lens row (D42)

    @classmethod
    def read(cls, store: Store, cfg: ci_config.CIConfig) -> "Snapshot":
        return cls(outputs={o["item_id"]: o for o in store.outputs()},
                   items={i["item_id"]: i for i in store.all_items()},
                   rejections=store.rejection_reasons(), states=store.item_states(), trusted=store.trusted_hosts(),
                   skips=store.skips(), runs=store.runs(), sightings=store.sightings(), level=store.autonomy_level(),
                   cfg=cfg, vetted_lists=sources.load(), lens=store.lens())

    # ---- vetting and routing ----

    def yaml_vetted(self, url: str) -> bool:
        return sources.is_vetted(url)

    def trusted_match(self, url: str) -> str | None:
        h = sources.host(url)
        return next((t for t in self.trusted if h == t or h.endswith("." + t)), None)

    def vetted(self, url: str) -> bool:
        return self.yaml_vetted(url) or self.trusted_match(url) is not None

    def route_input(self, item_id: str) -> route.RouteInput:
        return route.from_output(self.outputs[item_id], self.rejections.get(item_id, ()))

    def reasons(self, item_id: str) -> list[route.HoldReason]:
        return route.hold_reasons(self.route_input(item_id), self.vetted)

    def status(self, item_id: str, level: str | None = None) -> str:
        if item_id not in self.outputs:
            return HELD_OUT if item_id in self.skips else "unclassified"
        state = self.states.get(item_id) or {}
        x = self.route_input(item_id)
        if x.noise:
            return "dropped"
        if state.get("decision") == "dismissed":
            return "dismissed"
        if state.get("flagged"):
            return "flagged"
        if state.get("decision") == "approved":
            return "approved"
        return route.status(x, level or self.level, None, self.vetted)

    # ---- the Item object (contract §2) ----

    def item(self, item_id: str, level: str | None = None, badge: str | None = None) -> dict:
        row = self.items[item_id]
        raw = row["raw"]
        out = self.outputs.get(item_id)
        c = out["classification"] if out else {}
        r = out["ranking"] if out else {}
        state = self.states.get(item_id) or {}
        edited = {k: state[f"edit_{k}"] for k in ("competitor", "category", "score") if state.get(f"edit_{k}")
                  is not None}
        published, discovered = parse_ts(row["published_at"]), parse_ts(row["discovered_at"])
        score = edited.get("score", r.get("score"))
        reasons = self.reasons(item_id) if out else []
        return {
            "item_id": item_id, "title": row["title"], "url": row["url"], "excerpt": excerpt(raw),
            "source": row["source"], "publisher": raw.get("publisher") or sources.host(row["url"]),
            "publisher_host": sources.host(row["url"]),
            "competitor": edited.get("competitor", c.get("competitor", row["competitor"])),
            "classified": out is not None, "category": edited.get("category", c.get("category")),
            "noise": bool(c.get("noise", False)), "score": score, "urgency": URGENCY.get(score),
            "confidence": c.get("confidence"), "mentions_jfrog": bool(c.get("mentions_jfrog", False)),
            "reason": r.get("reason") or "", "why_it_matters": r.get("why_it_matters") or "",
            "published_at": iso(published), "date_precision": raw.get("date_precision", "time"),
            "discovered_at": iso(discovered),
            "discovery_lag_hours": round((discovered - published).total_seconds() / 3600, 1)
            if published and discovered else None,
            "badge": badge, "status": self.status(item_id, level),
            "hold_reasons": [{"code": h.code, "detail": h.detail, "held_at": list(h.held_at)} for h in reasons],
            "edited": edited or None, "flagged": bool(state.get("flagged")), "version": state.get("version", 0),
            "run_id": out["run_id"] if out else None, "fingerprint": out["fingerprint"] if out else None,
            "event_id": None,  # events are not built (D33)
            "lens": self.lens_out(item_id),
        }

    def lens_out(self, item_id: str) -> dict | None:
        """The JFrog lens (D42) when its quote check passed; None when there is none or it was dropped."""
        row = self.lens.get(item_id)
        if not row or row["status"] != "ok":
            return None
        return {"axis": row["axis"], "capability_quote": row["capability_quote"] or "", "relation": row["relation"],
                "why": row["why"] or ""}

    def classified_ids(self) -> list[str]:
        return [i for i, o in self.outputs.items()]

    # ---- Brief windows (D31) ----

    def anchors(self) -> list[tuple[str, dict]]:
        """(Brief date, anchor run) per Israel date: the first successful daily or import run of that day."""
        out: dict[str, dict] = {}
        for run in sorted(self.runs, key=lambda r: r["started_at"]):
            if run["kind"] in BRIEF_RUN_KINDS and run["status"] in BRIEF_RUN_STATUSES:
                out.setdefault(israel_date(parse_ts(run["started_at"])), run)
        return sorted(out.items())

    def window(self, date: str) -> dict | None:
        anchors = self.anchors()
        dates = [d for d, _ in anchors]
        if date not in dates:
            return None
        i = dates.index(date)
        anchor = parse_ts(anchors[i][1]["started_at"])
        prev = parse_ts(anchors[i - 1][1]["started_at"]) if i else anchor - timedelta(hours=24)
        return {"date": date, "anchor": anchor, "prev_anchor": prev, "anchor_run_id": anchors[i][1]["run_id"],
                "anchor_kind": anchors[i][1]["kind"],  # daily | import (a backfill Brief)
                "prev_date": dates[i - 1] if i else None}

    def brief_ids(self, w: dict, level: str | None = None) -> list[str]:
        """Published, non-noise, classified items discovered in (prev_anchor, anchor]."""
        return [i for i in self.classified_ids()
                if w["prev_anchor"] < parse_ts(self.items[i]["discovered_at"]) <= w["anchor"]
                and self.status(i, level) in PUBLISHED]

    def badge(self, item_id: str, w: dict) -> str:
        published = parse_ts(self.items[item_id]["published_at"])
        return "new" if published is None or published > w["anchor"] - timedelta(hours=24) else "late"

    # ---- trust suggestions (D34, D36 Q-C) ----

    def host_decisions(self) -> dict[str, Counter]:
        out: dict[str, Counter] = {}
        for item_id, st in self.states.items():
            if item_id in self.items and st.get("decision") in ("approved", "dismissed"):
                out.setdefault(sources.host(self.items[item_id]["url"]), Counter())[st["decision"]] += 1
        return out

    def trust_info(self, url: str) -> dict:
        h = sources.host(url)
        counts = self.host_decisions().get(h, Counter())
        vetted = self.vetted(url)
        return {"host": h, "vetted": vetted, "approved": counts["approved"], "dismissed": counts["dismissed"],
                "suggest": not vetted and counts["approved"] >= SUGGEST_APPROVALS and counts["dismissed"] == 0}


def sort_key(item: dict) -> tuple:
    """Score descending, then confidence, then newest publication, then id (the badge never changes the order)."""
    published = parse_ts(item["published_at"])
    return (-(item["score"] or 0), -(item["confidence"] or 0), -(published.timestamp() if published else 0),
            item["item_id"])


def competitor_keys(cfg: ci_config.CIConfig) -> list[str]:
    return [c.key for c in cfg.competitors]


def meta_lists(cfg: ci_config.CIConfig) -> dict:
    return {"competitors": [{"key": c.key, "name": c.name, "is_industry": c.key == INDUSTRY} for c in cfg.competitors],
            "categories": CATEGORIES, "levels": list(route.LEVELS), "default_level": route.DEFAULT_LEVEL,
            "statuses": [*route.STATUSES, HELD_OUT], "dismiss_reasons": list(DISMISS_REASONS),
            "hold_reasons": ["unvetted_source", "low_confidence", "teaser_high_score", "junk_extraction", "pricing",
                             "m_and_a", "mentions_jfrog", "model_failure", "invalid_output", "changed_cell"]}


def dropped_rows(runs_dir: Path, run_ids: list[str]) -> list[dict]:
    """Dedupe drops of the store's runs, from <run_id>.dropped.jsonl (not in the store yet)."""
    out = []
    for run_id in run_ids:
        path = runs_dir / f"{run_id}.dropped.jsonl"
        if path.exists():
            out += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out
