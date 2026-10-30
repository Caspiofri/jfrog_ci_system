"""Extraction quality: is a fetched page's text the article, or junk (cookie banners, nav menus, a different page)?

    assess(title, text) -> Quality(ok, reasons, title_coverage, boilerplate_ratio)

Two signals:
- title coverage: the share of the title's content words (4+ letters, stopwords dropped) found in the text. A page
  that never mentions what its title is about is not the article (a consent wall, a homepage, an error page).
- boilerplate ratio: the share of the text's characters on boilerplate lines (cookie/consent, subscribe, sign in,
  copyright, social share, and short nav-like link lines).
"""
import re
from dataclasses import dataclass, field

# Thresholds, set on fixtures and on the 135 page-fetched items of run 20261030T0836Z-5d06a9:
# - title coverage: the junk pages there (The Register's headline list served instead of the story) score 0.14 and
#   0.20; the lowest real articles score 0.38 and up. A paywalled teaser (one paragraph + "Log in") scores 0.20 too
#   and is flagged, which is acceptable: it holds no more than its teaser.
# - boilerplate: junk pages (JS walls, "verifying your browser", "Loading") score 0.87-1.00, real pages at most 0.10.
TITLE_MIN_COVERAGE = 0.25  # below this share of the title's content words, the text is about something else
TITLE_CHECK_MIN_WORDS = 40  # shorter texts (release notes, teasers) are not judged on title coverage
TITLE_MIN_CONTENT_WORDS = 2  # a title with fewer content words gives no signal
BOILERPLATE_MAX_RATIO = 0.5  # above this share of characters on boilerplate lines, the text is junk
NAV_LINE_MAX_WORDS = 3  # a short line with no sentence punctuation reads as a menu entry...
NAV_LINE_MAX_CHARS = 40  # ...if it is also short in characters
STEM_CHARS = 5  # "launches" matches "launched": words are compared on their first 5 letters

STOPWORDS = frozenset("""
about above after again against also among another been before being below between both but could does doing
down during each even every from further have having here into itself just more most much must new news now
once only other over same should some such than that their them then there these they this those through under
until very what when where which while will with within without would your yours today says said launches
launch announces announced report reports""".split())
BOILERPLATE_RE = re.compile(
    r"\b(?:cookies?|consent|accept all|reject all|manage (?:preferences|settings)|privacy (?:policy|settings)|"
    r"terms of (?:use|service)|subscribe|subscription|newsletter|sign (?:in|up)|log ?in|log out|register|"
    r"create an account|my account|forgot (?:your )?password|skip to (?:main )?content|main menu|menu|navigation|"
    r"copyright|all rights reserved|share (?:on|this|via)|follow us|tweet|linkedin|facebook|whatsapp|"
    r"advertisement|sponsored|enable javascript|your browser)\b|©",
    re.IGNORECASE)


@dataclass
class Quality:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    title_coverage: float = 1.0
    boilerplate_ratio: float = 0.0


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def title_coverage(title: str, text: str) -> float | None:
    """Share of the title's content words found in the text, or None when the title has too few to judge."""
    content = {w[:STEM_CHARS] for w in _words(title) if len(w) >= 4 and w not in STOPWORDS and not w.isdigit()}
    if len(content) < TITLE_MIN_CONTENT_WORDS:
        return None
    present = {w[:STEM_CHARS] for w in _words(text)}
    return len(content & present) / len(content)


def _is_nav_line(line: str) -> bool:
    words = line.split()
    return (0 < len(words) <= NAV_LINE_MAX_WORDS and len(line) <= NAV_LINE_MAX_CHARS
            and not re.search(r"[.!?:;,)]$", line))


def boilerplate_ratio(text: str) -> float:
    """Share of characters on boilerplate lines (a single-line text is judged as one line)."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    total = sum(map(len, lines))
    if not total:
        return 0.0
    junk = sum(len(line) for line in lines
               if (BOILERPLATE_RE.search(line) and len(line.split()) <= 25) or _is_nav_line(line))
    return junk / total


def assess(title: str, text: str) -> Quality:
    reasons = []
    coverage = title_coverage(title, text)
    if coverage is not None and len(_words(text)) >= TITLE_CHECK_MIN_WORDS and coverage < TITLE_MIN_COVERAGE:
        reasons.append(f"title words missing from the text ({coverage:.0%} found)")
    ratio = boilerplate_ratio(text)
    if ratio > BOILERPLATE_MAX_RATIO:
        reasons.append(f"mostly boilerplate ({ratio:.0%} of the text)")
    return Quality(ok=not reasons, reasons=reasons, title_coverage=1.0 if coverage is None else coverage,
                   boilerplate_ratio=ratio)
