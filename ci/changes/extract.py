"""Structured extraction of head-to-head cells from a tracked page's text, with the JsonLLM (PRD D13).

Per axis the page informs: a short normalized value, a verbatim quote from the page as evidence, and a confidence.
The quote is checked against the page text; a quote that is not on the page sets the confidence to 0.
"""
import json
import re

from pydantic import BaseModel

from ci.changes.config import AXES, TrackedPage
from ci.llm import JsonLLM

PROMPT_TEXT_CHARS = 30000  # the longest tracked page (jfrog.com/pricing) extracts to ~23k chars
NOT_STATED = "not stated"
ELIDED_PART_MIN_CHARS = 20  # each part of a quote elided with "..." must be at least this long

AXIS_GUIDE = {
    "deployment": "how it can be run: SaaS/cloud, self-hosted, hybrid, air-gapped, which clouds",
    "package_coverage": "package formats and ecosystems supported (npm, Maven, PyPI, Docker, ...): count or list",
    "security_scanning": "vulnerability/SCA scanning, SAST, secrets, container and SBOM capabilities",
    "curation_gating": "blocking or approving open-source packages before use: policies, quarantine, firewalls",
    "ai_mcp": "AI features: AI/ML model management, AI assistants or agents, an MCP server",
    "cicd_integration": "CI/CD: built-in pipelines, or integrations with CI systems",
    "pricing_model": "the pricing model: plans/tiers with their prices, usage-based or credit pricing, free tier",
}


class Tier(BaseModel):
    name: str
    price: float | None = None  # None when the page gives no number ("Contact sales")
    currency: str = ""  # ISO code, e.g. USD
    period: str = ""  # month | year | one-time | ""
    unit: str = ""  # what the price is per, e.g. "user", "GB", "1,000 requests"


class AxisField(BaseModel):
    axis: str
    value: str
    evidence: str = ""
    confidence: float = 0.0
    tiers: list[Tier] = []
    quote_verified: bool = False
    unverified_reason: str = ""  # why confidence was forced to 0: the quote, or a number, is not on the page

    @property
    def stated(self) -> bool:
        return bool(self.value.strip()) and self.value.strip().lower() != NOT_STATED


def schema_for(axes: list[str]) -> dict:
    field = {"type": "object", "properties": {
        "value": {"type": "string", "description": "short normalized value, or 'not stated'"},
        "evidence": {"type": "string", "description": "verbatim quote from the page text supporting the value"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    }, "required": ["value", "evidence", "confidence"]}
    props = {}
    for axis in axes:
        if axis == "pricing_model":
            tier = {"type": "object", "properties": {
                "name": {"type": "string"}, "price": {"type": "number"}, "currency": {"type": "string"},
                "period": {"type": "string", "enum": ["month", "year", "one-time", ""]}, "unit": {"type": "string"},
            }, "required": ["name"]}
            props[axis] = {**field, "properties": {**field["properties"], "tiers": {"type": "array", "items": tier}}}
        else:
            props[axis] = field
    return {"type": "object", "properties": props, "required": list(axes)}


def _previous_block(previous: dict[str, str] | None) -> str:
    """On a re-extraction, the cells' current values: the model keeps a value verbatim when the page still supports
    it. Measured Oct 30: two extractions of the same page text with no anchor reworded every prose axis (7 of 7),
    which would turn every hash change into spurious Changes items."""
    if not previous:
        return ""
    lines = "\n".join(f"- {a}: {json.dumps(v)}" for a, v in previous.items())
    return f"""
Previous values, extracted from an earlier version of this page:
{lines}
For each axis with a previous value: if the page text below still supports it, return the previous value exactly,
character for character, even if you would word it differently. Write a new value only when the facts changed
(e.g. a price, a tier, a supported format or a capability was added or removed). Evidence is always quoted from the
current page text.
"""


def _prices_note(page: TrackedPage) -> str:
    if page.prices_on_page:
        return ""
    return ("Note: this page renders its prices client-side, so the text below has no price numbers. Describe the "
            "pricing model (plans, usage-based or credit pricing, free tier) and give no prices.\n")


def build_prompt(competitor_name: str, page: TrackedPage, text: str, previous: dict[str, str] | None = None) -> str:
    axes = "\n".join(f"- {a} ({AXES[a]}): {AXIS_GUIDE[a]}" for a in page.axes)
    return f"""You extract competitive facts about {competitor_name} from one of its web pages, for a head-to-head
comparison with JFrog.

Page: {page.url} (a {page.page_type} page)
{_prices_note(page)}
For each axis below give:
- value: a short, normalized statement of what the page says (at most ~25 words). Write it so that the same facts
  always give the same wording: plain factual phrasing, no marketing adjectives, numbers as digits.
  For pricing_model, include each tier's name and price in the value (e.g. "Free $0; Pro $150/month; Enterprise
  contact sales"), and also list the tiers in `tiers` (price as a number, currency as an ISO code, period month or
  year, unit such as user or GB).
- evidence: one verbatim quote copied exactly from the page text below (a sentence or phrase, no paraphrase).
  For pricing_model, quote a line that states a price (e.g. "Pro $1,950 per year"), not a general description.
- confidence: 0 to 1, how directly the page states it.
If the page does not say anything about an axis, set value to "{NOT_STATED}", evidence to "" and confidence to 0.

Axes:
{axes}
{_previous_block(previous)}
Page text:
<<<
{text[:PROMPT_TEXT_CHARS]}
>>>"""


_TRANSLATE = str.maketrans({"\u2011": "-", "\u2010": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
                            "—": "-", " ": " ", "…": "..."})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(_TRANSLATE)).strip().casefold()


def quote_in_text(quote: str, text: str) -> bool:
    """The quote appears in the text, ignoring case, whitespace and typographic quotes/dashes. A quote elided with
    "..." matches when each part appears, in order and each part is at least ELIDED_PART_MIN_CHARS long (short
    fragments such as "Pro ... $150" would match almost any pricing page)."""
    parts = [p.strip() for p in _norm(quote).split("...") if p.strip()]
    if not parts or (len(parts) > 1 and any(len(p) < ELIDED_PART_MIN_CHARS for p in parts)):
        return False
    hay, pos = _norm(text), 0
    for part in parts:
        pos = hay.find(part, pos)
        if pos < 0:
            return False
        pos += len(part)
    return True


def _confidence(raw) -> float:
    try:
        return min(1.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return 0.0


def _tiers(raw) -> list[Tier]:
    out = []
    for t in raw if isinstance(raw, list) else []:
        try:
            if isinstance(t, dict) and t.get("name"):
                out.append(Tier.model_validate(t))
        except ValueError:  # a tier with an unparseable price is dropped; the value string still carries it
            continue
    return out


def _num(s: str) -> str:
    s = s.replace(",", "")
    return s.rstrip("0").rstrip(".") if "." in s else s  # 150.00 -> 150, 1.10 -> 1.1


def numbers_in(s: str) -> set[str]:
    """The numbers written in s, normalized ("1,950.00" -> "1950", "1.10" -> "1.1"); 0 is left out ("Free" is $0
    without a digit)."""
    return {n for n in (_num(m) for m in re.findall(r"\d[\d,]*(?:\.\d+)?", s)) if n.strip("0.") != ""}


def _price_str(p: float) -> str:
    return f"{p:.2f}".rstrip("0").rstrip(".")


def missing_numbers(value: str, tiers: list[Tier], text: str) -> list[str]:
    """Numbers in the value or the tier prices that the page text does not contain."""
    wanted = numbers_in(value) | {_price_str(t.price) for t in tiers if t.price}
    return sorted(wanted - numbers_in(text))


def price_in_quote(evidence: str, tiers: list[Tier]) -> bool:
    """The pricing quote states at least one extracted non-zero price ("$1,950" matches 1950). True when no tier has
    a price (a page without prices, or only free tiers): there is nothing to anchor."""
    prices = {_price_str(t.price) for t in tiers if t.price}
    return not prices or bool(prices & numbers_in(evidence))


def parse_fields(answer: dict, axes: list[str], text: str) -> dict[str, AxisField]:
    """One AxisField per axis from the LLM answer; a missing axis is 'not stated'. Confidence is forced to 0 when
    the quote is not on the page, when a number in the value or the tiers is not on the page, or when a pricing
    quote states none of the extracted prices."""
    out = {}
    for axis in axes:
        raw = answer.get(axis) if isinstance(answer.get(axis), dict) else {}
        value = str(raw.get("value") or "").strip() or NOT_STATED
        evidence = str(raw.get("evidence") or "").strip()
        tiers = _tiers(raw.get("tiers"))
        verified = bool(evidence) and quote_in_text(evidence, text)
        reason = "" if verified or not evidence else "evidence quote not on the page"
        missing = missing_numbers(value, tiers, text)
        if missing:
            reason = "; ".join(filter(None, [reason, f"numbers not on the page: {', '.join(missing)}"]))
        no_price = axis == "pricing_model" and verified and not price_in_quote(evidence, tiers)
        if no_price:
            reason = "; ".join(filter(None, [reason, "pricing quote states none of the extracted prices"]))
        ok = verified and not missing and not no_price
        out[axis] = AxisField(axis=axis, value=value, evidence=evidence, tiers=tiers, quote_verified=verified,
                              unverified_reason=reason, confidence=_confidence(raw.get("confidence")) if ok else 0.0)
    return out


def extract_fields(llm: JsonLLM, competitor_name: str, page: TrackedPage, text: str,
                   previous: dict[str, str] | None = None) -> dict[str, AxisField]:
    """`previous`: axis -> the cell's current value, for a re-extraction (see _previous_block)."""
    answer = llm.complete(build_prompt(competitor_name, page, text, previous), schema_for(page.axes))
    return parse_fields(answer, page.axes, text)
