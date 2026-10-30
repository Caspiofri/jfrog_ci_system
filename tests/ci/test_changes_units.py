"""Change detection building blocks: snapshots, extraction parsing, value normalization, section diffs."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ci.changes import config
from ci.changes.diff import normalize_value, same_field, section_diff
from ci.changes.extract import AxisField, Tier, extract_fields, parse_fields, quote_in_text, schema_for
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


def test_missing_or_malformed_axes_parse_as_not_stated():
    tiers = [{"name": "Pro", "price": "$150"}, {"name": "Free", "price": 0}]
    fields = parse_fields({"pricing_model": {"value": "", "confidence": "high", "tiers": tiers}},
                          ["pricing_model", "ai_mcp"], "page")
    assert not fields["ai_mcp"].stated and fields["ai_mcp"].confidence == 0
    assert not fields["pricing_model"].stated
    assert [t.name for t in fields["pricing_model"].tiers] == ["Free"]  # the unparseable price is dropped


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


def test_same_field_compares_tiers_too():
    old = AxisField(axis="pricing_model", value="Pro", tiers=[Tier(name="Pro", price=150, currency="usd")])
    assert same_field(old, AxisField(axis="pricing_model", value="pro",
                                     tiers=[Tier(name="PRO", price=150.0, currency="USD")]))
    assert not same_field(old, AxisField(axis="pricing_model", value="Pro",
                                         tiers=[Tier(name="Pro", price=180, currency="USD")]))


def test_an_unpriced_tier_ignores_currency_and_period():
    old = AxisField(axis="pricing_model", value="x", tiers=[Tier(name="Enterprise", currency="USD", period="year")])
    assert same_field(old, AxisField(axis="pricing_model", value="x", tiers=[Tier(name="Enterprise")]))


def test_section_diff_keeps_only_the_hunk_around_the_evidence():
    old = "\n".join(f"line {i}" for i in range(40))
    new = old.replace("line 5", "line five").replace("line 30", "line thirty")
    diff = section_diff(old, new, ["line 30", "line thirty"])
    assert "-line 30" in diff and "+line thirty" in diff and "line five" not in diff
    both = section_diff(old, new, ["no anchor here"])  # no hunk matches: all of them
    assert "+line five" in both and "+line thirty" in both
