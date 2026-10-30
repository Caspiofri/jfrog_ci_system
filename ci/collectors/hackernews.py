"""Hacker News collector: recent stories mentioning a competitor, via the Algolia search API."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from ci.config import CIConfig
from ci.packet import CollectorResult, Packet

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://news.ycombinator.com/item?id={}"
# Competitor news is niche: 2 points cuts unvetted single-vote posts but keeps real vendor blog posts,
# which on the live data often sit at 2-4 points.
MIN_POINTS = 2
HITS_PER_PAGE = 100
MAX_PAGES = 2
TIMEOUT = 15


def _words(s: str) -> str:
    """Lowercase words padded with spaces; any non-alphanumeric (hyphen, underscore, slash) is a separator."""
    return f" {' '.join(re.sub(r'[^a-z0-9]+', ' ', s.lower()).split())} "


def mentions(hit: dict, query: str) -> bool:
    """Algolia matches anywhere; keep the hit only if its title or URL path contains the query as whole words.
    The host is ignored, so a project hosted on gitlab.com is not GitLab news."""
    q = _words(query)
    return q in _words(hit.get("title") or "") or q in _words(urlparse(hit.get("url") or "").path)


def to_packet(hit: dict, competitor: str, query: str) -> Packet:
    item_url = ITEM_URL.format(hit["objectID"])
    text = BeautifulSoup(hit.get("story_text") or "", "html.parser").get_text(" ", strip=True)
    return Packet(
        source="hackernews",
        origin=query,
        competitor=competitor,
        title=hit["title"].strip(),
        url=hit.get("url") or item_url,
        original_url=item_url,
        published_at=datetime.fromtimestamp(hit["created_at_i"], tz=UTC),
        text=text,
        text_status="snippet",
        publisher="Hacker News",
    )


def search(query: str, since: datetime) -> tuple[list[dict], int]:
    """Hits for the query (up to MAX_PAGES pages) and Algolia's total count."""
    hits, total = [], 0
    for page in range(MAX_PAGES):
        resp = requests.get(API_URL, params={
            "tags": "story",
            "query": query,
            "typoTolerance": "false",  # otherwise "Snyk" matches "Snake"
            "numericFilters": f"created_at_i>={int(since.timestamp())},points>={MIN_POINTS}",
            "hitsPerPage": HITS_PER_PAGE,
            "page": page,
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        hits += data["hits"]
        total = data.get("nbHits", len(hits))
        if len(hits) >= total or not data["hits"]:
            break
    return hits, total


def _one(competitor: str, query: str, since: datetime) -> tuple[list[Packet], list[str]]:
    try:
        hits, total = search(query, since)
    except Exception as e:  # noqa: BLE001 -- isolation: no query may stop the run
        return [], [f"hackernews '{query}': {type(e).__name__}: {e}"[:300]]
    packets, errors, bad = [], [], 0
    for hit in hits:
        try:
            if hit.get("title") and mentions(hit, query):
                packets.append(to_packet(hit, competitor, query))
        except Exception:  # noqa: BLE001 -- one malformed hit is skipped, not the whole query
            bad += 1
    if bad:
        errors.append(f"hackernews '{query}': skipped {bad} malformed hits")
    if total > len(hits):
        errors.append(f"hackernews '{query}': truncated: {len(hits)} of {total}")
    return packets, errors


def collect(cfg: CIConfig, since: datetime) -> CollectorResult:
    """One packet per matching story, for every competitor's hn_queries. A failing query is recorded, not fatal."""
    jobs = [(c.key, q) for c in cfg.competitors for q in c.hn_queries]
    result = CollectorResult(source="hackernews")
    if not jobs:
        return result
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
        for packets, errors in pool.map(lambda job: _one(*job, since), jobs):
            result.packets.extend(packets)
            result.errors.extend(errors)
    return result
