"""Vetted sources (PRD D9, D34): config/vetted_sources.yaml lists the first-party hosts and the trade press.

An item is from a vetted source when its URL's host is a listed host or a subdomain of one. Everything else is an
unvetted source, a hold reason for review. The "Trust this source" review action (D34) adds to this list later.

github.com and gitlab.com are places, not one company (D34, D49, D53). A URL there is vetted only when its first
path segment is one of the tracked competitors' orgs (github_orgs / gitlab_orgs in the yaml), and only for pages the
org itself publishes: releases, tags, blob/tree (the repository's files) and changelog pages. Issues, discussions,
pull or merge requests, and everything else (repository roots, wikis, security advisories, D56) can be written or
edited by anyone, so they are unvetted. gist.github.com is never vetted: anyone can post a gist. Unvetted means held
for review, never dropped.
"""
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from config.settings import CONFIG_DIR

VETTED_PATH = CONFIG_DIR / "vetted_sources.yaml"
GROUPS = ("first_party", "trade_press")
ORG_KEYS = {"github.com": "github_orgs", "gitlab.com": "gitlab_orgs"}  # vetted per org and page kind, not per host
ORG_SCOPED_HOSTS = frozenset(ORG_KEYS)
ORG_SCOPED_HOST = "github.com"  # kept for callers that name GitHub alone
NEVER_VETTED = frozenset({"gist.github.com"})  # matched with subdomains; beats any listed parent host
VETTED_PAGE_KINDS = frozenset({"releases", "tags", "blob", "tree"})


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _within(h: str, hosts) -> bool:
    return any(h == v or h.endswith("." + v) for v in hosts)


@lru_cache(maxsize=4)
def load(path: Path = VETTED_PATH) -> dict[str, frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {g: frozenset(h.lower().removeprefix("www.") for h in data.get(g) or []) for g in GROUPS}


@lru_cache(maxsize=8)
def orgs(scoped_host: str, path: Path = VETTED_PATH) -> frozenset[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(str(o).lower() for o in data.get(ORG_KEYS[scoped_host]) or [])


def github_orgs(path: Path = VETTED_PATH) -> frozenset[str]:
    return orgs("github.com", path)


def gitlab_orgs(path: Path = VETTED_PATH) -> frozenset[str]:
    return orgs("gitlab.com", path)


def _segments(url: str) -> list[str]:
    return [p for p in urlsplit(url).path.lower().split("/") if p]


def org(url: str) -> str:
    """The first path segment: the owner of a github.com or gitlab.com repository URL ("" for the site root)."""
    parts = _segments(url)
    return parts[0] if parts else ""


def page_kind(url: str, scoped_host: str) -> str | None:
    """What a repository page is: the segment after owner/repo on GitHub, after "/-/" on GitLab (whose groups nest)."""
    parts = _segments(url)
    if scoped_host == "gitlab.com":
        return parts[parts.index("-") + 1] if "-" in parts[:-1] else None
    return parts[2] if len(parts) > 2 else None


def is_org_page_vetted(url: str, scoped_host: str, path: Path = VETTED_PATH) -> bool:
    if org(url) not in orgs(scoped_host, path):
        return False
    if any("changelog" in p for p in _segments(url)[1:]):
        return True
    return page_kind(url, scoped_host) in VETTED_PAGE_KINDS


def vetted_group(url: str, path: Path = VETTED_PATH) -> str | None:
    """"first_party" or "trade_press" for a vetted URL, None for an unvetted one."""
    h = host(url)
    if _within(h, NEVER_VETTED):
        return None
    if h in ORG_SCOPED_HOSTS:
        return "first_party" if is_org_page_vetted(url, h, path) else None
    for group, hosts in load(path).items():
        if _within(h, hosts):
            return group
    return None


def is_vetted(url: str, path: Path = VETTED_PATH) -> bool:
    return vetted_group(url, path) is not None
