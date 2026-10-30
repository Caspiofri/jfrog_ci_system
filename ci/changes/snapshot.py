"""Snapshots of tracked pages: fetch, normalize to main text, hash, store (glossary: Snapshot; PRD D13).

The text is the shared extraction (modules.reader.extract_main_text) with whitespace collapsed inside each line and
blank lines dropped, so re-flowed markup does not count as a change but the line structure survives for diffs.
Each snapshot is a .txt file under <root>/<competitor>/<page_key>/<UTC ts>.txt plus a row in sqlite; only the last
`keep` snapshots per page are kept.
"""
import hashlib
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

from modules.reader import _HEADERS, extract_main_text

KEEP_SNAPSHOTS = 10
FETCH_TIMEOUT_S = 20


class FetchError(RuntimeError):
    """The page could not be fetched as HTML, or had no extractable text."""


Fetch = Callable[[str], str]  # url -> page HTML; raises on failure


def http_fetch(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=FETCH_TIMEOUT_S, allow_redirects=True)
    if resp.status_code != 200:
        raise FetchError(f"HTTP {resp.status_code}")
    content_type = resp.headers.get("content-type", "html")
    if "html" not in content_type:
        raise FetchError(f"not HTML ({content_type})")
    return resp.text


def normalize_text(html: str) -> str:
    """Main text of the page, each line's whitespace collapsed, blank lines dropped."""
    text = extract_main_text(html) or ""
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    competitor: str
    page_key: str
    url: str
    hash: str
    fetched_at: datetime
    path: Path

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8")


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


class SnapshotStore:
    """Snapshot files under `root`, their metadata in the sqlite file `db_path` (table snapshots)."""

    def __init__(self, db_path: Path, root: Path, keep: int = KEEP_SNAPSHOTS):
        if keep < 1:
            raise ValueError("keep must be at least 1")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.root, self.keep = root, keep
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS snapshots (competitor TEXT, page_key TEXT, url TEXT, "
                         "hash TEXT, fetched_at TEXT, path TEXT)")
        self._db.execute("CREATE INDEX IF NOT EXISTS snapshots_page ON snapshots (competitor, page_key, fetched_at)")

    def _row(self, row) -> Snapshot:
        return Snapshot(row[0], row[1], row[2], row[3], datetime.fromisoformat(row[4]), Path(row[5]))

    def history(self, competitor: str, page_key: str) -> list[Snapshot]:
        """The page's stored snapshots, newest first."""
        rows = self._db.execute("SELECT competitor, page_key, url, hash, fetched_at, path FROM snapshots "
                                "WHERE competitor = ? AND page_key = ? ORDER BY fetched_at DESC",
                                (competitor, page_key)).fetchall()
        return [self._row(r) for r in rows]

    def latest(self, competitor: str, page_key: str) -> Snapshot | None:
        hist = self.history(competitor, page_key)
        return hist[0] if hist else None

    def add(self, competitor: str, page_key: str, url: str, text: str, fetched_at: datetime) -> Snapshot:
        """Write the snapshot file and row, then drop the page's snapshots beyond the newest `keep`."""
        folder = self.root / competitor / page_key
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{_ts(fetched_at)}.txt"
        path.write_text(text, encoding="utf-8")
        snap = Snapshot(competitor, page_key, url, content_hash(text), fetched_at.astimezone(UTC), path)
        with self._db:
            self._db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?, ?)",
                             (competitor, page_key, url, snap.hash, snap.fetched_at.isoformat(timespec="microseconds"),
                              str(path)))
        for old in self.history(competitor, page_key)[self.keep:]:
            old.path.unlink(missing_ok=True)
            with self._db:
                self._db.execute("DELETE FROM snapshots WHERE competitor = ? AND page_key = ? AND path = ?",
                                 (competitor, page_key, str(old.path)))
        return snap

    def close(self) -> None:
        self._db.close()
