"""Change detection end to end, offline: HTML fixtures behind an injected fetch, FakeLLM for extraction (PRD D13).

Ofri's required cases: an unchanged page (same hash, no LLM call, no item), a real change (a price edited: diff and
a Changes item) and a cosmetic change (a footer date edited: the LLM is called, the fields are equal, no item).
"""
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ci.changes.__main__ import main
from ci.changes.config import TrackedPage, TrackedPages
from ci.changes.diff import CellStore
from ci.changes.run import DB_NAME, run
from ci.changes.snapshot import FetchError
from ci.llm import FakeLLM, LLMError

FIX = Path(__file__).parent / "fixtures" / "changes"
PRICING_URL = "https://acme.test/pricing"
PRODUCT_URL = "https://acme.test/product"
T1 = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)
T2 = T1 + timedelta(days=1)
T3 = T2 + timedelta(days=1)

PAGES = TrackedPages(competitors={"acme": [
    TrackedPage(key="pricing", url=PRICING_URL, page_type="pricing", axes=["pricing_model", "deployment"]),
    TrackedPage(key="product", url=PRODUCT_URL, page_type="product",
                axes=["package_coverage", "security_scanning", "cicd_integration"]),
]})


def html(name: str) -> str:
    return (FIX / f"{name}.html").read_text(encoding="utf-8")


class Site:
    """The injected fetch: url -> fixture HTML, or an exception to raise. Records the urls fetched."""

    def __init__(self, pages: dict[str, str | Exception]):
        self.pages, self.fetched = dict(pages), []

    def __call__(self, url: str) -> str:
        self.fetched.append(url)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return page


def page_text(prompt: str) -> str:
    return prompt.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]


def answer(prompt: str, schema: dict) -> dict:
    """What a well-behaved model would extract from the fixture pages: values follow the page, quotes are verbatim."""
    text, axes, out = page_text(prompt), schema["properties"], {}
    if "pricing_model" in axes:
        pro = re.search(r"The Pro plan costs \$(\d+) per month", text)
        out["pricing_model"] = {
            "value": f"Free $0/month; Pro ${pro[1]}/month; Enterprise contact sales",
            "evidence": pro[0], "confidence": 0.9,
            "tiers": [{"name": "Free", "price": 0, "currency": "USD", "period": "month"},
                      {"name": "Pro", "price": float(pro[1]), "currency": "USD", "period": "month"},
                      {"name": "Enterprise"}]}
    if "deployment" in axes:
        out["deployment"] = {"value": "SaaS; self-hosted and air-gapped on Enterprise",
                             "evidence": "Enterprise customers can also self-host Acme Registry", "confidence": 0.8}
    if "package_coverage" in axes:
        out["package_coverage"] = {"value": "npm, Maven, PyPI, Docker, Go, Helm",
                                   "evidence": "npm, Maven, PyPI, Docker, Go and Helm packages", "confidence": 0.9}
    if "security_scanning" in axes:
        out["security_scanning"] = {"value": "vulnerability and malicious-code scanning",
                                    "evidence": "scanned for known vulnerabilities and malicious code",
                                    "confidence": 0.8}
    if "cicd_integration" in axes:
        out["cicd_integration"] = {"value": "GitHub Actions, Jenkins, GitLab CI plugins",
                                   "evidence": "Native plugins for GitHub Actions, Jenkins and GitLab CI",
                                   "confidence": 0.8}
    return out


@pytest.fixture
def env(tmp_path):
    site = Site({PRICING_URL: html("pricing_v1"), PRODUCT_URL: html("product")})
    llm = FakeLLM(answer)

    def go(now, **kw):
        return run(PAGES, llm=kw.pop("llm", llm), fetch=site, names={"acme": "Acme"}, data_dir=tmp_path / "data",
                   out_dir=tmp_path / "out", now=now, **kw)

    return site, llm, go, tmp_path


def statuses(result) -> dict[str, str]:
    return {r.page_key: r.status for r in result.pages}


def cells(tmp_path) -> CellStore:
    return CellStore(tmp_path / "data" / DB_NAME)


def test_baseline_stores_cells_and_emits_no_item(env):
    site, llm, go, tmp = env
    res = go(T1)
    assert statuses(res) == {"pricing": "baseline", "product": "baseline"}
    assert res.items == [] and len(llm.calls) == 2
    assert res.report["baseline"] == 2 and res.report["changes"] == 0
    store = cells(tmp)
    got = {c.axis: c for c in store.all("acme")}
    assert set(got) == {"pricing_model", "deployment", "package_coverage", "security_scanning", "cicd_integration"}
    assert got["pricing_model"].value == "Free $0/month; Pro $150/month; Enterprise contact sales"
    assert got["pricing_model"].source_url == PRICING_URL and got["pricing_model"].as_of == T1
    assert [t.price for t in got["pricing_model"].tiers] == [0, 150, None]
    assert [h["event"] for h in store.history("acme", "pricing_model")] == ["baseline"]
    store.close()
    assert len(list((tmp / "data" / "snapshots" / "acme" / "pricing").glob("*.txt"))) == 1
    assert (tmp / "out" / f"{res.run_id}.jsonl").read_text() == ""


def test_unchanged_page_skips_the_llm_and_emits_no_item(env):
    site, llm, go, tmp = env
    go(T1)
    calls = len(llm.calls)
    res = go(T2)
    assert len(llm.calls) == calls  # same hash: no extraction
    assert statuses(res) == {"pricing": "unchanged", "product": "unchanged"}
    assert res.items == [] and res.report["unchanged_by_hash"] == 2
    store = cells(tmp)
    cell = store.get("acme", "pricing_model")
    assert cell.as_of == T1 and cell.checked_at == T2  # value still from the T1 snapshot, confirmed at T2
    store.close()
    assert len(list((tmp / "data" / "snapshots" / "acme" / "pricing").glob("*.txt"))) == 1


def test_real_change_emits_a_reviewed_changes_item_with_a_diff(env):
    site, llm, go, tmp = env
    go(T1)
    site.pages[PRICING_URL] = html("pricing_price_edit")
    calls = len(llm.calls)
    res = go(T2)
    assert len(llm.calls) == calls + 1  # only the pricing page changed hash
    assert statuses(res) == {"pricing": "changed", "product": "unchanged"}
    [item] = res.items
    assert item.competitor == "acme" and item.axis == "pricing_model" and item.axis_label == "Pricing model"
    assert item.page_url == PRICING_URL and item.page_type == "pricing"
    assert "$150" in item.old_value and "$180" in item.new_value
    assert item.old_evidence == "The Pro plan costs $150 per month"
    assert item.new_evidence == "The Pro plan costs $180 per month"
    assert [t.price for t in item.old_tiers if t.name == "Pro"] == [150]
    assert [t.price for t in item.new_tiers if t.name == "Pro"] == [180]
    assert item.old_as_of == T1 and item.new_as_of == T2
    assert item.needs_review is True and "reviewed" in item.reason
    assert "-The Pro plan costs $150 per month" in item.diff and "+The Pro plan costs $180 per month" in item.diff
    assert "Prices updated" not in item.diff  # only the section around the change
    assert res.report["changes"] == 1 and res.report["changed_pages"] == 1

    rows = [json.loads(line) for line in (tmp / "out" / f"{res.run_id}.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == [item.id] and rows[0]["needs_review"] is True
    store = cells(tmp)
    assert "$180" in store.get("acme", "pricing_model").value
    hist = store.history("acme", "pricing_model")
    assert [h["event"] for h in hist] == ["baseline", "changed"] and hist[1]["change_id"] == item.id
    assert store.get("acme", "deployment").value == "SaaS; self-hosted and air-gapped on Enterprise"
    assert [h["event"] for h in store.history("acme", "deployment")] == ["baseline"]
    store.close()


def test_a_date_edited_in_the_footer_element_is_stripped_so_the_hash_is_unchanged(env):
    site, llm, go, _ = env
    go(T1)
    site.pages[PRICING_URL] = html("pricing_footer_tag_edit")
    assert html("pricing_footer_tag_edit") != html("pricing_v1")
    calls = len(llm.calls)
    res = go(T2)
    assert len(llm.calls) == calls and statuses(res)["pricing"] == "unchanged" and res.items == []


def test_cosmetic_change_in_the_article_calls_the_llm_but_emits_no_item(env):
    site, llm, go, tmp = env
    go(T1)
    site.pages[PRICING_URL] = html("pricing_article_date_edit")
    calls = len(llm.calls)
    res = go(T2)
    assert len(llm.calls) == calls + 1  # the hash differs, so the page is re-extracted
    assert "Previous values" not in llm.calls[0][0]  # the baseline extraction has nothing to anchor on
    prompt = llm.calls[-1][0]  # the re-extraction is anchored on the current cells, to keep their wording
    assert '- pricing_model: "Free $0/month; Pro $150/month; Enterprise contact sales"' in prompt
    assert '- deployment: "SaaS; self-hosted and air-gapped on Enterprise"' in prompt
    assert statuses(res)["pricing"] == "same_fields"
    assert res.items == [] and res.report["changed_hash_same_fields"] == 1 and res.report["changes"] == 0
    store = cells(tmp)
    assert [h["event"] for h in store.history("acme", "pricing_model")] == ["baseline"]
    assert store.get("acme", "pricing_model").as_of == T2
    store.close()
    # the new snapshot is stored, so the next run with the same page is unchanged by hash
    assert statuses(go(T3))["pricing"] == "unchanged"


def test_formatting_only_difference_in_the_extracted_value_is_not_a_change(env):
    site, _, go, _ = env
    go(T1)
    site.pages[PRICING_URL] = html("pricing_article_date_edit")

    def reformatted(prompt, schema):
        out = answer(prompt, schema)
        if "pricing_model" in out:
            out["pricing_model"]["value"] = "free  $0.00 / Month;  PRO $150.00/month; enterprise CONTACT sales."
        return out

    assert go(T2, llm=FakeLLM(reformatted)).items == []


def test_a_quote_missing_from_the_page_sets_confidence_zero_and_changes_nothing(env):
    site, _, go, tmp = env
    go(T1)
    site.pages[PRICING_URL] = html("pricing_price_edit")

    def misquoting(prompt, schema):
        out = answer(prompt, schema)
        if "pricing_model" in out:
            out["pricing_model"]["evidence"] = "Pro now costs $180 a month"  # not on the page
        return out

    res = go(T2, llm=FakeLLM(misquoting))
    assert res.items == []  # an unverified value never overwrites a cell
    assert res.report["unconfirmed"] == [{"competitor": "acme", "page": "pricing", "axes": ["pricing_model"]}]
    store = cells(tmp)
    assert "$150" in store.get("acme", "pricing_model").value
    store.close()


def test_one_failing_page_does_not_stop_the_others(env):
    site, _, go, tmp = env
    site.pages[PRICING_URL] = FetchError("HTTP 429")
    res = go(T1)
    assert statuses(res) == {"pricing": "failed", "product": "baseline"}
    assert res.report["status"] == "ok" and res.report["fetched"] == 1
    assert res.report["failures"] == [{"competitor": "acme", "page": "pricing", "url": PRICING_URL,
                                       "error": "FetchError: HTTP 429"}]


def test_a_failed_extraction_stores_no_snapshot_so_the_next_run_retries(env):
    site, _, go, tmp = env
    flaky = FakeLLM([LLMError("503"), answer])  # pricing fails, product succeeds
    res = go(T1, llm=flaky)
    assert statuses(res) == {"pricing": "failed", "product": "baseline"}
    assert res.report["fetched"] == 2 and "LLMError: 503" in res.report["failures"][0]["error"]
    assert not (tmp / "data" / "snapshots" / "acme" / "pricing").exists()
    res = go(T2)
    assert statuses(res) == {"pricing": "baseline", "product": "unchanged"}


def test_every_page_failing_marks_the_run_failed(env):
    site, _, go, _ = env
    site.pages = {PRICING_URL: FetchError("HTTP 500"), PRODUCT_URL: "<html><body></body></html>"}
    res = go(T1)
    assert res.report["status"] == "failed" and len(res.report["failures"]) == 2
    assert "no extractable text" in res.report["failures"][1]["error"]


def test_snapshot_retention_through_runs(env):
    site, _, go, tmp = env
    versions = ["pricing_v1", "pricing_price_edit", "pricing_article_date_edit", "pricing_v1"]
    for i, name in enumerate(versions):
        site.pages[PRICING_URL] = html(name)
        go(T1 + timedelta(hours=i), keep=2)
    files = sorted((tmp / "data" / "snapshots" / "acme" / "pricing").glob("*.txt"))
    assert len(files) == 2
    assert "$150" in files[-1].read_text() and "October 29" in files[0].read_text()


def test_dry_run_fetches_and_hashes_but_stores_nothing(env):
    site, _, go, tmp = env
    res = run(PAGES, llm=None, fetch=site, data_dir=tmp / "data", out_dir=tmp / "out", now=T1)
    assert statuses(res) == {"pricing": "would_extract", "product": "would_extract"}
    assert res.paths == {} and not (tmp / "out").exists() and not (tmp / "data" / "snapshots").exists()
    go(T1)
    res = run(PAGES, llm=None, fetch=site, data_dir=tmp / "data", out_dir=tmp / "out", now=T2)
    assert statuses(res) == {"pricing": "unchanged", "product": "unchanged"}
    store = cells(tmp)
    assert store.get("acme", "pricing_model").checked_at == T1  # a dry run does not touch the cells
    store.close()


def test_competitor_filter(env):
    _, _, _, tmp = env
    two = TrackedPages(competitors={**PAGES.competitors, "other": [
        TrackedPage(key="pricing", url="https://other.test/pricing", page_type="pricing", axes=["pricing_model"])]})
    site = Site({PRICING_URL: html("pricing_v1"), PRODUCT_URL: html("product")})
    res = run(two, llm=FakeLLM(answer), fetch=site, data_dir=tmp / "d", out_dir=tmp / "o", competitors=["acme"])
    assert {r.competitor for r in res.pages} == {"acme"} and "https://other.test/pricing" not in site.fetched


def test_cli_rejects_an_unknown_competitor():
    with pytest.raises(SystemExit) as exc:
        main(["--competitors", "jfrog,nope"])
    assert exc.value.code == 2

