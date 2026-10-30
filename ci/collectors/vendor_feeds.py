"""Vendor feeds collector: each competitor's official blog and changelog RSS/Atom feeds, from config."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ci.collectors.feedutil import entry_date, feed_body, fetch_feed, html_to_text, short_error
from ci.config import CIConfig, Competitor, Feed
from ci.packet import CollectorResult, Packet

SOURCE = "vendor_feed"


def _matches(entry, keywords: list[str]) -> bool:
    if not keywords:
        return True
    # match the text a reader sees, not the markup ("code" must not match <code>, "AT&T" must match AT&amp;T)
    haystack = f"{html_to_text(entry.get('title', ''))} {html_to_text(entry.get('summary', ''))}".lower()
    return any(k.lower() in haystack for k in keywords)


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


def collect(cfg: CIConfig, since: datetime) -> CollectorResult:
    """Every configured feed, fetched in parallel. A failing feed becomes one entry in `errors`."""
    jobs = [(c, f) for c in cfg.competitors for f in c.feeds]
    result = CollectorResult(source=SOURCE)

    def one(job):
        competitor, cfg_feed = job
        try:
            return parse(fetch_feed(cfg_feed.url), competitor, cfg_feed, since), None
        except Exception as e:  # any failure stays inside its feed
            return [], short_error(cfg_feed.url, e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for packets, error in pool.map(one, jobs):
            result.packets.extend(packets)
            if error:
                result.errors.append(error)
    return result
