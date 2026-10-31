"""Vetted sources (PRD D9, D34): config/vetted_sources.yaml lists the first-party hosts and the trade press.

An item is from a vetted source when its URL's host is a listed host or a subdomain of one. Everything else is an
unvetted source, a hold reason for review. The "Trust this source" review action (D34) adds to this list later.

github.com is a place, not one company (D34, D49): a github.com URL is vetted only when its first path segment is one
of the tracked competitors' orgs (github_orgs in the yaml). Other repositories there are unvetted.
"""
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from config.settings import CONFIG_DIR

VETTED_PATH = CONFIG_DIR / "vetted_sources.yaml"
GROUPS = ("first_party", "trade_press")
ORG_SCOPED_HOST = "github.com"  # vetted per org, not per host


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


@lru_cache(maxsize=4)
def load(path: Path = VETTED_PATH) -> dict[str, frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {g: frozenset(h.lower().removeprefix("www.") for h in data.get(g) or []) for g in GROUPS}


@lru_cache(maxsize=4)
def github_orgs(path: Path = VETTED_PATH) -> frozenset[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(str(o).lower() for o in data.get("github_orgs") or [])


def org(url: str) -> str:
    """The first path segment: the owner of a github.com repository URL ("" for the site root)."""
    return urlsplit(url).path.strip("/").split("/")[0].lower()


def vetted_group(url: str, path: Path = VETTED_PATH) -> str | None:
    """"first_party" or "trade_press" for a vetted URL, None for an unvetted one."""
    h = host(url)
    if h == ORG_SCOPED_HOST:
        return "first_party" if org(url) in github_orgs(path) else None
    for group, hosts in load(path).items():
        if any(h == v or h.endswith("." + v) for v in hosts):
            return group
    return None


def is_vetted(url: str, path: Path = VETTED_PATH) -> bool:
    return vetted_group(url, path) is not None
