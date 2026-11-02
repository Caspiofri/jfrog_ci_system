"""The insights marking sheet (ci.reliability_insights): the stored generation exported verbatim with the sha256 of
the stored row, served on the review page, each insight field and claim field marked and saved on the server, without
touching the store, the item review file or its marks. Offline."""
import hashlib
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ci import reliability_insights as ri
from ci.csrf import CSRFMiddleware
from ci.labeling import reliability_page
from ci.store import Store
from tests.ci.test_api import RUN2, build

GEN = {"status": "ok", "window": {"days": 7}, "level": "strict", "trigger": "daily", "sheet": True,
       "model": "gemini-x", "fingerprint": "9ec366312774", "generated_at": "2026-10-31T04:03:00+00:00", "error": "",
       "rejected": [{"title": "t", "pattern": "p", "reason": "quote not found"}], "candidates": [],
       "input_item_ids": ["new2", "pub1"],
       "insights": [{"insight_id": "ins_2026-10-31_1", "pattern": "competitor_momentum", "title": "GitHub moves",
                     "summary": "s", "why_it_matters": "w", "claims": [
                         {"text": "GitHub ships a firewall", "item_ids": ["pub1"], "quote": "Lorem ipsum dolor",
                          "quote_item_id": "pub1", "jfrog_quote": ""},
                         {"text": "Copilot agents are GA and JFrog has Curation", "item_ids": ["new2", "pub1"],
                          "quote": "Lorem ipsum", "quote_item_id": "new2", "jfrog_quote": "Curation blocks"}]}]}


@pytest.fixture
def env(tmp_path):
    store_path, _, _ = build(tmp_path)
    with Store(store_path) as s:
        s.save_insights("2026-10-31", GEN)
    reviews = tmp_path / "reviews"
    path = ri.export(RUN2, store_path=store_path, out_dir=reviews)
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)
    reliability_page.add_routes(app, reviews, store_path)
    return TestClient(app), path, store_path, reviews


def test_the_export_holds_the_generation_exactly_as_stored(env):
    _, path, store_path, _ = env
    data = json.loads(path.read_text())
    raw = sqlite3.connect(store_path).execute("SELECT data FROM insights WHERE brief_date = '2026-10-31'").fetchone()[0]
    assert data["stored"] == json.loads(raw)
    assert data["source"]["data_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert (data["brief_date"], data["source"]["fingerprint"]) == ("2026-10-31", "9ec366312774")
    assert data["cited_items"]["pub1"]["score"] == 4 and data["cited_items"]["pub1"]["text_seen"].startswith("Lorem")
    assert len(data["cited_items"]["pub1"]["text_seen"]) == ri.SEEN_TEXT_CHARS
    with pytest.raises(FileExistsError):  # written once, so marks always refer to the same export
        ri.export(RUN2, store_path=store_path, out_dir=path.parent)


def test_the_sheet_lists_every_insight_and_claim_with_its_fields(env):
    c, _, _, _ = env
    assert c.get("/api/reliability-insights").json()["runs"] == [RUN2]
    d = c.get(f"/api/reliability-insights/{RUN2}").json()
    [ins] = d["insights"]
    assert [f["key"] for f in ins["fields"]] == ["pattern", "title", "summary", "why_it_matters"]
    c1, c2 = ins["claims"]
    assert [f["key"] for f in c1["fields"]] == ["claim", "cited", "quote"]  # no JFrog quote, no JFrog field
    assert [f["key"] for f in c2["fields"]] == ["claim", "cited", "quote", "jfrog_quote"]
    assert [(x["id"], x["quote_here"]) for x in c2["items"]] == [("new2", True), ("pub1", False)]
    assert d["marks"] == {} and len(d["rejected"]) == 1
    assert c.get("/reliability/insights").status_code == 200


def test_marks_are_saved_and_nothing_else_is_written(env):
    c, _, store_path, reviews = env
    before = {p.name: p.read_bytes() for p in reviews.iterdir()}
    db_before = sqlite3.connect(store_path).execute("SELECT count(*), max(generated_at) FROM insights").fetchone()
    url = f"/api/reliability-insights/{RUN2}/marks"
    r = c.put(url, json={"target": "ins_2026-10-31_1/c2", "field": "jfrog_quote", "mark": "wrong", "note": "n"})
    assert r.status_code == 200 and r.json()["mark"] == "wrong"
    c.put(url, json={"target": "ins_2026-10-31_1", "field": "title", "mark": "right"})
    marks = c.get(f"/api/reliability-insights/{RUN2}").json()["marks"]
    assert marks["ins_2026-10-31_1/c2"]["jfrog_quote"]["note"] == "n" and marks["ins_2026-10-31_1"]["title"]["mark"]
    after = {p.name: p.read_bytes() for p in reviews.iterdir()}
    assert set(after) - set(before) == {f"insights_{RUN2}.marks.json"}
    assert all(after[k] == v for k, v in before.items())  # the export itself is never rewritten
    assert sqlite3.connect(store_path).execute("SELECT count(*), max(generated_at) FROM insights").fetchone() == \
        db_before
    rows = c.get(f"/api/reliability-insights/{RUN2}/export").json()["marks"]
    assert len(rows) == 4 + 3 + 4 and sum(r["mark"] is not None for r in rows) == 2


def test_bad_marks_are_refused(env):
    c, _, _, _ = env
    url = f"/api/reliability-insights/{RUN2}/marks"
    assert c.put(url, json={"target": "ins_2026-10-31_1/c1", "field": "jfrog_quote", "mark": "right"}).status_code \
        == 422  # claim 1 has no JFrog quote
    assert c.put(url, json={"target": "nope", "field": "title", "mark": "right"}).status_code == 422
    assert c.put(url, json={"target": "ins_2026-10-31_1", "field": "title", "mark": "maybe"}).status_code == 422
    assert c.get("/api/reliability-insights/..%2Fsecret").status_code == 404
    evil = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    assert c.put(url, json={"target": "ins_2026-10-31_1", "field": "title", "mark": "right"},
                 headers=evil).status_code == 403
