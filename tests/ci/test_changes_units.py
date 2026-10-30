"""Change detection building blocks: snapshots, extraction parsing, value normalization, section diffs."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ci.changes import config
from ci.changes.diff import normalize_value, same_field, section_diff, tier_changes, tokens
from ci.changes.extract import (
    AxisField,
    Tier,
    extract_fields,
    missing_numbers,
    name_levels,
    numbers_in,
    parse_fields,
    price_in_quote,
    quote_in_text,
    render_tiers,
    schema_for,
)
from ci.changes.snapshot import SnapshotStore, content_hash, normalize_text
from ci.llm import FakeLLM

FIX = Path(__file__).parent / "fixtures" / "changes"
T0 = datetime(2026, 10, 30, tzinfo=UTC)


# --- snapshots ---

def test_normalized_text_ignores_whitespace_and_markup_reflow():
    page = (FIX / "pricing_v1.html").read_text()
    reflowed = page.replace("<p>The Pro plan", "<p>\n\n   The   Pro\tplan").replace("</p>", "  </p>\n\n")
    assert content_hash(normalize_text(page)) == content_hash(normalize_text(reflowed))
    assert "  " not in normalize_text(reflowed)


def test_snapshot_store_keeps_the_last_n_per_page(tmp_path):
    store = SnapshotStore(tmp_path / "s.sqlite", tmp_path / "snaps", keep=3)
    for i in range(5):
        store.add("acme", "pricing", "https://acme.test", f"version {i}", T0 + timedelta(minutes=i))
    store.add("acme", "product", "https://acme.test/p", "product", T0)
    hist = store.history("acme", "pricing")
    assert [s.text() for s in hist] == ["version 4", "version 3", "version 2"]
    assert hist[0].hash == content_hash("version 4") and hist[0].fetched_at == T0 + timedelta(minutes=4)
    assert len(list((tmp_path / "snaps" / "acme" / "pricing").glob("*.txt"))) == 3
    assert store.latest("acme", "product").text() == "product"
    assert store.latest("acme", "nope") is None
    store.close()


# --- extraction ---

def test_quote_matching_ignores_case_whitespace_and_typography():
    text = "Every plan runs as a managed cloud service.\nEnterprise customers can also self‑host it — today."
    assert quote_in_text("every plan  runs as a managed\ncloud service", text)
    assert quote_in_text("Every plan runs as a managed ... can also self-host it - today", text)
    assert not quote_in_text("Every plan runs ... cloud service", text)  # elided parts under 20 chars
    assert not quote_in_text("Every plan runs as a managed ... it", text)
    assert not quote_in_text("Every plan runs on premises", text)
    assert not quote_in_text("", text)
    # elided parts must appear in order
    assert not quote_in_text("Enterprise customers can also ... Every plan runs as a managed", text)


def test_a_quote_not_on_the_page_sets_confidence_zero():
    text = "The Pro plan costs $150 per month."
    fields = parse_fields({
        "pricing_model": {"value": "Pro $150/month", "evidence": "The Pro plan costs $150 per month",
                          "confidence": 0.9},
        "deployment": {"value": "SaaS", "evidence": "Runs in the cloud", "confidence": 0.95},
    }, ["pricing_model", "deployment"], text)
    assert fields["pricing_model"].confidence == 0.9 and fields["pricing_model"].quote_verified
    assert fields["deployment"].confidence == 0.0 and not fields["deployment"].quote_verified


def test_numbers_are_normalized_and_zero_is_ignored():
    assert numbers_in("Pro $1,950.00/year, Free $0, 2 GB, 1.10 per GB") == {"1950", "2", "1.1"}


def test_every_number_in_the_value_and_tiers_must_be_on_the_page():
    text = "The Pro plan costs $1,950 per year. Storage is $0.25 per GB. The Free plan has no fee."
    assert missing_numbers("Pro $1950/year; storage $0.25/GB; Free $0", [Tier(name="Free", price=0)], text) == []
    assert missing_numbers("Pro $1950/year", [Tier(name="Pro", price=2100)], text) == ["2100"]
    assert missing_numbers("Pro $2,100/year with 50 GB", [], text) == ["2100", "50"]
    raw = {"value": "Pro $2100/year", "evidence": "The Pro plan costs $1,950 per year", "confidence": 0.9}
    fields = parse_fields({"pricing_model": raw}, ["pricing_model"], text)
    assert fields["pricing_model"].confidence == 0 and fields["pricing_model"].quote_verified
    assert fields["pricing_model"].unverified_reason == "numbers not on the page: 2100"


SONATYPE_TEXT = ("Sonatype solutions use a consumption-based pricing model for cloud and self-hosted deployment "
                 "models.\nPro Edition (Cloud) $1,950/year for 1 user and 10k requests.")
SONATYPE_TIERS = [{"name": "Pro Edition (Cloud)", "price": 1950, "currency": "USD", "period": "year"}]


def test_a_generic_pricing_quote_leaves_the_pricing_cell_unconfirmed():
    raw = {"value": "Pro $1950/year", "confidence": 1.0, "tiers": SONATYPE_TIERS,
           "evidence": "Sonatype solutions use a consumption-based pricing model"}
    f = parse_fields({"pricing_model": raw}, ["pricing_model"], SONATYPE_TEXT)["pricing_model"]
    assert f.quote_verified and f.confidence == 0
    assert f.unverified_reason == "pricing quote states none of the extracted prices"


def test_a_pricing_quote_with_a_price_line_is_confirmed():
    raw = {"value": "Pro $1950/year", "confidence": 1.0, "tiers": SONATYPE_TIERS,
           "evidence": "Pro Edition (Cloud) $1,950/year"}
    f = parse_fields({"pricing_model": raw}, ["pricing_model"], SONATYPE_TEXT)["pricing_model"]
    assert f.confidence == 1.0 and f.unverified_reason == ""


def test_price_in_quote_needs_a_priced_tier():
    assert price_in_quote("Free for open source", [Tier(name="Free", price=0), Tier(name="Enterprise")])
    assert not price_in_quote("Pro for teams", [Tier(name="Pro", price=50)])
    assert price_in_quote("Pro is $50.00 a month", [Tier(name="Pro", price=50)])


def test_the_pricing_value_is_rendered_from_the_tiers_not_taken_from_the_model():
    text = "Team $1,200 per year. Pro $50/month per user. Enterprise: contact sales."
    raw = {"value": "a lovely summary", "evidence": "Pro $50/month per user", "confidence": 0.9, "tiers": [
        {"name": "Enterprise"}, {"name": "Pro", "price": 50, "currency": "$", "period": "monthly", "unit": "user"},
        {"name": "Team", "price": 1200, "currency": "usd", "period": "annually"}]}
    f = parse_fields({"pricing_model": raw}, ["pricing_model"], text)["pricing_model"]
    assert f.value == "Pro $50/user/month; Team $1,200/year; Enterprise (no price listed)"
    assert [(t.name, t.currency, t.period) for t in f.tiers] == [("Pro", "USD", "month"), ("Team", "USD", "year"),
                                                                 ("Enterprise", "", "")]
    shuffled = {**raw, "value": "other words", "tiers": list(reversed(raw["tiers"]))}
    assert parse_fields({"pricing_model": shuffled}, ["pricing_model"], text)["pricing_model"].value == f.value


def test_one_plan_at_several_prices_becomes_levels_ordered_by_price():
    pro = [Tier(name="Pro", price=p, currency="USD", period="year") for p in (4800, 1200, 7500, 1950, 1200)]
    assert [(t.name, t.price) for t in name_levels(pro)] == [
        ("Pro (level 1)", 1200), ("Pro (level 2)", 1950), ("Pro (level 3)", 4800), ("Pro (level 4)", 7500)]
    labeled = [Tier(name="Pro - 1 user / 10k requests", price=1950), Tier(name="Pro - 5 users", price=4800)]
    assert [t.name for t in name_levels(labeled)] == ["Pro - 1 user / 10k requests", "Pro - 5 users"]
    assert render_tiers(name_levels(pro)).startswith("Pro (level 1) $1,200/year; Pro (level 2) $1,950/year")


def test_missing_or_malformed_axes_parse_as_not_stated():
    tiers = [{"name": "Pro", "price": "$150"}, {"name": "Free", "price": 0}]
    fields = parse_fields({"pricing_model": {"value": "", "confidence": "high", "tiers": tiers}},
                          ["pricing_model", "ai_mcp"], "page")
    assert not fields["ai_mcp"].stated and fields["ai_mcp"].confidence == 0
    assert [t.name for t in fields["pricing_model"].tiers] == ["Free"]  # the unparseable price is dropped
    assert fields["pricing_model"].value == "Free 0"  # rendered from the remaining tier


def test_extraction_asks_for_exactly_the_page_axes_with_structured_pricing():
    page = config.TrackedPage(key="pricing", url="https://acme.test/pricing", page_type="pricing",
                              axes=["pricing_model", "deployment"])
    llm = FakeLLM([{}])
    extract_fields(llm, "Acme", page, "Acme pricing page text")
    prompt, schema = llm.calls[0]
    assert schema == schema_for(["pricing_model", "deployment"])
    assert schema["required"] == ["pricing_model", "deployment"]
    tier = schema["properties"]["pricing_model"]["properties"]["tiers"]["items"]["properties"]
    assert {"name", "price", "currency", "period"} <= set(tier)
    assert "tiers" not in schema["properties"]["deployment"]["properties"]
    assert "Acme pricing page text" in prompt and "https://acme.test/pricing" in prompt


# --- diffing ---

@pytest.mark.parametrize(("a", "b"), [
    ("Pro $1,950 / year", "pro $1950/year"),
    ("Pro $150.00 per month.", "PRO  $150 per month"),
    ("SaaS,\n self-hosted", "saas, self-hosted"),
])
def test_value_normalization_ignores_whitespace_case_and_number_format(a, b):
    assert normalize_value(a) == normalize_value(b)


def test_value_normalization_keeps_real_differences():
    assert normalize_value("Pro $150/month") != normalize_value("Pro $180/month")
    assert normalize_value("Pro $1.5k") != normalize_value("Pro $15k")


def prose(value: str, axis: str = "package_coverage") -> AxisField:
    return AxisField(axis=axis, value=value)


def priced(*tiers: Tier) -> AxisField:
    return AxisField(axis="pricing_model", value="summary", tiers=list(tiers))


@pytest.mark.parametrize(("a", "b"), [
    ("npm, Maven, PyPI", "PyPI, maven and npm"),  # list order
    ("Pro 150 USD/month", "Pro $150/month"),  # $ vs USD
    ("$5 per user per month", "$5 / users / month"),  # user vs users
    ("Pro $150/mo", "Pro $150 per month"),  # /mo vs /month
    ("Team $1,200 annually", "team $1200.00/yr"),
    ("SaaS, self-hosted and air-gapped", "air-gapped; SaaS; self-hosted"),
])
def test_prose_values_compare_as_token_sets(a, b):
    assert tokens(a) == tokens(b)
    assert same_field(prose(a), prose(b))


@pytest.mark.parametrize(("a", "b"), [
    ("npm, Maven", "npm, Maven, Go"),
    ("Pro $150/month", "Pro $180/month"),
    ("Pro $150/month", "Pro $150/year"),
    ("SaaS", "SaaS and self-hosted"),
])
def test_prose_values_keep_real_differences(a, b):
    assert not same_field(prose(a), prose(b))


def test_pricing_compares_the_tier_set_not_the_wording():
    old = priced(Tier(name="Pro", price=150, currency="usd", period="month"), Tier(name="Enterprise"))
    assert same_field(old, AxisField(axis="pricing_model", value="Enterprise on request, Pro is 150 dollars monthly",
                                     tiers=[Tier(name="Enterprise", currency="USD", period="year"),
                                            Tier(name="PRO", price=150.0, currency="$", period="monthly")]))
    assert not same_field(old, priced(Tier(name="Pro", price=180, currency="USD", period="month"),
                                      Tier(name="Enterprise")))
    assert not same_field(old, priced(Tier(name="Pro", price=150, currency="EUR", period="month"),
                                      Tier(name="Enterprise")))


def test_a_free_tier_with_price_zero_equals_one_without_a_price():
    assert same_field(priced(Tier(name="Free", price=0, currency="USD", period="month")), priced(Tier(name="Free")))
    assert not same_field(priced(Tier(name="Starter", price=0)), priced(Tier(name="Starter")))


def test_swapped_tier_prices_are_a_change():
    a = priced(Tier(name="Pro", price=50, period="month"), Tier(name="Enterprise", price=950, period="month"))
    b = priced(Tier(name="Pro", price=950, period="month"), Tier(name="Enterprise", price=50, period="month"))
    assert not same_field(a, b)


def test_tier_changes_lists_added_removed_and_repriced_tiers():
    old = [Tier(name="Free", price=0), Tier(name="Pro", price=150, currency="USD", period="month"),
           Tier(name="Legacy", price=10, currency="USD", period="month")]
    new = [Tier(name="Team", price=90, currency="USD", period="month"), Tier(name="free"),
           Tier(name="PRO", price=150, currency="$", period="year", unit="user")]
    assert tier_changes(old, new) == [
        {"tier": "Legacy", "change": "removed", "old": "$10/month", "new": ""},
        {"tier": "PRO", "change": "changed", "old": "$150/month", "new": "$150/user/year"},
        {"tier": "Team", "change": "added", "old": "", "new": "$90/month"},
    ]
    assert tier_changes(old, list(reversed(old))) == []
    assert tier_changes([Tier(name="Pro", price=150, currency="USD")],
                        [Tier(name="Pro", price=150, currency="USD", unit="user")]) == []  # unit is not compared


def test_section_diff_keeps_only_the_hunk_around_the_evidence():
    old = "\n".join(f"line {i}" for i in range(40))
    new = old.replace("line 5", "line five").replace("line 30", "line thirty")
    diff = section_diff(old, new, ["line 30", "line thirty"])
    assert "-line 30" in diff and "+line thirty" in diff and "line five" not in diff
    both = section_diff(old, new, ["no anchor here"])  # no hunk matches: all of them
    assert "+line five" in both and "+line thirty" in both
