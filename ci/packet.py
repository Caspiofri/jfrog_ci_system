"""The packet: one normalized item per story, the unit every collector emits and every later stage reads."""
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

Source = Literal["google_news", "vendor_feed", "github_releases", "hackernews"]
TextStatus = Literal["full", "partial", "snippet", "junk"]  # junk: the fetched page text is not the article
TextSource = Literal["feed", "page", "teaser"]
# A feed entry whose own body (Atom content, RSS content:encoded, GitHub release notes) has at least this much text
# is taken as the complete item, and the pipeline does not fetch its page. Below it the body is usually a teaser
# ("... Read more"); a fetched changelog page drags in neighbouring entries, so a complete feed body is preferred.
FEED_FULL_MIN_CHARS = 500

INDUSTRY = "industry"  # competitor key for the Industry channel (D10)
NON_COMPETITOR = "none"  # the story is about none of the tracked competitors (a label, never a query key)


def packet_id(url: str) -> str:
    """Stable id from the resolved URL, so the same story gets the same id in every run."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


class Packet(BaseModel):
    source: Source
    origin: str  # what produced it: the search query, the feed URL or the repo
    competitor: str  # competitor key from config/competitors.yaml, or INDUSTRY; prefilled from the query
    title: str
    url: str  # resolved publisher URL
    original_url: str  # as the source gave it (e.g. a news.google.com redirect)
    url_resolved: bool = True  # False when a redirect could not be decoded and url == original_url
    published_at: datetime | None = None  # timezone-aware UTC
    text: str = ""  # plain text: the source's teaser, replaced by the full page text when fetched
    text_status: TextStatus = "snippet"
    text_source: TextSource = "teaser"  # where text came from: the feed's full entry body, the fetched page, a teaser
    teaser: str = ""  # the source's teaser, kept when page text replaces it (the fallback when the page is junk)
    extraction_reasons: list[str] = []  # why the page text was judged junk (ci.extraction_quality)
    publisher: str = ""  # outlet name when the source gives one (Google News does)
    # filled by the pipeline, not by collectors
    id: str = ""
    run_id: str = ""
    collected_at: datetime | None = None
    in_24h: bool = False
    # counted over the whole fetched page (or the teaser), before the text is capped; empty in runs made before
    # this existed (see ci.backfill_mentions for those)
    mentions: dict[str, int] = {}  # competitor key -> name matches, title included; every tracked key, zeros too
    mentions_jfrog: bool = False
    mentions_config: str = ""  # MentionCounter.config_hash: which competitor list and name rules made the counts


@dataclass
class CollectorResult:
    """What a collector returns: its packets plus the errors it survived (one entry per failed query/feed)."""
    source: Source
    packets: list[Packet] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(UTC)


def window_start(days: int, now: datetime | None = None) -> datetime:
    return (now or utc_now()) - timedelta(days=days)
