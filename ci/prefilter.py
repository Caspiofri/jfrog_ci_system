"""High-precision noise pre-filter, run before the classifier's rules and LLM.

An item is noise without asking the model when its title is stock chatter (price targets, 52-week highs, fund share
trades, analyst ratings, short interest...) or it comes from a software-review site. It is NEVER pre-filtered when
its title or its full text carries an event-protection word (a vulnerability, an acquisition, funding, pricing, a
launch, GA...): a real event inside a market story must still reach the model.

PREFILTER_MODE "shadow" (default) changes nothing: the would-be decision is only recorded on the classification
(shadow_prefilter) and in the eval report. "on" makes the decision: noise, method "prefilter", no LLM call.
"""
import re
from urllib.parse import urlsplit

PREFILTER_MODE = "shadow"  # "off" | "shadow" | "on"; Ofri switches it after the shadow report
MODES = ("off", "shadow", "on")  # off: not even computed (the baseline the shadow mode must equal)

CHATTER_PATTERNS = {
    "price target": r"price targets?",
    "52-week high/low": r"52[- ]week (?:highs?|lows?)",
    "fund share trade": r"shares? (?:sold|bought|acquired|purchased) by|(?:sells|buys|acquires|acquired|purchases|"
                        r"purchased|sold|bought) [\d,.]+ (?:\w+ ){0,4}shares",
    "is it a buy": r"is \S+(?: \S+){0,4} stock a (?:buy|sell)|stock a buy",
    "stake": r"(?:raises|lowers|boosts|trims|cuts|increases|decreases|reduces|takes|builds|grows|holds) (?:its |a |"
             r"new |position in |stake in |holdings in )*(?:stake|position)\b|\bstake in\b",
    "holdings": r"holdings? in|(?:raises|lowers|boosts|trims|cuts) holdings",
    "analyst rating": r"analyst (?:rating|ratings|upgrade|downgrade)s?|(?:upgraded|downgraded|upgrades|downgrades)"
                      r" (?:to|by)|rating (?:upgrade|downgrade|reiterated)|(?:buy|sell|hold|overweight|underweight)"
                      r" rating",
    "short interest": r"short interest",
    "institutional investor": r"institutional (?:investors?|ownership|holders?)",
}
# whole words at both ends: "Holdings Inc.", "price targeting" and "a buyer's market" are not chatter
CHATTER_RES = {name: re.compile(rf"\b(?:{p})\b", re.IGNORECASE) for name, p in CHATTER_PATTERNS.items()}
REVIEW_DOMAINS = ("g2.com", "capterra.com", "softwareadvice.com")  # review sites: listings, not news
PROTECTION_RE = re.compile(
    r"\b(?:vulnerabilit(?:y|ies)|cve(?:-\d{4}-\d+)?|zero-day|breach(?:es|ed)?|outages?|acquisitions?|"
    r"acquir(?:e|es|ed)|funding|raises|pricing|price change|partnerships?|partners|ga|generally available|"
    r"general availability|launch(?:es|ed)?)\b", re.IGNORECASE)


def _review_site(item: dict) -> str | None:
    """On the URL host only: a publisher name ("G2") on a news.google.com link proves nothing."""
    hosts = [(urlsplit(item.get(k) or "").hostname or "").lower() for k in ("url", "original_url")]
    for domain in REVIEW_DOMAINS:
        if any(h == domain or h.endswith("." + domain) for h in hosts):
            return f"review site {domain}"
    return None


def _without_patterns(text: str) -> str:
    for rx in CHATTER_RES.values():
        text = rx.sub(" ", text)
    return text


def check(item: dict, full_text: str) -> str | None:
    """The reason the item is pre-filtered as noise, or None. full_text is the item's content text (the stored text,
    or the teaser when the page was junk), checked for protection words along with the title."""
    title = item.get("title") or ""
    reason = None
    for name, rx in CHATTER_RES.items():
        if rx.search(title):
            reason = f"stock chatter: {name}"
            break
    reason = reason or _review_site(item)
    if reason is None:
        return None
    # a pattern's own words never protect it ("shares acquired by", "acquired 5,000 shares"): protection is looked
    # for outside the matches, in the title and in the full text alike
    if PROTECTION_RE.search(_without_patterns(title)) or PROTECTION_RE.search(_without_patterns(full_text or "")):
        return None
    return reason
