"""Loads config/competitors.yaml: who we track, and where each source looks for them (D10)."""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from config.settings import CONFIG_DIR

COMPETITORS_PATH = CONFIG_DIR / "competitors.yaml"
# competitor keys that were renamed: old runs, queue files, labels and coverage events keep the old key, and every
# reader maps it to the new one (the stored files are never rewritten)
LEGACY_COMPETITOR_KEYS = {"aws_codeartifact": "aws"}


def canonical_key(key):
    """The current competitor key for a possibly legacy one; anything else comes back unchanged."""
    return LEGACY_COMPETITOR_KEYS.get(key, key) if isinstance(key, str) else key


def canonical_counts(counts):
    """A {competitor: count} dict with legacy keys mapped (and summed into the current key)."""
    if not isinstance(counts, dict):
        return counts
    out: dict = {}
    for k, v in counts.items():
        key = canonical_key(k)
        out[key] = out.get(key, 0) + v if isinstance(v, int) and key in out else v
    return out


def migrate_legacy_keys(db, tables: list[str], unique: dict[str, tuple[str, ...]] | None = None,
                        newest_by: tuple[str, ...] = ("as_of", "checked_at")) -> None:
    """Rename legacy competitor keys in sqlite state tables (change detection's own stores). In a table with a
    unique key (`unique`: table -> its columns besides competitor), a legacy row that collides with a current-key
    row is resolved first: the newer of the two by `newest_by` is kept and the other deleted."""
    with db:
        for table in tables:
            for old, new in LEGACY_COMPETITOR_KEYS.items():
                if unique and table in unique:
                    _drop_older_twin(db, table, old, new, unique[table], newest_by)
                db.execute(f"UPDATE {table} SET competitor = ? WHERE competitor = ?", (new, old))


def _drop_older_twin(db, table: str, old: str, new: str, key: tuple[str, ...], newest_by: tuple[str, ...]) -> None:
    order = ", ".join(f"COALESCE({c}, '')" for c in newest_by)
    match = " AND ".join(f"{c} IS ?" for c in key)
    for rowid, *rest in db.execute(f"SELECT rowid, {', '.join(key)}, {order} FROM {table} WHERE competitor = ?",
                                   (old,)).fetchall():
        key_values, legacy_age = rest[:len(key)], tuple(rest[len(key):])
        twin = db.execute(f"SELECT rowid, {order} FROM {table} WHERE competitor = ? AND {match}",
                          (new, *key_values)).fetchone()
        if twin is None:
            continue
        older = twin[0] if legacy_age > tuple(twin[1:]) else rowid  # a tie keeps the current-key row
        db.execute(f"DELETE FROM {table} WHERE rowid = ?", (older,))


def canonical_item(row: dict) -> dict:
    """A run item or label with its competitor key (and mention counts) mapped to the current keys."""
    if not isinstance(row, dict):
        return row
    out = dict(row)
    if "competitor" in out:
        out["competitor"] = canonical_key(out["competitor"])
    if isinstance(out.get("mentions"), dict):
        out["mentions"] = canonical_counts(out["mentions"])
    if isinstance(out.get("item"), dict):  # a label's snapshot
        out["item"] = canonical_item(out["item"])
    return out


class Feed(BaseModel):
    url: str
    # keep an entry only if its title or text contains one of these as a whole word or phrase (case-insensitive);
    # empty keeps everything.
    # Needed for broad feeds such as AWS What's New, where CodeArtifact is a small fraction.
    keywords: list[str] = []


class ListingPage(BaseModel):
    """An HTML listing of posts (a changelog index), read when the feed is too short: GitHub's changelog feed holds
    only the newest 10 entries, fewer than it posts on a launch day."""
    url: str  # the first page
    page_url: str = ""  # later pages, "{n}" = page number 2, 3, ...; empty reads the first page only
    format: Literal["github_changelog"] = "github_changelog"  # which parser reads the page layout
    max_pages: int = 10  # hard cap, whatever the window


class Competitor(BaseModel):
    key: str
    name: str
    news_queries: list[str] = []
    hn_queries: list[str] = []
    feeds: list[Feed] = []
    listing_pages: list[ListingPage] = []  # entries already in a feed are dropped (ci.collectors.vendor_feeds)
    github_repos: list[str] = []  # "owner/repo"
    # extra names that mean this competitor (products: "Amazon ECR"), on top of the name and the key
    aliases: list[str] = []


class CIConfig(BaseModel):
    window_days: int = 7
    competitors: list[Competitor]  # includes the Industry channel under key "industry"

    def by_key(self) -> dict[str, Competitor]:
        return {c.key: c for c in self.competitors}


def load(path: Path = COMPETITORS_PATH) -> CIConfig:
    return CIConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
