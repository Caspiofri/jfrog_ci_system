"""published_at is never in the future (D24 regression pin).

Snyk's changelog RSS listed "Kubernetes connector reaches end of life - 02-Nov-202" with
pubDate Sun, 01 Nov 2026 05:00:00 GMT while our 31 Oct 13:45Z run read it: a scheduled entry already in the feed.
The title's date is the end-of-life date, not the publication date. A future date is stored as the time we saw
the item, and the source's own date is kept as published_at_source."""
import json
from datetime import UTC, datetime

import feedparser

from ci import pipeline
from ci.collectors import vendor_feeds
from ci.config import CIConfig
from ci.store import Store

RUN_START = datetime(2026, 10, 31, 13, 45, 36, tzinfo=UTC)
SNYK_TITLE = "Kubernetes connector reaches end of life - 02-Nov-202"
SNYK_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Snyk updates</title><link>https://updates.snyk.io/</link>
<lastBuildDate>Sat, 31 Oct 2026 18:28:19 GMT</lastBuildDate>
<item><title>{SNYK_TITLE}</title>
<link>https://updates.snyk.io/kubernetes-connector-reaches-end-of-life-02-nov-202/</link>
<pubDate>Sun, 01 Nov 2026 05:00:00 GMT</pubDate>
<description>The Kubernetes connector for Insights is reaching end of life. On Nov 2nd 2026 it stops.</description>
</item></channel></rss>"""


def snyk_packet():
    cfg = CIConfig(competitors=[{"key": "snyk", "name": "Snyk",
                                 "feeds": [{"url": "https://updates.snyk.io/rss/", "keywords": []}]}])
    comp = cfg.competitors[0]
    since = datetime(2026, 10, 1, tzinfo=UTC)
    [p] = vendor_feeds.parse(feedparser.parse(SNYK_RSS.encode()), comp, comp.feeds[0], since)
    return p


def test_snyk_scheduled_changelog_entry_is_stamped_at_collection_time():
    p = snyk_packet()
    assert p.title == SNYK_TITLE and p.published_at == datetime(2026, 11, 1, 5, tzinfo=UTC)  # what the feed says
    s = pipeline.stamp(p, "20261031T1345Z-802913", RUN_START)
    assert s.published_at == RUN_START
    assert s.published_at_source == datetime(2026, 11, 1, 5, tzinfo=UTC)
    assert s.in_24h


def test_past_and_missing_dates_are_untouched():
    p = snyk_packet().model_copy(update={"published_at": datetime(2026, 10, 29, 14, tzinfo=UTC)})
    s = pipeline.stamp(p, "rid", RUN_START)
    assert s.published_at == datetime(2026, 10, 29, 14, tzinfo=UTC) and s.published_at_source is None
    assert pipeline.stamp(p.model_copy(update={"published_at": None}), "rid", RUN_START).published_at is None


def row(item_id: str, published_at: str) -> dict:
    return {"id": item_id, "url": f"https://updates.snyk.io/{item_id}", "source": "vendor_feed", "competitor": "snyk",
            "title": SNYK_TITLE, "published_at": published_at}


def test_store_never_keeps_a_published_at_after_discovery(tmp_path):
    seen = "2026-10-31T13:45:36.242398+00:00"
    with Store(tmp_path / "ci.sqlite") as s:
        s.add_items([row("a", "2026-11-01T05:00:00Z"), row("b", "2026-10-29T14:00:00Z")], "run", seen)
        a, b = s.item("a"), s.item("b")
    assert a["published_at"] == seen and json.loads(a["raw"])["published_at_source"] == "2026-11-01T05:00:00Z"
    assert b["published_at"] == "2026-10-29T14:00:00Z" and "published_at_source" not in json.loads(b["raw"])


def test_store_repairs_a_future_published_at_stored_before_the_fix(tmp_path):
    path = tmp_path / "ci.sqlite"
    seen = "2026-10-31T13:45:36.242398+00:00"
    with Store(path) as s:
        s.add_items([row("a", "2026-10-29T14:00:00Z")], "run", seen)
        with s._db:  # the row as the old code stored it
            s._db.execute("UPDATE items SET published_at = '2026-11-01T05:00:00Z', raw = ? WHERE item_id = 'a'",
                          (json.dumps(row("a", "2026-11-01T05:00:00Z")),))
    with Store(path) as s:
        a = s.item("a")
    assert a["published_at"] == seen
    raw = json.loads(a["raw"])
    assert raw["published_at"] == seen and raw["published_at_source"] == "2026-11-01T05:00:00Z"
