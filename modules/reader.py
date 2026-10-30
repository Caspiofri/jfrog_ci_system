"""Reader: fetches the full text of shortlisted articles so ranking and summarizing see more than a teaser."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from modules.models import Article

FULL_TEXT_MIN_CHARS = 1500
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
# where the abstract ends on an arxiv.org/abs page (the rest is site chrome)
_ARXIV_CUT_MARKERS = ("Comments:", "Subjects:", "Cite as:", "Submission history", "Bibliographic", "Bookmark",
                      "Additional Features", "arXivLabs")
_ARXIV_CUT_RE = re.compile(r"^[ \t]*(?:%s)" % "|".join(map(re.escape, _ARXIV_CUT_MARKERS)), re.M)


def clean_page_text(final_url: str, text: str) -> str:
    """For an arxiv.org/abs page keep the title, submission date and abstract; anything else comes back unchanged."""
    try:
        parsed = urlparse(final_url)
        if parsed.hostname not in ("arxiv.org", "www.arxiv.org") or not parsed.path.startswith("/abs/"):
            return text
        start = text.find("Abstract:")
        if start < 0:
            return text
        abstract = text[start:]
        # markers count only at a line start, after the abstract's own line (the words also occur in running text)
        first, _, rest = abstract.partition("\n")
        cut = _ARXIV_CUT_RE.search(rest)
        abstract = (first + "\n" + rest[:cut.start()] if cut else abstract).strip()
        head = text[:start]
        title = re.search(r"^\s*Title:.*$", head, re.M)
        submitted = re.search(r"^\s*\[Submitted on[^\n]*$", head, re.M)
        lines = [m.group(0).strip() for m in (title, submitted) if m] + [abstract]
        # without a title or submitted line only the abstract was found: not a page we understand, keep the raw text
        return "\n".join(lines) if len(lines) > 1 else text
    except Exception:  # cleaning is best effort; the raw text is always usable
        return text


# Blocks that show other posts next to the article ("Other logs" carousels, related posts, recommendations), matched
# against whole class/id tokens split on "-" and "_": "post-related-list" and "Carousel-module__x__root" match,
# "uncorrelated-layout" does not. aria-label is never matched (it is prose: "Related to CVE-...").
RELATED_PART_RE = re.compile(r"(?:^|-)(?:related|other-(?:posts|logs)|more-(?:posts|stories)|carousel|recommended|"
                             r"you-might)(?:-|$)")
# a heading that only labels such a block ("Other logs", "Related posts") goes with it
RELATED_HEADING_RE = re.compile(r"(?:other|more|related|recommended)\s+(?:logs|posts|articles|stories|reading)|"
                                r"you might (?:also )?like|recommended(?: for you)?|read next", re.IGNORECASE)
_NEVER_DROP = {"html", "head", "body", "main", "article"}
PROTECT_SHARE = 0.3  # a prose block holding this share of the plain extraction's text is the article, kept
LISTING_SHARE = 0.6  # a block whose text is at least this much link cards is a listing (removable even when large)
SAFETY_MIN_RATIO = 0.5  # stripped extraction below this share of the plain one is checked against what was removed
log = logging.getLogger(__name__)


def _marked_related(el) -> bool:
    classes = el.get("class") or []
    tokens = [*(classes if isinstance(classes, list) else str(classes).split()), *(el.get("id") or "").split()]
    return any(RELATED_PART_RE.search("-".join(p for p in re.split(r"[-_]+", t.lower()) if p)) for t in tokens)


def _squash(text: str) -> str:
    """The comparison basis between bs4 text and trafilatura text: no whitespace at all (the two space inline
    elements differently)."""
    return re.sub(r"\s+", "", text or "")


def _is_listing(el) -> bool:
    """Mostly link cards (other posts): <li>/<article> or a div with a link and a heading, each with a link."""
    total = len(_squash(el.get_text())) or 1
    cards = [c for c in el.find_all(["li", "article", "div"])
             if c.find("a", href=True) and (c.name != "div" or c.find(["h2", "h3", "h4"]))]
    top = [c for c in cards if not any(p in cards for p in c.parents)]
    return len(top) >= 2 and sum(len(_squash(c.get_text())) for c in top) >= LISTING_SHARE * total


def _strip(html: str, plain: str = "") -> tuple[str, int]:
    """(page without related blocks, characters of the plain extraction they held).

    Measured on trafilatura's text (plain), not bs4's: a candidate holding the plain extraction's longest
    paragraph, or more than PROTECT_SHARE of its text, is the article and stays, unless it is a listing of link
    cards (an "Other logs" carousel is most of a leaky extraction). Also never removed: <article>, <main>, <body>,
    an element holding the <h1>. An <aside> goes only outside <article>/<main> or when itself marked related;
    callouts inside the article stay."""
    soup = BeautifulSoup(html, "lxml")
    paras = [_squash(line) for line in plain.splitlines() if _squash(line)]
    total = sum(map(len, paras)) or 1
    longest = max(paras, key=len) if paras else ""
    doomed = []
    for el in soup.find_all(True):
        if el.name in _NEVER_DROP or el.attrs is None:
            continue
        if el.name in ("h2", "h3", "h4") and RELATED_HEADING_RE.fullmatch(" ".join(el.get_text(" ").split())):
            doomed.append(el)
        elif el.name == "aside":
            if el.find_parent(["article", "main"]) is None or _marked_related(el):
                doomed.append(el)
        elif _marked_related(el):
            doomed.append(el)
    removed, dropped = 0, 0
    for el in doomed:
        if el.decomposed or el.find("h1") is not None:
            continue
        text = _squash(el.get_text())
        held = sum(len(p) for p in paras if p in text)
        if not _is_listing(el) and ((longest and longest in text) or held > PROTECT_SHARE * total):
            continue
        removed += held
        dropped += 1
        el.decompose()
    return (str(soup) if dropped else html), removed


def strip_related(html: str) -> str:
    """The page without related / other-posts blocks (see _strip), so the extractor cannot pull a neighbouring entry
    into the article."""
    return _strip(html, _extract(html) or "")[0]


def _extract(html: str) -> str | None:
    return trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=FAVOR_PRECISION)


# trafilatura's favor_precision was measured on the Oct 30 CI run (135 page-fetched items) and left off: it fixed
# nothing that strip_related did not, and it cut real articles (a Kaspersky post 8025 -> 0 chars, a Microsoft
# customer story 10438 -> 652, a Business Wire release 11618 -> 2873).
FAVOR_PRECISION = False


def extract_main_text(html: str) -> str | None:
    """The article's own text: related blocks stripped, then trafilatura. Shared by the old funnel and the CI
    pipeline. The plain extraction comes first and decides what may be stripped (see _strip). Second line: when
    the stripped extraction is under SAFETY_MIN_RATIO of the plain one and the loss is more than the removed blocks
    held (both on trafilatura's text), the plain extraction is used and logged."""
    plain = _extract(html) or ""
    try:
        cleaned, removed = _strip(html, plain)
    except Exception:  # a page bs4 cannot parse is still worth a plain extraction
        return plain or None
    if cleaned == html or not plain:
        return plain or _extract(cleaned)
    kept = _extract(cleaned) or ""
    lost = len(_squash(plain)) - len(_squash(kept))
    if len(kept) < SAFETY_MIN_RATIO * len(plain) and lost > 1.2 * removed + 200:
        log.warning("related-block stripping lost article text (%d -> %d chars, %d removed); using plain extraction",
                    len(plain), len(kept), removed)
        return plain
    return kept or plain


def fetch_text(url: str, timeout: int = 10) -> str | None:
    """Main article text of a page, or None when it can't be fetched or has no extractable text."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", "html"):
            return None
        text = extract_main_text(resp.text)
        return clean_page_text(resp.url, text) if text else None
    except Exception:  # network errors and parser errors both mean "keep the teaser"
        return None


def read_article(article: Article, max_chars: int, fetch=fetch_text) -> Article:
    """read_status: "full" (>= FULL_TEXT_MIN_CHARS fetched), "partial" (less), "snippet" (fetch failed, teaser kept).
    A collector may already have supplied the text (Medium author feeds): a full one is not fetched again, and a
    failed fetch keeps the status the collector gave."""
    if article.read_status == "full":
        return article
    text = fetch(article.url)
    if not text or len(text) <= len(article.content):
        return article
    status = "full" if len(text) >= FULL_TEXT_MIN_CHARS else "partial"
    return article.model_copy(update={"content": text[:max_chars], "read_status": status})


def read_articles(articles: list[Article], max_chars: int = 6000, max_workers: int = 8) -> list[Article]:
    if not articles:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(lambda a: read_article(a, max_chars), articles))
