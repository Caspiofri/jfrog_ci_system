"""Classifier (PRD D11): competitor, one of 7 categories, noise, the Mentions JFrog flag and a confidence per item.

Rules first, and deliberately narrow. Rules settle an item only when its prefilled competitor is confirmed by a
first-party source (a feed on a host from its own config block, or one of its configured GitHub repos; never for
Industry) or by its name in the title, no other competitor is named in the title or dominates the mentions, the
title is not market chatter, marketing/event content or a multi-company roundup, and exactly one category's
tightened keywords match the title. Everything else goes to the LLM in batches, referenced by id, so the model can
only answer about items it was given and can judge noise. Mentions JFrog is always the regex.

A missing, malformed or failed LLM answer never raises: the item keeps its prefilled competitor at low confidence
with method "fallback", which routes it to review (D9) and lets the eval refuse to score a degraded live run.
"""
import hashlib
import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from ci import config as ci_config
from ci import mentions as side_mentions
from ci.llm import JsonLLM, LLMError
from ci.packet import INDUSTRY, NON_COMPETITOR
from config.settings import OUTPUT_DIR

log = logging.getLogger(__name__)

# D11, verbatim as the labeling page stores them (a test keeps the two lists equal)
CATEGORIES = [
    "Product & Features",
    "Pricing & Packaging",
    "AI & Agents",
    "Security",
    "Funding/M&A/Partnerships",
    "Customers & Market",
    "Leadership & Org",
]
PRODUCT = "Product & Features"
RUNS_DIR = OUTPUT_DIR / "runs"
BATCH_SIZE = 10
LLM_TEXT_CHARS = 1500  # of each item's text shown to the model
LOW_CONFIDENCE = 0.2  # given when the LLM answer for an item is missing or invalid
RULES_CONFIDENCE = 0.85  # competitor in the title or a first-party source, and one category keyword match
TITLE_WEIGHT = 3  # a title mention counts as this many text mentions when comparing competitors
FIRST_PARTY_SOURCES = {"vendor_feed", "github_releases"}  # can be first-party, if the feed/repo is the competitor's

# JFrog and its unambiguous product names. Bare "Xray" is left out: it is also a popular proxy tool and an x-ray;
# "JFrog Xray" or Xray next to Artifactory still match through those words.
# URLs and bare domains (github.com/org/repo, about.gitlab.com, snyk.io) are links, not mentions
URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|io|org|net|dev|co|ai|blog)\b(?:/\S*)?",
                    re.IGNORECASE)
JFROG_RE = re.compile(r"\b(jfrog|artifactory|frogbot|swampup)\b", re.IGNORECASE)

# Title keywords per category, kept narrow: a rule must match exactly one category, else the LLM decides.
# No bare "flaw" (idioms like "a fatal flaw") and no bare "AI" (thought-leadership titles); "security" and
# "researchers" are Security words, so a Copilot-in-a-security-story title matches two categories and goes to the LLM.
CATEGORY_PATTERNS = {
    "Funding/M&A/Partnerships": r"acquir\w*|acquisition|merger|merges|funding|raises|series [a-f]|invest\w*|"
                                r"partner\w*|ipo",
    "Pricing & Packaging": r"pricing|price change|per seat|free tier|free plan|licens\w*|subscription|new plans?",
    "Leadership & Org": r"ceo|cto|cfo|ciso|chief \w+ officer|appoint\w*|steps down|layoffs?|hires|joins as|"
                        r"reorg\w*",
    "Security": r"security|vulnerabilit\w*|cve-\d+|cves?|exploit\w*|malicious|malware|breach\w*|attacks?|"
                r"attackers?|secret scanning|supply[- ]chain|patch(?:es|ed)?|cvss|zero-day|backdoor\w*|rce|"
                r"researchers?|compromised?",
    "AI & Agents": r"ai agents?|ai-powered|ai models?|agents?|agentic|copilot|mcp|llms?|genai|duo",
    "Customers & Market": r"customers?|gartner|forrester|idc|market share|case study|adopts|selects|"
                          r"consolidates|migrates|moves to|switch(?:es)? to",
    PRODUCT: r"launch\w*|releases?|released|generally available|general availability|ga|now supports?|"
             r"introduc\w*|new feature|public preview|beta|adds|announces|changelog|deprecat\w*|sunset\w*|"
             r"v?\d+\.\d+(?:\.\d+)?",
}
CATEGORY_RES = {c: re.compile(rf"\b(?:{p})\b", re.IGNORECASE) for c, p in CATEGORY_PATTERNS.items()}
# titles that look like noise or market chatter; rules never settle these, the LLM decides
NOISE_HINT_RE = re.compile(r"\b(stocks?|shares|52-week|price target|nasdaq|nyse|earnings|analyst rating|"
                           r"short interest|buy rating|sell rating|rally|valuation|investors?|gtlb|"
                           r"q[1-4] results|too late to buy)\b", re.IGNORECASE)
# marketing, events, reports and listicles: possibly noise, so the LLM judges them
MARKETING_HINT_RE = re.compile(r"\b(summit|webinar|unfiltered|conference|keynote|events?|podcast|supercast|"
                               r"livestream|meetup|awards?|octoverse|state of|reports?|survey|predictions|trends|"
                               r"recap|roundup|weekly|digest|top \d+|\d+ best|best|vs\.?|versus|ways|lessons|"
                               r"guide|how to|why)\b", re.IGNORECASE)
ROUNDUP_MIN_COMMAS = 2  # "PHP2Shell, LiteLLM, GitLab: ..." lists several subjects (commas before a word, not digits)
ROUNDUP_RE = re.compile(r",\s+[^\W\d]")

# Definitions the LLM works from (D11 categories, D10 scope, and the noise/none semantics of the labeling page)
CATEGORY_DEFINITIONS = {
    "Product & Features": "a new or changed product, feature, integration, release or GA/preview announcement",
    "Pricing & Packaging": "prices, plans, tiers, licensing, free-tier or bundling changes",
    "AI & Agents": "AI features, coding assistants, agents, MCP servers, LLM capabilities in the product",
    "Security": "vulnerabilities, CVEs, attacks, malicious packages, breaches, security research or scanning news",
    "Funding/M&A/Partnerships": "funding rounds, acquisitions, mergers, IPOs, strategic partnerships",
    "Customers & Market": "customer wins, analyst reports, market share, surveys, adoption and market positioning",
    "Leadership & Org": "executive hires and departures, layoffs, reorganizations",
}

Method = Literal["rules", "llm", "fallback"]  # fallback: the LLM answer for this item was unusable


class Classification(BaseModel):
    id: str
    competitor: str  # a config key (incl. "industry") or "none"
    category: str | None  # one of CATEGORIES; None only when nothing could decide it
    noise: bool
    mentions_jfrog: bool
    confidence: float  # 0-1
    method: Method
    reason: str = ""
    # set when the LLM failed for this item: the prefilled competitor is kept but not confirmed, and it goes to review
    degraded: bool = False
    competitor_confirmed: bool = True
    needs_review: bool = False
    review_reason: str = ""


MIN_NAME_CHARS = 4  # a name or key shorter than this ("AWS") would match every story about the company
BLOCKED_ALIASES = frozenset({"aws", "amazon", "amazon web services"})  # whole-company names, never a product


def aliases(comp: ci_config.Competitor) -> list[str]:
    """Names to look for: the configured aliases, the name and the key as words (when 4+ letters), and their
    distinctive words (6+ letters, so "CodeArtifact" counts). A bare "AWS" or "Amazon" never does."""
    found = {n.lower() for n in (comp.name, comp.key.replace("_", " ")) if len(n) >= MIN_NAME_CHARS}
    for word in re.split(r"[\s_]+", f"{comp.name} {comp.key}"):
        if len(word) >= 6:
            found.add(word.lower())
    found |= {" ".join(a.split()).lower() for a in comp.aliases if a.strip()}
    return sorted(found - BLOCKED_ALIASES, key=len, reverse=True)


def _alias_re(names: Iterable[str]) -> re.Pattern:
    names = [n for n in names if n]
    if not names:
        return re.compile(r"(?!x)x")  # never matches (an empty alternation would match everywhere)
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")\b", re.IGNORECASE)


# the title's subject: it opens with the competitor (after a short lead such as "Exclusive:"), followed by an action
# verb or in possessive form ("GitHub's npm firewall"); "Malware hidden in GitHub repos" only names a venue
TITLE_LEAD = r"(?:[^:\s][^:]{0,24}:\s+)?(?:the\s+)?"
SUBJECT_VERBS = (r"launch(?:es|ed)?|adds?|added|introduc(?:es|ed)|unveil(?:s|ed)?|announc(?:es|ed)|releas(?:es|ed)|"
                 r"acquir(?:es|ed)|preview(?:s|ed)?|debut(?:s|ed)?|expand(?:s|ed)?|updat(?:es|ed)|ship(?:s|ped)?|"
                 r"roll(?:s|ed)?\s+out|brings?|brought|makes?|made|patch(?:es|ed)|fix(?:es|ed)")


def _subject_re(names: Iterable[str]) -> re.Pattern:
    alias = "|".join(re.escape(n) for n in names)
    return re.compile(rf"^{TITLE_LEAD}(?:{alias})(?:['’]s\b|\s+(?:{SUBJECT_VERBS})\b)", re.IGNORECASE)


def title_mention_hint(key: str) -> str:
    """The prompt line for an industry item whose title names a competitor without being about it by rule."""
    return f"Competitor named in title: {key} — company or platform?"


def _host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def own_sources(comp: ci_config.Competitor) -> set[str]:
    """The competitor's own feed and listing-page hosts and GitHub repos, derived from its config block."""
    hosts = {_host(f.url) for f in comp.feeds} | {_host(page.url) for page in comp.listing_pages}
    return hosts | {f"repo:{r.lower()}" for r in comp.github_repos}


def _as_count(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def has_full_mentions(item: dict) -> bool:
    """True when the item carries mention counts taken over its whole page (pipeline or backfill side file)."""
    return isinstance(item.get("mentions"), dict) and bool(item["mentions"])


def strip_urls(text: str) -> str:
    """Text with URLs and bare domains blanked, so github.com/... or about.gitlab.com is not a mention."""
    return URL_RE.sub(" ", text or "")


def content_text(item: dict) -> str:
    """The text that stands for the item: its stored text, or its teaser when the page text is junk (a nav menu or
    a consent wall must never reach the LLM or the mention counts)."""
    if item.get("text_status") == "junk":
        return item.get("teaser") or ""
    return item.get("text") or ""


def mentions_jfrog(item: dict) -> bool:
    """The full-page flag when the item has one, or'd with the regex over the (possibly capped) stored text."""
    stored = bool(JFROG_RE.search(strip_urls(f"{item.get('title') or ''}\n{content_text(item)}")))
    return stored or (has_full_mentions(item) and bool(item.get("mentions_jfrog")))


class MentionCounter:
    """Counts each tracked competitor's names (and JFrog's) in page text, URLs ignored. Run it on the full fetched
    page before any truncation: list articles often name a competitor only far down the page. The title is not
    counted here; the classifier weights title mentions itself (TITLE_WEIGHT)."""

    def __init__(self, cfg: ci_config.CIConfig):
        self.patterns = {c.key: _alias_re(aliases(c)) for c in cfg.competitors if c.key != INDUSTRY}
        spec = {"competitors": {k: rx.pattern for k, rx in sorted(self.patterns.items())},
                "jfrog": JFROG_RE.pattern, "urls": URL_RE.pattern}
        # stored with the counts, so it is traceable which competitor list and name rules produced them
        self.config_hash = hashlib.sha1(json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest()[:12]

    def __call__(self, text: str) -> tuple[dict[str, int], bool]:
        page = strip_urls(text)
        return {key: len(rx.findall(page)) for key, rx in self.patterns.items()}, bool(JFROG_RE.search(page))


def format_hint(counts: dict[str, int]) -> str:
    """'sonatype×3, snyk×1', most mentioned first; empty when there are none."""
    hits = sorted(((k, n) for k, n in counts.items() if n), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(f"{k}×{n}" for k, n in hits)


def rule_category(title: str) -> tuple[str | None, str]:
    """The one category the title's keywords point to, or None with the reason it is ambiguous."""
    hits = [c for c, rx in CATEGORY_RES.items() if rx.search(title)]
    if len(hits) == 1:
        return hits[0], f"title keywords: {hits[0]}"
    if hits:
        return None, f"title matches several categories: {', '.join(hits)}"
    return None, "no category keywords in title"


def title_hint(title: str) -> str | None:
    """Why the title needs judgment rather than rules, if it does."""
    if NOISE_HINT_RE.search(title):
        return "title looks like market chatter"
    if MARKETING_HINT_RE.search(title):
        return "title looks like marketing, an event, a report or a listicle"
    if len(ROUNDUP_RE.findall(title)) >= ROUNDUP_MIN_COMMAS:
        return "title looks like a roundup of several subjects"
    return None


class Classifier:
    def __init__(self, llm: JsonLLM, cfg: ci_config.CIConfig | None = None, batch_size: int = BATCH_SIZE,
                 runs_dir: Path | None = RUNS_DIR):
        self.llm = llm
        self.runs_dir = runs_dir  # where <run_id>.mentions.json side files are read from; None to skip
        self.cfg = cfg or ci_config.load()
        self.batch_size = batch_size
        tracked = [c for c in self.cfg.competitors if c.key != INDUSTRY]
        self.names = {c.key: c.name for c in self.cfg.competitors}
        self.alias_res = {c.key: _alias_re(aliases(c)) for c in tracked}
        self.subject_res = {c.key: _subject_re(aliases(c)) for c in tracked}
        self.competitor_keys = [c.key for c in self.cfg.competitors] + [NON_COMPETITOR]
        self.own = {c.key: own_sources(c) for c in tracked}  # never for the Industry channel

    # ---- rules -------------------------------------------------------------------------------------------------

    def is_first_party(self, item: dict) -> bool:
        """True when the item came from the prefilled competitor's own feed host or GitHub repo."""
        own = self.own.get(item.get("competitor") or "", set())
        origin = item.get("origin") or ""
        if item.get("source") == "github_releases":
            return f"repo:{origin.lower()}" in own
        if item.get("source") == "vendor_feed":
            return bool(origin) and _host(origin) in own
        return False

    def _mention_weights(self, item: dict) -> dict[str, int]:
        """TITLE_WEIGHT x title hits, plus text mentions: over the full page when known, else the stored text.
        The only place the title is weighted; page counts never include it."""
        title = strip_urls(item.get("title") or "")
        text = self.text_counts(item)
        return {key: TITLE_WEIGHT * len(rx.findall(title)) + text[key] for key, rx in self.alias_res.items()}

    def text_counts(self, item: dict) -> dict[str, int]:
        """Mentions in the text per tracked competitor: per key, the max of the stored full-page count and the count
        over the stored text, so a competitor or alias added after the counts were taken is never zeroed."""
        stored = strip_urls(content_text(item))
        full = item["mentions"] if has_full_mentions(item) else {}
        return {key: max(_as_count(full.get(key)), len(rx.findall(stored))) for key, rx in self.alias_res.items()}

    def title_named(self, item: dict) -> str | None:
        """For an item prefilled as industry: the one tracked competitor its title names (whole word, aliases
        included), or None. Two or more named, or a chatter/marketing/roundup title, name nothing here."""
        if (item.get("competitor") or "") != INDUSTRY:
            return None
        title = item.get("title") or ""
        if title_hint(title):
            return None
        named = [key for key, rx in self.alias_res.items() if rx.search(title)]
        return named[0] if len(named) == 1 else None

    def title_competitor(self, item: dict) -> str | None:
        """The competitor settled by rule: named in the title and its subject ("GitHub launches ...", "GitHub's
        ..."). Named elsewhere in the title, it is left to the LLM with a hint (see classify)."""
        key = self.title_named(item)
        return key if key and self.subject_res[key].search(item.get("title") or "") else None

    def apply_rules(self, item: dict) -> tuple[Classification | None, str]:
        """A rules classification, or None with why the item is ambiguous."""
        prefilled, title = item.get("competitor") or "", item.get("title") or ""
        if prefilled not in self.alias_res:
            return None, f"prefilled competitor {prefilled!r} has no name rules (industry goes to the LLM)"
        hint = title_hint(title)
        if hint:
            return None, hint
        weights = self._mention_weights(item)
        own = weights[prefilled]
        rival = max((k for k in weights if k != prefilled), key=lambda k: weights[k], default=None)
        if rival is not None and weights[rival] > own:  # None: only one competitor is tracked
            return None, f"{self.names[rival]} dominates ({weights[rival]} vs {own})"
        named = [k for k, rx in self.alias_res.items() if k != prefilled and rx.search(title)]
        if named:
            return None, f"title also names {', '.join(self.names[k] for k in named)}"
        in_title = bool(self.alias_res[prefilled].search(title))
        first_party = item.get("source") in FIRST_PARTY_SOURCES and self.is_first_party(item)
        if not (in_title or first_party):
            return None, f"{self.names[prefilled]} not in the title and not a first-party source"
        category, why = rule_category(title)
        if category is None and item.get("source") == "github_releases" and why.startswith("no category"):
            category, why = PRODUCT, "a release of the competitor's repo"
        if category is None:
            return None, why
        where = "title" if in_title else "own source"
        return Classification(id=item["id"], competitor=prefilled, category=category, noise=False,
                              mentions_jfrog=mentions_jfrog(item), confidence=RULES_CONFIDENCE, method="rules",
                              reason=f"{self.names[prefilled]} in {where}; {why}"), ""

    # ---- LLM -----------------------------------------------------------------------------------------------------

    def schema(self, ids: list[str]) -> dict:
        return {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "enum": ids},
                    "competitor": {"type": "string", "enum": self.competitor_keys},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "noise": {"type": "boolean"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["id", "competitor", "category", "noise", "confidence"],
            }}},
            "required": ["items"],
        }

    def prompt(self, items: list[dict]) -> str:
        comps = "\n".join(f"- {c.key}: {c.name}" + (f" ({', '.join(c.aliases)})" if c.aliases else "")
                           for c in self.cfg.competitors if c.key != INDUSTRY)
        cats = "\n".join(f"- {c}: {d}" for c, d in CATEGORY_DEFINITIONS.items())
        payload = [{"id": it["id"], "prefilled_competitor": it.get("competitor"), "source": it.get("source"),
                    "found_by": it.get("origin"), "publisher": it.get("publisher") or "",
                    "title": it.get("title") or "", "text": content_text(it)[:LLM_TEXT_CHARS],
                    **({"hint": it["_title_hint"]} if it.get("_title_hint") else {}),
                    **({"full_text_mentions": hint}
                       if has_full_mentions(it) and (hint := format_hint(self.text_counts(it))) else {})}
                   for it in items]
        return f"""You classify news items for JFrog's competitive-intelligence team.
JFrog sells a software supply chain platform: Artifactory (artifact and package repositories), Xray (security
scanning), Curation, and AI/MCP tooling. The team tracks these competitors:
{comps}

For every item below, answer with its id and:
1. competitor: the key of the tracked competitor the story is mainly about. The prefilled competitor is only the
   search query that found the item and may be wrong. Use "{INDUSTRY}" for industry news that matters to JFrog
   without centering on one tracked competitor (software supply chain attacks, malicious packages, AI agent and MCP
   security). Use "{NON_COMPETITOR}" when the story is about none of the tracked competitors and is not such
   industry news.
2. category: exactly one primary category:
{cats}
3. noise: true when the item is irrelevant to JFrog's competitive picture: stock-price or trading chatter,
   a different company with a confusable name, generic marketing or listicles, or news outside software supply chain,
   DevSecOps and developer tooling. Noise is independent of competitor: a GitHub story can still be noise.
4. confidence: 0 to 1, how sure you are of the competitor and category together.

Some items carry full_text_mentions: how often each tracked competitor is named across the whole page, which can
be far longer than the text shown (e.g. "sonatype×3, snyk×1"). Use it to judge what a list or comparison article is
really about, even when the passage naming the competitor is not in the text shown.

Some items carry a hint "Competitor named in title: <key> — company or platform?": the title names that
competitor but not as its subject. Use its key only when the story is about the company or its product; when the
title names it as the place something happened (malware in GitHub repositories), keep "{INDUSTRY}".

Answer only about the ids given, once each.

Items (JSON):
{json.dumps(payload, ensure_ascii=False, indent=1)}
"""

    def _fallback(self, item: dict, why: str, error: str = "InvalidAnswer") -> Classification:
        """Degraded: the LLM failed for this item. The prefilled competitor is kept, marked unconfirmed, and the
        item goes to review; nothing here looks like a normal classification."""
        category, _ = rule_category(item.get("title") or "")
        return Classification(id=item["id"], competitor=item.get("competitor") or NON_COMPETITOR, category=category,
                              noise=False, mentions_jfrog=mentions_jfrog(item), confidence=LOW_CONFIDENCE,
                              method="fallback", reason=f"LLM answer unusable ({why}); kept the prefilled competitor",
                              degraded=True, competitor_confirmed=False, needs_review=True,
                              review_reason=f"classifier unavailable: {error}")

    def _from_answer(self, item: dict, ans: dict, ambiguous_why: str) -> Classification:
        comp, cat, noise, conf = (ans.get(k) for k in ("competitor", "category", "noise", "confidence"))
        problems = []
        if comp not in self.competitor_keys:
            problems.append(f"competitor {comp!r}")
        if cat not in CATEGORIES:
            problems.append(f"category {cat!r}")
        if not isinstance(noise, bool):
            problems.append(f"noise {noise!r}")
        if isinstance(conf, bool) or not isinstance(conf, int | float):
            problems.append(f"confidence {conf!r}")
        if problems:
            return self._fallback(item, "invalid " + ", ".join(problems))
        return Classification(id=item["id"], competitor=comp, category=cat, noise=noise,
                              mentions_jfrog=mentions_jfrog(item), confidence=min(1.0, max(0.0, float(conf))),
                              method="llm", reason=f"ambiguous: {ambiguous_why}")

    def classify_batch(self, items: list[dict], why: dict[str, str]) -> list[Classification]:
        ids = [it["id"] for it in items]
        try:
            answer = self.llm.complete(self.prompt(items), self.schema(ids))
            rows = answer.get("items") if isinstance(answer, dict) else None
            if not isinstance(rows, list):
                raise LLMError(f"no items list in answer: {str(answer)[:200]}")
        except Exception as e:  # one bad batch must not stop the run
            log.warning("classifier batch of %d failed: %s", len(items), e)
            return [self._fallback(it, f"call failed: {e}", type(e).__name__) for it in items]
        by_id: dict[str, dict] = {}
        for row in rows:
            if isinstance(row, dict) and row.get("id") in ids and row["id"] not in by_id:
                by_id[row["id"]] = row  # first answer per id wins; invented ids are dropped
        return [self._from_answer(it, by_id[it["id"]], why[it["id"]]) if it["id"] in by_id
                else self._fallback(it, "item missing from answer", "MissingAnswer") for it in items]

    # ---- entry point -----------------------------------------------------------------------------------------------

    def classify(self, items: list[dict]) -> list[Classification]:
        """One classification per item, in input order. Items without full-page mention counts get them from
        their run's backfill side file when there is one."""
        items = side_mentions.attach(items, self.runs_dir)
        # an industry-query item whose title has a tracked competitor as its subject is about that competitor (the
        # rules or the LLM still decide category and noise); one that only names it goes to the LLM with a hint,
        # still prefilled industry, which stays the fallback
        from_title: dict[str, str] = {}
        tagged = []
        for item in items:
            key = self.title_competitor(item)
            if key:
                from_title[item["id"]] = key
                item = {**item, "competitor": key}
            elif named := self.title_named(item):
                item = {**item, "_title_hint": title_mention_hint(named)}
            tagged.append(item)
        out: dict[str, Classification] = {}
        ambiguous, why = [], {}
        for item in tagged:
            result, reason = self.apply_rules(item)
            if result is not None:
                out[item["id"]] = result
            else:
                ambiguous.append(item)
                why[item["id"]] = reason
        for start in range(0, len(ambiguous), self.batch_size):
            for c in self.classify_batch(ambiguous[start:start + self.batch_size], why):
                out[c.id] = c
        for item_id, key in from_title.items():  # the title settles the competitor, whatever the LLM said
            c = out[item_id]
            out[item_id] = c.model_copy(update={"competitor": key, "reason": f"title names {key}; {c.reason}"})
        return [out[item["id"]] for item in items]


def classify(items: list[dict], llm: JsonLLM, cfg: ci_config.CIConfig | None = None) -> list[Classification]:
    return Classifier(llm, cfg).classify(items)
