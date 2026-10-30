"""Old vs new head-to-head fields -> Changes items, and the head-to-head cell store (PRD D9, D13, D20).

A cell is one competitor x one axis: current value, evidence, source url, as-of date and confidence, with its history.
Values are compared normalized, so whitespace, case and number formatting ("$1,950.00" vs "$1950") do not count.
"""
import difflib
import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from ci.changes.config import AXES
from ci.changes.extract import AxisField, Tier

DIFF_CONTEXT_LINES = 2
DIFF_MAX_LINES = 60
ANCHOR_MIN_LINE = 20  # a changed line shorter than this is not matched as a fragment of the evidence


def normalize_value(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().casefold().rstrip(".;,")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)  # 1,950 -> 1950
    s = re.sub(r"(\d+)\.0+\b", r"\1", s)  # 150.00 -> 150
    s = re.sub(r"\s*([/$€£])\s*", r"\1", s)  # "$ 150 / month" -> "$150/month"
    return s


def _tier_key(t: Tier) -> tuple:
    """Currency, period and unit only count next to a price ("Enterprise: contact sales" has none to qualify)."""
    if t.price is None:
        return (normalize_value(t.name), None)
    return (normalize_value(t.name), round(float(t.price), 2), t.currency.strip().upper(), normalize_value(t.period),
            normalize_value(t.unit))


def same_field(old: "Cell | AxisField", new: AxisField) -> bool:
    """Equal value after normalization, and (for pricing) the same set of tiers."""
    if normalize_value(old.value) != normalize_value(new.value):
        return False
    return {_tier_key(t) for t in old.tiers} == {_tier_key(t) for t in new.tiers}


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
    old_as_of: datetime
    new_as_of: datetime
    diff: str
    needs_review: bool = True  # D9: every changed head-to-head cell is reviewed
    reason: str


def change_id(competitor: str, axis: str, new_as_of: datetime) -> str:
    return hashlib.sha1(f"{competitor}|{axis}|{new_as_of.isoformat()}".encode()).hexdigest()[:16]


def make_change(run_id: str, page_type: str, old: Cell, new: AxisField, new_url: str, new_as_of: datetime,
                diff: str) -> ChangeItem:
    label = AXES[new.axis]
    return ChangeItem(
        id=change_id(old.competitor, new.axis, new_as_of), run_id=run_id, competitor=old.competitor, axis=new.axis,
        axis_label=label, page_key=old.page_key, page_url=new_url, page_type=page_type,
        old_value=old.value, new_value=new.value, old_evidence=old.evidence, new_evidence=new.evidence,
        old_confidence=old.confidence, new_confidence=new.confidence, old_tiers=old.tiers, new_tiers=new.tiers,
        old_as_of=old.as_of, new_as_of=new_as_of, diff=diff,
        reason=f"{label} changed on the tracked {page_type} page: every changed head-to-head cell is reviewed (D9)")


class CellStore:
    """Head-to-head cells (current value per competitor x axis) and their history, in sqlite."""

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        cols = ("competitor TEXT, axis TEXT, value TEXT, evidence TEXT, confidence REAL, tiers TEXT, "
                "source_url TEXT, page_key TEXT, as_of TEXT, checked_at TEXT")
        self._db.execute(f"CREATE TABLE IF NOT EXISTS cells ({cols}, PRIMARY KEY (competitor, axis))")
        self._db.execute(f"CREATE TABLE IF NOT EXISTS cell_history ({cols}, run_id TEXT, event TEXT, change_id TEXT)")

    @staticmethod
    def _values(c: Cell) -> tuple:
        return (c.competitor, c.axis, c.value, c.evidence, c.confidence,
                json.dumps([t.model_dump() for t in c.tiers]), c.source_url, c.page_key, c.as_of.isoformat(),
                c.checked_at.isoformat())

    @staticmethod
    def _cell(row) -> Cell:
        return Cell(competitor=row[0], axis=row[1], value=row[2], evidence=row[3], confidence=row[4],
                    tiers=json.loads(row[5] or "[]"), source_url=row[6], page_key=row[7],
                    as_of=datetime.fromisoformat(row[8]), checked_at=datetime.fromisoformat(row[9]))

    def get(self, competitor: str, axis: str) -> Cell | None:
        row = self._db.execute("SELECT * FROM cells WHERE competitor = ? AND axis = ?", (competitor, axis)).fetchone()
        return self._cell(row) if row else None

    def all(self, competitor: str | None = None) -> list[Cell]:
        q, args = "SELECT * FROM cells", ()
        if competitor:
            q, args = q + " WHERE competitor = ?", (competitor,)
        return [self._cell(r) for r in self._db.execute(q + " ORDER BY competitor, axis", args)]

    def put(self, cell: Cell, run_id: str, event: str, change: str = "") -> None:
        """Set the current cell; `event` (baseline | changed) also appends it to the history."""
        with self._db:
            self._db.execute("INSERT OR REPLACE INTO cells VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", self._values(cell))
            if event:
                self._db.execute("INSERT INTO cell_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                 (*self._values(cell), run_id, event, change))

    def history(self, competitor: str, axis: str) -> list[dict]:
        rows = self._db.execute("SELECT value, as_of, confidence, source_url, run_id, event, change_id "
                                "FROM cell_history WHERE competitor = ? AND axis = ? ORDER BY rowid",
                                (competitor, axis)).fetchall()
        keys = ("value", "as_of", "confidence", "source_url", "run_id", "event", "change_id")
        return [dict(zip(keys, r, strict=True)) for r in rows]

    def touch(self, competitor: str, axes: list[str], checked_at: datetime) -> None:
        """The page was fetched again with the same text: its cells still hold as of now."""
        with self._db:
            self._db.executemany("UPDATE cells SET checked_at = ? WHERE competitor = ? AND axis = ?",
                                 [(checked_at.isoformat(), competitor, a) for a in axes])

    def close(self) -> None:
        self._db.close()
