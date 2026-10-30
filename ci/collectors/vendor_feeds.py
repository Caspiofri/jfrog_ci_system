"""Vendor feeds collector: each competitor's official blog and changelog RSS/Atom feeds, from config, plus the
HTML listing pages configured where a feed is too short to cover the window (ci.collectors.listing_pages)."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time

from ci.collectors.feedutil import entry_date, feed_body, fetch_feed, html_to_text, short_error
from ci.collectors.listing_pages import ListingEntry, read_listing
from ci.config import CIConfig, Competitor, Feed, ListingPage
from ci.dedupe import normalize_url
from ci.packet import CollectorResult, Packet, utc_now

SOURCE = "vendor_feed"
# a day-only date is stamped at noon UTC (off by at most 12h either way), but never later than the run: a post
# dated today must not sort as newer than it can be
DAY_STAMP = time(12, 0)


def keyword_re(keyword: str) -> re.Pattern:
    """Whole words or a whole phrase, any case, joined by spaces or hyphens ("supply-chain"), with an optional
    plural s ("SBOMs"). Whole words: "ecr" must not match "secrets" or "decrease"."""
    words = r"[\s-]+".join(re.escape(w) for w in keyword.split())
    return re.compile(rf"(?<!\w){words}s?(?!\w)", re.IGNORECASE)


def _matches(entry, keywords: list[str]) -> bool:
    if not keywords:
        return True
    # match the text a reader sees, not the markup ("code" must not match <code>, "AT&T" must match AT&amp;T)
    haystack = f"{html_to_text(entry.get('title', ''))} {html_to_text(entry.get('summary', ''))}"
    return any(keyword_re(k).search(haystack) for k in keywords)


def parse(feed, competitor: Competitor, cfg_feed: Feed, since: datetime) -> list[Packet]:
    """Packets for the feed's entries published since `since` that pass its keyword filter. Undated entries are
    dropped: without a date they cannot be placed in the window."""
    packets = []
    for entry in feed.entries:
        link, published = entry.get("link", ""), entry_date(entry)
        if not link or published is None or published < since or not _matches(entry, cfg_feed.keywords):
            continue
        text, complete = feed_body(entry)
        packets.append(Packet(
            source=SOURCE,
            origin=cfg_feed.url,
            competitor=competitor.key,
            title=html_to_text(entry.get("title", "")),
            url=link,
            original_url=link,
            published_at=published,
            text=text,
            text_status="full" if complete else "snippet",  # complete: the pipeline keeps it and skips the fetch
            text_source="feed" if complete else "teaser",
            publisher=competitor.name,
        ))
    return packets


def listing_packet(entry: ListingEntry, competitor: Competitor, page: ListingPage, now: datetime) -> Packet:
    """A listing entry has no body: text is its teaser if any, and the pipeline fetches the entry page."""
    return Packet(
        source=SOURCE,
        origin=page.url,
        competitor=competitor.key,
        title=entry.title,
        url=entry.url,
        original_url=entry.url,
        published_at=min(datetime.combine(entry.day, DAY_STAMP, tzinfo=UTC), now),
        date_precision="day",  # the listing gives the day only
        text=entry.teaser,
        text_status="snippet",
        text_source="teaser",
        publisher=competitor.name,
    )


def merge(feed_packets: list[Packet], listing_packets: list[Packet]) -> list[Packet]:
    """Feed packets, plus the listing entries no feed carried (by normalized URL): a feed entry has an exact time
    and often the complete body."""
    seen = {normalize_url(p.url) for p in feed_packets}
    extra = []
    for p in listing_packets:
        key = normalize_url(p.url)
        if key not in seen:
            seen.add(key)
            extra.append(p)
    return feed_packets + extra


def collect(cfg: CIConfig, since: datetime) -> CollectorResult:
    """Every configured feed and listing page, fetched in parallel (a listing's own pages are read one at a time).
    A failing feed or page becomes one entry in `errors`; what was read before it is kept."""
    feed_jobs = [(c, f) for c in cfg.competitors for f in c.feeds]
    listing_jobs = [(c, page) for c in cfg.competitors for page in c.listing_pages]
    result = CollectorResult(source=SOURCE)

    def one_feed(job):
        competitor, cfg_feed = job
        try:
            return parse(fetch_feed(cfg_feed.url), competitor, cfg_feed, since), []
        except Exception as e:  # any failure stays inside its feed
            return [], [short_error(cfg_feed.url, e)]

    def one_listing(job):
        competitor, page = job
        try:
            entries, errors = read_listing(page, since)
        except Exception as e:  # a parser crash stays inside its listing
            return [], [short_error(page.url, e)]
        now = utc_now()
        packets = [listing_packet(e, competitor, page, now) for e in entries]
        return [p for p in packets if p.published_at >= since], errors  # the window, on the stamped time

    with ThreadPoolExecutor(max_workers=8) as pool:
        feed_runs, listing_runs = pool.map(one_feed, feed_jobs), pool.map(one_listing, listing_jobs)
        feeds, listings = list(feed_runs), list(listing_runs)
    feed_packets = [p for packets, _ in feeds for p in packets]
    listing_packets = [p for packets, _ in listings for p in packets]
    result.packets = merge(feed_packets, listing_packets)
    result.errors = [e for _, errors in feeds + listings for e in errors]
    return result
