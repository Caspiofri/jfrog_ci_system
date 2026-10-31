"""Reviewing changed head-to-head cells (D9, D13): approve, dismiss (the old value comes back), edit; and the page
note that leaked onto GitLab's Deployment cell."""
from datetime import UTC, datetime

import pytest

from ci.changes.config import PRICES_OFF_PAGE_NOTE, TrackedPage, TrackedPages
from ci.changes.diff import Cell, CellStore, ChangeItem
from ci.changes.run import cell_note, run
from ci.llm import FakeLLM
from tests.ci.test_changes import PRICING_URL, T1, Site, html

T0, T2 = datetime(2026, 10, 30, 12, tzinfo=UTC), datetime(2026, 10, 31, 12, tzinfo=UTC)


def cell(value, evidence, as_of):
    return Cell(competitor="snyk", axis="pricing_model", value=value, evidence=evidence, confidence=0.9,
                source_url="https://snyk.io/plans/", page_key="plans", as_of=as_of, checked_at=as_of)


def change(old, new):
    return ChangeItem(id="chg1", run_id="r2", competitor="snyk", axis="pricing_model", axis_label="Pricing model",
                      page_key="plans", page_url="https://snyk.io/plans/", page_type="pricing", old_value=old.value,
                      new_value=new.value, old_evidence=old.evidence, new_evidence=new.evidence, old_confidence=0.9,
                      new_confidence=0.9, old_as_of=old.as_of, new_as_of=new.as_of, diff="-old\n+new", reason="r")


@pytest.fixture
def store(tmp_path):
    s = CellStore(tmp_path / "changes.sqlite")
    old = cell("Team $25/month", "Team $25", T0)
    s.put(old, "r1", "baseline")
    new = cell("Team $30/month", "Team $30", T1)
    s.put(new, "r2", "changed", change(old, new))
    yield s
    s.close()


def events(s):
    return [h["event"] for h in s.history("snyk", "pricing_model")]


def test_a_new_change_awaits_review(store):
    [(item, state)] = store.changes()
    assert item.id == "chg1" and state["status"] == "awaiting_review"


def test_approve_keeps_the_new_value(store):
    store.decide("chg1", "approve", now=T2, note="checked on the page")
    assert store.get("snyk", "pricing_model").value == "Team $30/month"
    assert store.change("chg1")[1]["status"] == "approved" and events(store)[-1] == "approved"


def test_dismiss_restores_the_old_value(store):
    store.decide("chg1", "dismiss", now=T2, reason="wrong_extraction")
    c = store.get("snyk", "pricing_model")
    assert (c.value, c.evidence, c.as_of) == ("Team $25/month", "Team $25", T0) and c.checked_at == T2
    assert store.change("chg1")[1] == {"status": "dismissed", "reason": "wrong_extraction", "note": None,
                                       "value": None, "decided_at": T2.isoformat()}
    assert events(store) == ["baseline", "changed", "dismissed"]


def test_edit_sets_the_analysts_value(store):
    store.decide("chg1", "edit", now=T2, value="Team $30 per developer per month")
    assert store.get("snyk", "pricing_model").value == "Team $30 per developer per month"
    assert store.change("chg1")[1]["status"] == "edited" and events(store)[-1] == "analyst_edit"
    with pytest.raises(ValueError):
        store.decide("chg1", "approve", now=T2)  # already decided


def test_an_edit_needs_a_value_and_a_superseded_change_cannot_be_decided(store):
    with pytest.raises(ValueError, match="value"):
        store.decide("chg1", "edit", now=T2, value="  ")
    store.put(cell("Team $35/month", "Team $35", T2), "r3", "changed")  # the cell moved on
    with pytest.raises(ValueError, match="superseded"):
        store.decide("chg1", "approve", now=T2)
    with pytest.raises(KeyError):
        store.decide("nope", "approve", now=T2)


def test_the_prices_note_goes_on_the_pricing_cell_only():
    page = TrackedPage(key="pricing", url=PRICING_URL, page_type="pricing", axes=["pricing_model", "deployment"],
                       prices_on_page=False)
    assert cell_note(page, "pricing_model") == PRICES_OFF_PAGE_NOTE and cell_note(page, "deployment") == ""
    explicit = TrackedPage(key="docs", url=PRICING_URL, page_type="docs", axes=["deployment"], note="beta docs")
    assert cell_note(explicit, "deployment") == "beta docs"


def answer(prompt, schema):
    return {"pricing_model": {"value": "Free, Pro and Enterprise plans",
                              "evidence": "The Enterprise plan is priced on request", "confidence": 0.7},
            "deployment": {"value": "not stated", "evidence": "", "confidence": 0}}


def test_a_stored_leaked_note_is_repaired_on_the_next_run_without_a_history_event(tmp_path):
    page = TrackedPage(key="pricing", url=PRICING_URL, page_type="pricing", axes=["pricing_model", "deployment"],
                       prices_on_page=False)
    pages = TrackedPages(competitors={"acme": [page]})
    site = Site({PRICING_URL: html("pricing_v1")})
    run(pages, llm=FakeLLM(answer), fetch=site, data_dir=tmp_path / "d", out_dir=tmp_path / "o", now=T1)
    s = CellStore(tmp_path / "d" / "changes.sqlite")
    assert s.get("acme", "deployment").note == ""
    s.set_note("acme", "deployment", PRICES_OFF_PAGE_NOTE)  # as stored before the fix
    before = len(s.history("acme", "deployment"))
    s.close()
    run(pages, llm=FakeLLM(answer), fetch=site, data_dir=tmp_path / "d", out_dir=tmp_path / "o", now=T2)
    s = CellStore(tmp_path / "d" / "changes.sqlite")
    assert s.get("acme", "deployment").note == "" and s.get("acme", "pricing_model").note == PRICES_OFF_PAGE_NOTE
    assert len(s.history("acme", "deployment")) == before
    s.close()
