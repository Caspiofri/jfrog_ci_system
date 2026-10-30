"""Old vs new head-to-head fields -> Changes items, and the head-to-head cell store (PRD D9, D13, D20).

A cell is one competitor x one axis: current value, evidence, source url, as-of date and confidence, with its history.
Values are compared as normalized token sets, and pricing as a set of tiers, so whitespace, case, list order, plurals
and number or currency formatting ("$1,950.00/mo" vs "1950 USD per month") do not count.
"""
import difflib
import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from ci import config as ci_config
from ci.changes.config import AXES
from ci.changes.extract import AxisField, Tier, price_text

log = logging.getLogger(__name__)

DIFF_CONTEXT_LINES = 2
DIFF_MAX_LINES = 60
ANCHOR_MIN_LINE = 20  # a changed line shorter than this is not matched as a fragment of the evidence


def normalize_value(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().casefold().rstrip(".;,")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # 1,950 -> 1950
    s = re.sub(r"(\d+)\.0+\b", r"\1", s)  # 150.00 -> 150
    s = re.sub(r"\s*([/$€£])\s*", r"\1", s)  # "$ 150 / month" -> "$150/month"
    return s


_CURRENCY = {"$": "usd", "€": "eur", "£": "gbp"}
_SYNONYMS = {"mo": "month", "monthly": "month", "yr": "year", "annual": "year", "annually": "year",
             "yearly": "year"}
_STOPWORDS = {"a", "an", "and", "or", "the", "per", "of", "for", "with", "to", "in", "on", "at", "by", "is", "are",
              "plus", "also", "via"}


def _word(w: str) -> str:
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and not w[0].isdigit():
        w = w[:-1]  # users -> user, charts -> chart
    return _SYNONYMS.get(w, w)


def tokens(s: str) -> frozenset[str]:
    """The value as a set of words and numbers: order, case, plurals, stopwords, $ vs USD, /mo vs /month and number
    formatting do not count ("npm, Maven" == "Maven and npm"; "$150/mo" == "150 USD per month")."""
    s = normalize_value(s)
    for sym, code in _CURRENCY.items():
        s = s.replace(sym, f" {code} ")
    words = (_word(w) for w in re.findall(r"\d+(?:\.\d+)?|[a-z][a-z0-9+#]*", s))
    return frozenset(w for w in words if w not in _STOPWORDS)


def _period(p: str) -> str:
    return " ".join(sorted(tokens(p)))


def _tier_key(t: Tier) -> tuple:
    """(tier name, price, currency, period). A Free tier without a price is $0; currency and period only count next
    to a non-zero price ("Enterprise: contact sales" has none to qualify)."""
    name = tokens(t.name)
    price = t.price if t.price is not None else (0.0 if "free" in name else None)
    if not price:
        return (name, price)
    currency = _CURRENCY.get(t.currency.strip(), t.currency.strip().casefold()) or "usd"
    return (name, round(float(price), 2), currency, _period(t.period))


def _tier_name(t: Tier) -> str:
    return " ".join(sorted(tokens(t.name)))


# words that do not tell plans apart: "Pro (level 1)" and "Pro - 1 user / 10k requests" share "pro", and
# "Team plan" / "Business plan" share nothing once "plan" is set aside
_GENERIC_TIER_WORDS = {"plan", "tier", "edition", "level", "package", "bundle", "option", "pricing", "price"}


def _name_words(t: Tier) -> set[str]:
    return {w for w in tokens(t.name) if w not in _GENERIC_TIER_WORDS and not w[0].isdigit()}


def _rename_key(t: Tier) -> tuple | None:
    """(price, currency, period, unit) of a priced tier; None for an unpriced one, which is never paired as a
    rename ("Enterprise: contact sales" dropped and "AI add-on: contact sales" launched are two changes)."""
    key = _tier_key(t)
    if key[1] is None:
        return None
    return (*key[1:], " ".join(sorted(tokens(t.unit))))


def _similarity(a: Tier, b: Tier) -> float:
    wa, wb = _name_words(a), _name_words(b)
    return len(wa & wb) / len(wa | wb) if wa & wb else 0.0


def _pair_renames(removed: list[Tier], added: list[Tier]) -> list[tuple[Tier, Tier]]:
    """One-to-one pairs of a removed and an added tier that are the same tier renamed: same price, currency, period
    and unit, and names sharing a meaningful word; the most similar names pair first."""
    candidates = sorted(
        ((_similarity(o, n), i, j) for i, o in enumerate(removed) for j, n in enumerate(added)
         if _rename_key(o) is not None and _rename_key(o) == _rename_key(n) and _similarity(o, n) > 0),
        key=lambda c: (-c[0], c[1], c[2]))
    used_o, used_n, pairs = set(), set(), []
    for _, i, j in candidates:
        if i not in used_o and j not in used_n:
            used_o.add(i)
            used_n.add(j)
            pairs.append((removed[i], added[j]))
    return pairs


def tier_changes(old: list[Tier], new: list[Tier]) -> list[dict]:
    """Per tier, matched by normalized name: added, removed, or changed price/currency/period (the optional unit is
    not compared). Order and rendering never count. Each entry: {tier, change, old, new} with the price as shown.

    A removed and an added tier are one tier renamed ("Pro (level 2)" -> "Pro - 1 user / 10k requests") when
    _pair_renames pairs them: {tier, change: "renamed", old_name, old, new}."""
    before = {_tier_name(t): t for t in old}
    after = {_tier_name(t): t for t in new}
    out, removed, added = [], [], []
    for key in sorted(before.keys() | after.keys()):
        o, n = before.get(key), after.get(key)
        if o is None:
            added.append(n)
        elif n is None:
            removed.append(o)
        elif _tier_key(o)[1:] != _tier_key(n)[1:]:
            out.append({"tier": n.name, "change": "changed", "old": price_text(o).strip(),
                        "new": price_text(n).strip()})
    pairs = _pair_renames(removed, added)
    paired_old = {id(o) for o, _ in pairs}
    paired_new = {id(n) for _, n in pairs}
    out += [{"tier": n.name, "change": "renamed", "old_name": o.name, "old": price_text(o).strip(),
             "new": price_text(n).strip()} for o, n in pairs]
    out += [{"tier": o.name, "change": "removed", "old": price_text(o).strip(), "new": ""}
            for o in removed if id(o) not in paired_old]
    out += [{"tier": n.name, "change": "added", "old": "", "new": price_text(n).strip()}
            for n in added if id(n) not in paired_new]
    return out


def renamed_only(changes: list[dict]) -> bool:
    return bool(changes) and all(c["change"] == "renamed" for c in changes)


def same_field(old: "Cell | AxisField", new: AxisField) -> bool:
    """Pricing with tiers on both sides: no tier added, removed or re-priced (see tier_changes; renamed tiers at an
    unchanged price do not count); the value is not compared. Otherwise: the same token set (see tokens)."""
    if new.axis == "pricing_model" and old.tiers and new.tiers:
        changes = tier_changes(old.tiers, new.tiers)
        return not changes or renamed_only(changes)  # a pure rename is no change (the run reports it)
    return tokens(old.value) == tokens(new.value)


def section_diff(old_text: str, new_text: str, anchors: list[str]) -> str:
    """Unified diff of the page section around the change: the hunks touching a line that holds one of the anchors
    (old and new evidence), or every hunk when none does; capped at DIFF_MAX_LINES."""
    old_lines, new_lines = old_text.splitlines(), new_text.splitlines()
    sm = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    groups = list(sm.get_grouped_opcodes(DIFF_CONTEXT_LINES))
    keys = [a.casefold() for a in anchors if a]

    def touches(group) -> bool:
        """A changed line holds an anchor, or (a long enough line) lies inside one."""
        lines = [x.casefold() for tag, i1, i2, j1, j2 in group if tag != "equal"
                 for x in old_lines[i1:i2] + new_lines[j1:j2]]
        return any(k in line or (len(line) >= ANCHOR_MIN_LINE and line in k) for k in keys for line in lines)

    picked = [g for g in groups if touches(g)] or groups
    out = []
    for g in picked:
        i1, i2, j1, j2 = g[0][1], g[-1][2], g[0][3], g[-1][4]
        out.append(f"@@ -{i1 + 1},{i2 - i1} +{j1 + 1},{j2 - j1} @@")
        for tag, a1, a2, b1, b2 in g:
            if tag == "equal":
                out += [" " + x for x in old_lines[a1:a2]]
            else:
                out += ["-" + x for x in old_lines[a1:a2]] + ["+" + x for x in new_lines[b1:b2]]
    if len(out) > DIFF_MAX_LINES:
        out = out[:DIFF_MAX_LINES] + [f"... ({len(out) - DIFF_MAX_LINES} more diff lines)"]
    return "\n".join(out)


class Cell(BaseModel):
    competitor: str
    axis: str
    value: str
    evidence: str = ""
    confidence: float = 0.0
    tiers: list[Tier] = []
    source_url: str
    page_key: str
    as_of: datetime  # when the page this value was extracted from was fetched
    checked_at: datetime  # last time the page was fetched and still supported the value
    note: str = ""  # from the source page's config, e.g. "prices rendered client-side; pricing model only"
    # the latest extraction of the source page could not confirm this value (quote or number not on the page, or
    # the value no longer stated): it is kept, but not re-confirmed by later runs until an extraction confirms it
    stale: bool = False
    stale_reason: str = ""
    # an analyst should check this cell although no Changes item was emitted (e.g. "evidence gone, value repeated")
    needs_review: bool = False
    review_reason: str = ""


class ChangeItem(BaseModel):
    """One changed head-to-head cell, published on the Changes page after review (D9, D13)."""
    id: str
    run_id: str
    kind: str = "head_to_head_change"
    competitor: str
    axis: str
    axis_label: str
    page_key: str
    page_url: str
    page_type: str
    old_value: str
    new_value: str
    old_evidence: str
    new_evidence: str
    old_confidence: float
    new_confidence: float
    old_tiers: list[Tier] = []
    new_tiers: list[Tier] = []
    # pricing: one entry per added, removed or re-priced tier, e.g. {"tier": "Pro", "change": "changed",
    # "old": "$150/month", "new": "$180/month"}; empty for other axes
    tier_changes: list[dict] = []
    old_as_of: datetime
    new_as_of: datetime
    diff: str
    needs_review: bool = True  # D9: every changed head-to-head cell is reviewed
    note: str = ""  # the source page's note (see Cell.note)
    reason: str


def change_id(competitor: str, axis: str, new_as_of: datetime) -> str:
    return hashlib.sha1(f"{competitor}|{axis}|{new_as_of.isoformat()}".encode()).hexdigest()[:16]


def _describe(changes: list[dict]) -> str:
    words = {"added": lambda c: f"{c['tier']} added at {c['new']}", "removed": lambda c: f"{c['tier']} removed",
             "changed": lambda c: f"{c['tier']} {c['old']} -> {c['new']}",
             "renamed": lambda c: f"{c['old_name']} renamed {c['tier']} ({c['new']})"}
    return "; ".join(words[c["change"]](c) for c in changes)


def make_change(run_id: str, page_type: str, old: Cell, new: AxisField, new_url: str, new_as_of: datetime,
                diff: str, note: str = "") -> ChangeItem:
    label = AXES[new.axis]
    tiers = tier_changes(old.tiers, new.tiers) if new.axis == "pricing_model" and old.tiers and new.tiers else []
    detail = f" ({_describe(tiers)})" if tiers else ""
    return ChangeItem(
        id=change_id(old.competitor, new.axis, new_as_of), run_id=run_id, competitor=old.competitor, axis=new.axis,
        axis_label=label, page_key=old.page_key, page_url=new_url, page_type=page_type,
        old_value=old.value, new_value=new.value, old_evidence=old.evidence, new_evidence=new.evidence,
        old_confidence=old.confidence, new_confidence=new.confidence, old_tiers=old.tiers, new_tiers=new.tiers,
        old_as_of=old.as_of, new_as_of=new_as_of, diff=diff, note=note,
        tier_changes=tiers, reason=f"{label} changed on the tracked {page_type} page{detail}: every changed "
        "head-to-head cell is reviewed (D9)")


class CellStore:
    """Head-to-head cells (current value per competitor x axis) and their history, in sqlite."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        cols = ("competitor TEXT, axis TEXT, value TEXT, evidence TEXT, confidence REAL, tiers TEXT, "
                "source_url TEXT, page_key TEXT, as_of TEXT, checked_at TEXT, note TEXT, stale INTEGER, "
                "stale_reason TEXT, needs_review INTEGER, review_reason TEXT")
        self._db.execute(f"CREATE TABLE IF NOT EXISTS cells ({cols}, PRIMARY KEY (competitor, axis))")
        self._db.execute(f"CREATE TABLE IF NOT EXISTS cell_history ({cols}, run_id TEXT, event TEXT, change_id TEXT)")
        # every Changes item, with the run that wrote it to output/changes/<run_id>.jsonl ('' = not yet written)
        self._db.execute("CREATE TABLE IF NOT EXISTS changes (id TEXT PRIMARY KEY, run_id TEXT, item TEXT, "
                         "published_in TEXT)")
        # aws_codeartifact -> aws: cells keep the newer of a colliding pair; history rows are all renamed
        ci_config.migrate_legacy_keys(self._db, ["cells", "cell_history"], unique={"cells": ("axis",)})
        self._migrate_unpublished_items()

    def _migrate_unpublished_items(self) -> None:
        """Legacy competitor keys inside Changes items not yet written out (published files are never rewritten).
        An item that is not a JSON object is logged and left as it is: it must not block change detection. One
        transaction: a failure part-way leaves every row as it was."""
        rows = self._db.execute("SELECT id, item FROM changes WHERE published_in = '' ORDER BY rowid").fetchall()
        with self._db:
            for change_id, raw in rows:
                try:
                    item = json.loads(raw)
                except (TypeError, ValueError) as e:
                    log.warning("changes item %s is not JSON (%s); left as it is", change_id, e)
                    continue
                if not isinstance(item, dict):
                    log.warning("changes item %s is a %s, not an object; left as it is", change_id, type(item).__name__)
                    continue
                if ci_config.canonical_key(item.get("competitor")) != item.get("competitor"):
                    item["competitor"] = ci_config.canonical_key(item["competitor"])
                    self._db.execute("UPDATE changes SET item = ? WHERE id = ?", (json.dumps(item), change_id))

    @staticmethod
    def _values(c: Cell) -> tuple:
        return (c.competitor, c.axis, c.value, c.evidence, c.confidence,
                json.dumps([t.model_dump() for t in c.tiers]), c.source_url, c.page_key, c.as_of.isoformat(),
                c.checked_at.isoformat(), c.note, int(c.stale), c.stale_reason,
                int(c.needs_review), c.review_reason)

    @staticmethod
    def _cell(row) -> Cell:
        return Cell(competitor=row[0], axis=row[1], value=row[2], evidence=row[3], confidence=row[4],
                    tiers=json.loads(row[5] or "[]"), source_url=row[6], page_key=row[7],
                    as_of=datetime.fromisoformat(row[8]), checked_at=datetime.fromisoformat(row[9]), note=row[10] or "",
                    stale=bool(row[11]), stale_reason=row[12] or "",
                    needs_review=bool(row[13]), review_reason=row[14] or "")

    def get(self, competitor: str, axis: str) -> Cell | None:
        row = self._db.execute("SELECT * FROM cells WHERE competitor = ? AND axis = ?", (competitor, axis)).fetchone()
        return self._cell(row) if row else None

    def all(self, competitor: str | None = None) -> list[Cell]:
        q, args = "SELECT * FROM cells", ()
        if competitor:
            q, args = q + " WHERE competitor = ?", (competitor,)
        return [self._cell(r) for r in self._db.execute(q + " ORDER BY competitor, axis", args)]

    def put(self, cell: Cell, run_id: str, event: str, change: "ChangeItem | None" = None) -> None:
        """Set the current cell; a non-empty `event` also appends it to the history. A Changes item is stored in the
        same transaction, so a run that dies later cannot lose it (see unpublished)."""
        with self._db:
            row = self._values(cell)
            self._db.execute(f"INSERT OR REPLACE INTO cells VALUES ({', '.join('?' * len(row))})", row)
            if event:
                self._db.execute(f"INSERT INTO cell_history VALUES ({', '.join('?' * (len(row) + 3))})",
                                 (*row, run_id, event, change.id if change else ""))
            if change is not None:
                self._db.execute("INSERT OR IGNORE INTO changes (id, run_id, item, published_in) VALUES (?, ?, ?, '')",
                                 (change.id, change.run_id, change.model_dump_json()))

    def unpublished(self) -> list[ChangeItem]:
        """Changes items not yet written to an output file, oldest first, each with the run_id that detected it."""
        rows = self._db.execute("SELECT item FROM changes WHERE published_in = '' ORDER BY rowid").fetchall()
        return [ChangeItem.model_validate_json(r[0]) for r in rows]

    def mark_published(self, ids: list[str], run_id: str) -> None:
        with self._db:
            self._db.executemany("UPDATE changes SET published_in = ? WHERE id = ?", [(run_id, i) for i in ids])

    def history(self, competitor: str, axis: str) -> list[dict]:
        rows = self._db.execute("SELECT value, as_of, confidence, source_url, run_id, event, change_id "
                                "FROM cell_history WHERE competitor = ? AND axis = ? ORDER BY rowid",
                                (competitor, axis)).fetchall()
        keys = ("value", "as_of", "confidence", "source_url", "run_id", "event", "change_id")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def touch(self, competitor: str, axes: list[str], checked_at: datetime) -> None:
        """The page was fetched again with the same text: its cells still hold as of now. A stale cell is not
        re-confirmed: its latest extraction did not support it."""
        with self._db:
            self._db.executemany("UPDATE cells SET checked_at = ? WHERE competitor = ? AND axis = ? AND stale = 0",
                                 [(checked_at.isoformat(), competitor, a) for a in axes])

    def mark_stale(self, competitor: str, axis: str, reason: str) -> None:
        with self._db:
            self._db.execute("UPDATE cells SET stale = 1, stale_reason = ? WHERE competitor = ? AND axis = ?",
                             (reason, competitor, axis))

    def close(self) -> None:
        self._db.close()
