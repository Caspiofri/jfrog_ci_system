"""HTML listing pages (a changelog index): entries a short feed misses. Pages are read in order, one at a time with
a pause, until the entries are older than the window or the page cap is hit. The listing carries a title, a link
and a day; the pipeline fetches each entry's page for its text."""
import time
from dataclasses import dataclass
from datetime import date, datetime
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from ci.collectors.feedutil import HEADERS, TIMEOUT, html_to_text, short_error
from ci.config import ListingPage

PAGE_DELAY_S = 1.0  # between pages of one listing
PAGE_HEADERS = {**HEADERS, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"}


@dataclass
class ListingEntry:
    title: str
    url: str
    day: date  # listings give a day, not a time
    teaser: str = ""


def parse_github_changelog(html: str, page_url: str) -> list[ListingEntry]:
    """github.blog/changelog: one <article> per entry, with a.ChangelogItem-title and time[datetime="YYYY-MM-DD"].
    An entry without a link, a title or a readable date is skipped."""
    entries = []
    for article in BeautifulSoup(html, "html.parser").find_all("article"):
        link, stamp = article.select_one("a.ChangelogItem-title[href]"), article.select_one("time[datetime]")
        title = link.get_text(" ", strip=True) if link else ""
        if not title or stamp is None:
            continue
        try:
            day = date.fromisoformat(stamp["datetime"][:10])
        except ValueError:
            continue
        excerpt = article.select_one(".ChangelogItem-excerpt, p")  # the current layout has none
        entries.append(ListingEntry(title=title, url=urljoin(page_url, link["href"]), day=day,
                                    teaser=html_to_text(str(excerpt)) if excerpt else ""))
    return entries


PARSERS = {"github_changelog": parse_github_changelog}


def robots_allows(url: str) -> bool:
    """robots.txt verdict for our agent; an unreadable robots.txt (404, network error) allows, as crawlers do."""
    parts = urlsplit(url)
    try:
        resp = requests.get(f"{parts.scheme}://{parts.netloc}/robots.txt", headers=PAGE_HEADERS, timeout=TIMEOUT)
    except requests.RequestException:
        return True
    if resp.status_code != 200:
        return True
    rules = robotparser.RobotFileParser()
    rules.parse(resp.text.splitlines())
    return rules.can_fetch(PAGE_HEADERS["User-Agent"], url)


def page_urls(page: ListingPage):
    yield page.url
    if page.page_url:
        for n in range(2, page.max_pages + 1):
            yield page.page_url.format(n=n)


def read_listing(page: ListingPage, since: datetime) -> tuple[list[ListingEntry], list[str]]:
    """(entries on or after since's day, errors). A failed page stops the listing but keeps the pages before it."""
    if not robots_allows(page.url):
        return [], [f"{page.url}: disallowed by robots.txt"]
    parse, oldest_wanted = PARSERS[page.format], since.date()
    entries: dict[str, ListingEntry] = {}  # by URL: a post can slide onto the next page between two requests
    for n, url in enumerate(page_urls(page), start=1):
        if n > 1:
            time.sleep(PAGE_DELAY_S)
        try:
            resp = requests.get(url, headers=PAGE_HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            found = parse(resp.text, url)
        except Exception as e:  # HTTP errors (403/429 included) stop here, never retried in a loop
            return list(entries.values()), [short_error(url, e)]
        if not found:  # page 1 empty means the layout changed; a later empty page is the end of the listing
            return list(entries.values()), [f"{url}: no entries parsed"] if n == 1 else []
        for e in found:
            if e.day >= oldest_wanted:
                entries.setdefault(e.url, e)
        if min(e.day for e in found) < oldest_wanted:
            return list(entries.values()), []
    capped = page.page_url and n >= page.max_pages
    return list(entries.values()), [f"{page.url}: stopped at the {page.max_pages}-page cap"] if capped else []
