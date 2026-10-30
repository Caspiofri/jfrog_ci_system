"""GitHub releases collector: each configured repo's public releases Atom feed (no API key, no rate limit)."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ci.collectors.feedutil import entry_date, feed_body, fetch_feed, html_to_text, short_error
from ci.config import CIConfig, Competitor
from ci.packet import CollectorResult, Packet

SOURCE = "github_releases"
FEED_URL = "https://github.com/{repo}/releases.atom"


def parse(feed, competitor: Competitor, repo: str, since: datetime) -> list[Packet]:
    """Packets for the releases published since `since`, titled "<repo> <release title>"."""
    name = repo.split("/")[-1]
    packets = []
    for entry in feed.entries:
        link, published = entry.get("link", ""), entry_date(entry)
        if not link or published is None or published < since:
            continue
        text, complete = feed_body(entry)  # the release notes
        packets.append(Packet(
            source=SOURCE,
            origin=repo,
            competitor=competitor.key,
            title=f"{name} {html_to_text(entry.get('title', ''))}".strip(),
            url=link,
            original_url=link,
            published_at=published,
            text=text,
            text_status="full" if complete else "snippet",
            text_source="feed" if complete else "teaser",
            publisher=competitor.name,
        ))
    return packets


def collect(cfg: CIConfig, since: datetime) -> CollectorResult:
    """Every configured repo, fetched in parallel. A failing repo becomes one entry in `errors`."""
    jobs = [(c, r) for c in cfg.competitors for r in c.github_repos]
    result = CollectorResult(source=SOURCE)

    def one(job):
        competitor, repo = job
        try:
            return parse(fetch_feed(FEED_URL.format(repo=repo)), competitor, repo, since), None
        except Exception as e:  # any failure stays inside its repo
            return [], short_error(repo, e)

    with ThreadPoolExecutor(max_workers=8) as pool:
        for packets, error in pool.map(one, jobs):
            result.packets.extend(packets)
            if error:
                result.errors.append(error)
    return result
