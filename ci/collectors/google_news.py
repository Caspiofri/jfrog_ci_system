"""Google News RSS collector: one search per configured query, redirect links decoded to the publisher URL."""
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup
from googlenewsdecoder import gnewsdecoder

from ci.config import CIConfig
from ci.packet import CollectorResult, Packet

SEARCH_URL = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
FETCH_TIMEOUT = 15  # seconds per RSS request
DECODE_TIMEOUT = 10  # seconds per decoder HTTP call
DECODE_WORKERS = 4  # Google throttles the decoder endpoint; keep this small
DECODE_DELAY = 0.3  # seconds each worker waits after a decode
USER_AGENT = "Mozilla/5.0 (compatible; jfrog-ci-collector)"

Decoder = Callable[[str], str | None]


def search_url(query: str, days: int) -> str:
    return SEARCH_URL.format(q=quote_plus(f"{query} when:{days}d"))


def decode_url(link: str) -> str | None:
    """Publisher URL behind a news.google.com redirect, or None if it cannot be decoded."""
    try:
        res = gnewsdecoder(link, timeout=DECODE_TIMEOUT)
    except Exception:  # any decoder failure means "unresolved"
        return None
    finally:
        time.sleep(DECODE_DELAY)
    return res.get("decoded_url") if res.get("success") else None


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def _published(entry) -> datetime | None:
    t = entry.get("published_parsed")
    return datetime(*t[:6], tzinfo=UTC) if t else None


def _strip_publisher(title: str, publisher: str) -> str:
    suffix = f" - {publisher}"
    return title[: -len(suffix)].rstrip() if publisher and title.endswith(suffix) else title


def _teaser(summary_html: str, titles: set[str], publisher: str, link: str = "") -> str:
    """The summary without what Google News repeats in it: the story's own title link and the publisher tag.
    Usually nothing is left, and that is honest: counting the echoed title would weigh the title twice (it is
    already weighted by the classifier) and inflate the mention hint."""
    soup = BeautifulSoup(summary_html or "", "html.parser")
    norm = {" ".join(t.split()).lower() for t in titles if t}
    for a in soup.find_all("a"):  # the story's own link: same href as the entry, or the title as its text
        if (link and a.get("href") == link) or " ".join(a.get_text(" ").split()).lower() in norm:
            a.decompose()
    for font in soup.find_all("font"):
        if publisher and " ".join(font.get_text(" ").split()) == " ".join(publisher.split()):
            font.decompose()
    return " ".join(soup.get_text(" ").split())


def to_packet(entry, competitor: str, query: str) -> Packet:
    """Packet from one RSS entry; url is the raw link until decoding replaces it."""
    publisher = (entry.get("source") or {}).get("title", "")
    title = _strip_publisher(entry.get("title", ""), publisher)
    return Packet(
        source="google_news",
        origin=query,
        competitor=competitor,
        title=title,
        url=entry.link,
        original_url=entry.link,
        url_resolved=False,
        published_at=_published(entry),
        text=_teaser(entry.get("summary", ""), {title, entry.get("title", "")}, publisher, entry.get("link", "")),
        text_status="snippet",
        publisher=publisher,
    )


def _resolve(packets: list[Packet], decoder: Decoder) -> None:
    """Decode each distinct redirect once, in a small thread pool; failures leave the packet unresolved."""
    links = sorted({p.original_url for p in packets})

    def safe(link: str) -> str | None:
        try:
            return decoder(link)
        except Exception:  # an injected decoder must not stop the run
            return None

    with ThreadPoolExecutor(max_workers=DECODE_WORKERS) as pool:
        decoded = dict(zip(links, pool.map(safe, links), strict=True))
    for p in packets:
        if url := decoded.get(p.original_url):
            p.url, p.url_resolved = url, True


def collect(
    cfg: CIConfig,
    since: datetime,
    decoder: Decoder = decode_url,
    fetch: Callable[[str], feedparser.FeedParserDict] = fetch_feed,
) -> CollectorResult:
    result = CollectorResult(source="google_news")
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)  # a naive since is taken as UTC
    for comp in cfg.competitors:
        for query in comp.news_queries:
            try:
                feed = fetch(search_url(query, cfg.window_days))
                if feed.get("bozo") and not feed.entries:
                    raise ValueError(f"unparseable feed: {feed.get('bozo_exception')}")
            except Exception as e:  # one failed query never stops the run
                result.errors.append(f"google_news {query!r}: {type(e).__name__}: {e}"[:300])
                continue
            for entry in feed.entries:
                try:
                    p = to_packet(entry, comp.key, query)
                except Exception as e:  # a malformed entry is skipped, the rest of the query survives
                    result.errors.append(f"google_news {query!r} entry: {type(e).__name__}: {e}"[:300])
                    continue
                if p.published_at is None or p.published_at >= since:
                    result.packets.append(p)
    _resolve(result.packets, decoder)
    return result
