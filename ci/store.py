"""The CI store (PRD D6): data/ci/ci.sqlite, one file for runs, items and the model output per item.

This is the first slice of the store in the events/freshness plan (1.10): runs, items, sightings, classifications,
rankings, rejections, insights, settings, skips, and the
analyst side: item_state, analyst_actions, trusted_sources. Events, routing and analyst actions come later.

- An item's discovered_at is the started_at of the earliest run that saw it. A later sighting never moves it, and an
  older run imported later moves it back, so a re-collected item never looks new again.
- Classifier and ranker output is stored per (item, run) with the fingerprint of the prompts and config that made it.
- A rejection is a model output that failed validation (ci.validate, D32); its item was routed to review.
- A skip records why an item was not sent to the model in a run (today: it is in the golden-set test split).
"""
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from ci.classify import Classification
from ci.rank import Ranked
from config.settings import DATA_DIR

STORE_PATH = DATA_DIR / "ci" / "ci.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- daily | import
    started_at TEXT NOT NULL,        -- the collection run's start: the discovery time of its new items
    processed_at TEXT NOT NULL,      -- when classify + rank started for this run
    finished_at TEXT,
    status TEXT NOT NULL,            -- running | ok | degraded | failed
    fingerprint TEXT,
    model TEXT,
    error TEXT,
    report TEXT
);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    competitor TEXT NOT NULL,        -- prefilled from the query; the classified one is in classifications
    title TEXT NOT NULL,
    published_at TEXT,
    discovered_at TEXT NOT NULL,
    first_run_id TEXT NOT NULL,
    raw TEXT NOT NULL                -- the item as the collection run wrote it
);
CREATE TABLE IF NOT EXISTS sightings (
    item_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (item_id, run_id)
);
CREATE TABLE IF NOT EXISTS classifications (
    item_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    competitor TEXT NOT NULL,
    category TEXT,
    noise INTEGER NOT NULL,
    mentions_jfrog INTEGER NOT NULL,
    confidence REAL NOT NULL,
    method TEXT NOT NULL,
    degraded INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, run_id)
);
CREATE TABLE IF NOT EXISTS rankings (
    item_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    score INTEGER,
    raw_score INTEGER,
    noise INTEGER NOT NULL,
    degraded INTEGER NOT NULL,
    needs_review INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (item_id, run_id)
);
CREATE TABLE IF NOT EXISTS rejections (   -- D32: a model output that failed validation; its item went to review
    item_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    stage TEXT NOT NULL,             -- classifier | ranker | output
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,            -- autonomy_level (D34): strict | balanced | relaxed
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS insights (  -- Brief insights (ci.insights); every generation is kept, the latest is shown
    brief_date TEXT NOT NULL,        -- Israel date of the Brief
    generated_at TEXT NOT NULL,
    trigger TEXT NOT NULL,           -- daily | refresh (D37: after analyst approvals)
    level TEXT NOT NULL,
    status TEXT NOT NULL,            -- ok | partial | none | failed
    fingerprint TEXT NOT NULL,
    model TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (brief_date, generated_at)
);
CREATE TABLE IF NOT EXISTS item_state (  -- analyst decisions (D16); routing is derived, this only overrides it
    item_id TEXT PRIMARY KEY,
    decision TEXT,                   -- approved | dismissed | NULL
    flagged INTEGER NOT NULL DEFAULT 0,
    edit_competitor TEXT,
    edit_category TEXT,
    edit_score INTEGER,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyst_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_kind TEXT NOT NULL,       -- item | source
    target_id TEXT NOT NULL,
    action TEXT NOT NULL,            -- approve | dismiss | edit | flag | unflag | trust | untrust
    reason TEXT,
    note TEXT,
    payload TEXT NOT NULL,           -- before/after values, what the action measures
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trusted_sources (  -- D34 "Trust this source": added on top of config/vetted_sources.yaml
    host TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    note TEXT,
    from_item_id TEXT
);
CREATE TABLE IF NOT EXISTS skips (
    item_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    PRIMARY KEY (item_id, run_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value or None


class Store:
    def __init__(self, path: Path = STORE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- runs ----------------------------------------------------------------------------------------------------

    def start_run(self, run_id: str, kind: str, started_at: str, fingerprint: str, model: str) -> None:
        """Insert or restart the run row; a re-run of the same run id replaces its status, not its outputs."""
        with self._db:
            self._db.execute(
                "INSERT INTO runs (run_id, kind, started_at, processed_at, status, fingerprint, model)"
                " VALUES (?, ?, ?, ?, 'running', ?, ?) ON CONFLICT(run_id) DO UPDATE SET"
                " processed_at = excluded.processed_at, status = 'running', fingerprint = excluded.fingerprint,"
                " model = excluded.model, finished_at = NULL, error = NULL",
                (run_id, kind, started_at, _now(), fingerprint, model))

    def finish_run(self, run_id: str, status: str, report: dict, error: str = "") -> None:
        with self._db:
            self._db.execute("UPDATE runs SET status = ?, finished_at = ?, report = ?, error = ? WHERE run_id = ?",
                             (status, _now(), json.dumps(report, ensure_ascii=False), error or None, run_id))

    def run(self, run_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    # ---- items ---------------------------------------------------------------------------------------------------

    def add_items(self, rows: Iterable[dict], run_id: str, seen_at: str) -> list[str]:
        """Store each item and its sighting in run_id; returns the ids that were not in the store before.

        discovered_at only ever moves earlier: the earliest run that saw an item is its discovery."""
        rows = list(rows)
        known = self.known_ids(r["id"] for r in rows)
        with self._db:
            for r in rows:
                self._db.execute(
                    "INSERT INTO items (item_id, url, source, competitor, title, published_at, discovered_at,"
                    " first_run_id, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(item_id) DO UPDATE SET"
                    " discovered_at = excluded.discovered_at, first_run_id = excluded.first_run_id"
                    " WHERE excluded.discovered_at < items.discovered_at",
                    (r["id"], r["url"], r["source"], r.get("competitor") or "", r.get("title") or "",
                     _iso(r.get("published_at")), seen_at, run_id, json.dumps(r, ensure_ascii=False, default=str)))
                self._db.execute("INSERT OR IGNORE INTO sightings VALUES (?, ?, ?)", (r["id"], run_id, seen_at))
        return [r["id"] for r in rows if r["id"] not in known]

    def known_ids(self, ids: Iterable[str]) -> set[str]:
        ids = list(ids)
        found: set[str] = set()
        for start in range(0, len(ids), 500):  # SQLite caps the number of bound parameters
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            found |= {r[0] for r in self._db.execute(f"SELECT item_id FROM items WHERE item_id IN ({marks})", chunk)}
        return found

    def item(self, item_id: str) -> dict | None:
        row = self._db.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def unclassified(self, ids: Iterable[str]) -> list[str]:
        """The given ids, in order, that have no classification from any run."""
        ids = list(ids)
        done = {r[0] for r in self._db.execute("SELECT DISTINCT item_id FROM classifications")}
        return [i for i in ids if i not in done]

    # ---- model output --------------------------------------------------------------------------------------------

    def save_outputs(self, run_id: str, fingerprint: str, classifications: list[Classification],
                     ranked: list[Ranked]) -> None:
        """Both tables in one transaction, so an item never has a classification without its ranking."""
        now = _now()
        with self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO classifications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(c.id, run_id, fingerprint, c.competitor, c.category, int(c.noise), int(c.mentions_jfrog),
                  c.confidence, c.method, int(c.degraded), c.model_dump_json(), now) for c in classifications])
            self._db.executemany(
                "INSERT OR REPLACE INTO rankings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(r.id, run_id, fingerprint, r.score, r.raw_score, int(r.noise), int(r.degraded),
                  int(r.needs_review), r.model_dump_json(), now) for r in ranked])

    def save_rejections(self, run_id: str, rejections) -> None:
        now = _now()
        with self._db:
            self._db.executemany("INSERT INTO rejections VALUES (?, ?, ?, ?, ?)",
                                 [(r.item_id, run_id, r.stage, r.reason, now) for r in rejections])

    def rejection_reasons(self) -> dict[str, list[str]]:
        """item_id -> its D32 rejection reasons, across runs."""
        out: dict[str, list[str]] = {}
        for item_id, stage, reason in self._db.execute("SELECT item_id, stage, reason FROM rejections ORDER BY rowid"):
            out.setdefault(item_id, []).append(f"{stage}: {reason}")
        return out

    # ---- insights ------------------------------------------------------------------------------------------------

    def save_insights(self, brief_date: str, result: dict) -> None:
        with self._db:
            self._db.execute("INSERT INTO insights VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (brief_date, result["generated_at"], result["trigger"], result["level"],
                              result["status"], result["fingerprint"], result["model"],
                              json.dumps(result, ensure_ascii=False)))

    def latest_insights(self, brief_date: str) -> dict | None:
        row = self._db.execute("SELECT data FROM insights WHERE brief_date = ? ORDER BY generated_at DESC LIMIT 1",
                               (brief_date,)).fetchone()
        return json.loads(row[0]) if row else None

    def insights_history(self, brief_date: str) -> list[dict]:
        rows = self._db.execute("SELECT generated_at, trigger, level, status FROM insights WHERE brief_date = ?"
                                " ORDER BY generated_at", (brief_date,))
        return [dict(r) for r in rows]

    # ---- analyst state ---------------------------------------------------------------------------------------------

    def item_states(self) -> dict[str, dict]:
        return {r["item_id"]: dict(r) for r in self._db.execute("SELECT * FROM item_state")}

    def apply_item_action(self, item_id: str, action: str, update: dict, *, reason: str | None = None,
                          note: str | None = None, payload: dict | None = None,
                          expect_version: int | None = None) -> dict:
        """Change item_state and log the action in one transaction. expect_version (If-Match) must match the current
        version (0 when the item has no state yet); otherwise ValueError("version")."""
        now = _now()
        with self._db:
            row = self._db.execute("SELECT * FROM item_state WHERE item_id = ?", (item_id,)).fetchone()
            current = dict(row) if row else {"item_id": item_id, "decision": None, "flagged": 0,
                                             "edit_competitor": None, "edit_category": None, "edit_score": None,
                                             "version": 0}
            if expect_version is not None and expect_version != current["version"]:
                raise ValueError("version")
            new = {**current, **update, "version": current["version"] + 1, "updated_at": now}
            self._db.execute(
                "INSERT INTO item_state VALUES (:item_id, :decision, :flagged, :edit_competitor, :edit_category,"
                " :edit_score, :version, :updated_at) ON CONFLICT(item_id) DO UPDATE SET decision = excluded.decision,"
                " flagged = excluded.flagged, edit_competitor = excluded.edit_competitor,"
                " edit_category = excluded.edit_category, edit_score = excluded.edit_score,"
                " version = excluded.version, updated_at = excluded.updated_at", new)
            cur = self._db.execute(
                "INSERT INTO analyst_actions (target_kind, target_id, action, reason, note, payload, at)"
                " VALUES ('item', ?, ?, ?, ?, ?, ?)",
                (item_id, action, reason, note, json.dumps(payload or {}, ensure_ascii=False), now))
        return {**new, "action_id": cur.lastrowid, "at": now}

    def log_action(self, target_kind: str, target_id: str, action: str, reason: str | None, note: str | None,
                   payload: dict) -> int:
        """An analyst action on something whose state lives elsewhere (a changed cell: changes.sqlite)."""
        with self._db:
            cur = self._db.execute(
                "INSERT INTO analyst_actions (target_kind, target_id, action, reason, note, payload, at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (target_kind, target_id, action, reason, note, json.dumps(payload, ensure_ascii=False), _now()))
        return cur.lastrowid

    def actions(self, target_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM analyst_actions", ()
        if target_id is not None:
            sql, args = sql + " WHERE target_id = ?", (target_id,)
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in self._db.execute(sql + " ORDER BY action_id",
                                                                                            args)]

    def trusted_hosts(self) -> dict[str, dict]:
        return {r["host"]: dict(r) for r in self._db.execute("SELECT * FROM trusted_sources")}

    def trust(self, host: str, note: str | None, from_item_id: str | None) -> dict:
        now = _now()
        with self._db:
            self._db.execute("INSERT INTO trusted_sources VALUES (?, ?, ?, ?)", (host, now, note, from_item_id))
            cur = self._db.execute(
                "INSERT INTO analyst_actions (target_kind, target_id, action, reason, note, payload, at)"
                " VALUES ('source', ?, 'trust', NULL, ?, ?, ?)",
                (host, note, json.dumps({"from_item_id": from_item_id}), now))
        return {"host": host, "added_at": now, "action_id": cur.lastrowid}

    def untrust(self, host: str) -> None:
        now = _now()
        with self._db:
            self._db.execute("DELETE FROM trusted_sources WHERE host = ?", (host,))
            self._db.execute("INSERT INTO analyst_actions (target_kind, target_id, action, reason, note, payload, at)"
                             " VALUES ('source', ?, 'untrust', NULL, NULL, '{}', ?)", (host, now))

    # ---- runs and items for the API -------------------------------------------------------------------------------

    def runs(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM runs ORDER BY started_at")]

    def all_items(self) -> list[dict]:
        return [{**dict(r), "raw": json.loads(r["raw"])} for r in self._db.execute("SELECT * FROM items")]

    def sightings(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM sightings")]

    def skips(self) -> dict[str, str]:
        return {r["item_id"]: r["reason"] for r in self._db.execute("SELECT item_id, reason FROM skips")}

    def setting(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute("INSERT INTO settings VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET"
                             " value = excluded.value, updated_at = excluded.updated_at", (key, value, _now()))

    # ---- settings ------------------------------------------------------------------------------------------------

    def autonomy_level(self) -> str:
        """The routing level (D34); strict until someone sets another one."""
        from ci.route import DEFAULT_LEVEL
        row = self._db.execute("SELECT value FROM settings WHERE key = 'autonomy_level'").fetchone()
        return row[0] if row else DEFAULT_LEVEL

    def set_autonomy_level(self, level: str) -> None:
        from ci.route import LEVELS
        if level not in LEVELS:
            raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
        with self._db:
            self._db.execute("INSERT INTO settings VALUES ('autonomy_level', ?, ?) ON CONFLICT(key) DO UPDATE SET"
                             " value = excluded.value, updated_at = excluded.updated_at", (level, _now()))

    def save_skips(self, run_id: str, skips: dict[str, str]) -> None:
        with self._db:
            self._db.executemany("INSERT OR REPLACE INTO skips VALUES (?, ?, ?)",
                                 [(i, run_id, why) for i, why in skips.items()])

    def outputs(self) -> list[dict]:
        """One row per classified item: the item fields plus its latest classification and ranking."""
        rows = self._db.execute(
            "SELECT i.item_id, i.url, i.source, i.competitor AS prefilled, i.title, i.published_at,"
            " i.discovered_at, i.raw, c.run_id, c.fingerprint, c.data AS classification, r.data AS ranking"
            " FROM items i JOIN classifications c ON c.item_id = i.item_id"
            " JOIN rankings r ON r.item_id = c.item_id AND r.run_id = c.run_id"
            " WHERE c.created_at = (SELECT MAX(created_at) FROM classifications WHERE item_id = i.item_id)"
            " ORDER BY i.item_id")
        return [{**dict(r), "raw": json.loads(r["raw"]), "classification": json.loads(r["classification"]),
                 "ranking": json.loads(r["ranking"])} for r in rows]
