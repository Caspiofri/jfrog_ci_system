"""Cross-run relabel queue: selection, order, storage outside output/runs, the page API and the reason rule."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from ci.labeling import relabel
from ci.labeling.app import RUNS_DIR, create_app

COMPETITORS = ["snyk", "sonatype", "github", "aws", "industry"]
CUTOFF = "2026-10-30T15:30:00Z"
BEFORE, AFTER = "2026-10-30T10:00:00+00:00", "2026-10-30T16:00:00+00:00"


def _packet(i, run_id, title, **kw):
    return {"id": i, "run_id": run_id, "source": "google_news", "origin": "q", "competitor": "snyk", "title": title,
            "url": f"https://a.com/{i}", "original_url": f"https://a.com/{i}", "url_resolved": True,
            "published_at": "2026-10-29T10:00:00+00:00", "text": "body " * 50, "text_status": "full",
            "publisher": "A", "in_24h": True, **kw}


def _label(i, run_id, title, competitor, score, category="Security", noise=False, at=BEFORE, **kw):
    return {"id": i, "run_id": run_id, "competitor": competitor, "category": None if noise else category,
            "score": None if noise else score, "noise": noise, "mentions_jfrog": False, "note": "",
            "labeled_at": at, "item": {"title": title}, **kw}


LABELS = [  # id, run, title, competitor, score, extra
    ("a1", "r1", "Snyk low", "snyk", 2, {}),
    ("a2", "r1", "Snyk high", "snyk", 5, {}),
    ("a3", "r2", "AWS thing", "aws_codeartifact", 3, {}),  # legacy key sorts as aws
    ("a4", "r2", "Noise item", "github", None, {"noise": True}),
    ("a5", "r1", "Sonatype pricing", "sonatype", 4, {"category": "Pricing & Packaging"}),
    ("a6", "r2", "Late but wanted", "sonatype", 3, {"at": AFTER}),
    ("a7", "r2", "Late, not wanted", "github", 3, {"at": AFTER}),
    ("a8", "r1", "GitHub product", "github", 3, {"category": "Product & Features"}),
]


@pytest.fixture
def env(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    by_run = {}
    for i, run_id, title, *_ in LABELS:
        extra = {"mentions": {"snyk": 3}, "mentions_jfrog": True, "extraction_reasons": ["nav"],
                 "prefilter": "stock", "teaser": "t"} if i == "a2" else {}
        by_run.setdefault(run_id, []).append(_packet(i, run_id, title, **extra))
    for run_id, packets in by_run.items():
        (runs / f"{run_id}.jsonl").write_text("".join(json.dumps(p) + "\n" for p in packets), encoding="utf-8")
    labels = tmp_path / "golden_set.jsonl"
    labels.write_text("".join(json.dumps(_label(i, r, t, c, s, **x)) + "\n" for i, r, t, c, s, x in LABELS),
                      encoding="utf-8")
    db = tmp_path / "changes.sqlite"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE cells (competitor TEXT, axis TEXT, value TEXT, evidence TEXT, as_of TEXT)")
        con.executemany("INSERT INTO cells VALUES (?, ?, ?, ?, ?)", [
            ("jfrog", "security_scanning", "Xray", "block vulnerable packages", "2026-10-30T11:57:00+00:00"),
            ("jfrog", "curation_gating", "Curation", "automated policies", "2026-10-30T11:57:00+00:00"),
            ("jfrog", "pricing_model", "Pro $50/month", "$50 / Month", "2026-10-30T11:57:00+00:00"),
            ("jfrog", "ai_mcp", "MCP registry", "MCP servers", "2026-10-30T11:57:00+00:00"),
            ("sonatype", "pricing_model", "not jfrog", "x", "2026-10-30T11:57:00+00:00")])
    con.close()
    out = tmp_path / "relabel"
    q = relabel.build(labels, runs, CUTOFF, first=["Sonatype pricing", "Late but wanted"],
                      include=["Late but wanted"], include_reason="Ofri wants it", queue_id="v2")
    relabel.write(q, out)
    client = TestClient(create_app(runs_dir=runs, labels_path=labels, competitors=COMPETITORS, relabel_dir=out,
                                   changes_db=db))
    return client, labels, runs, out, db, q


def _ids(q):
    return [e["id"] for e in q["entries"]]


def test_selection_cutoff_extra_and_noise(env):
    *_, q = env
    assert set(_ids(q)) == {"a1", "a2", "a3", "a4", "a5", "a6", "a8"}  # a7 is late and not asked for
    reasons = {e["id"]: e["reason"] for e in q["entries"]}
    assert reasons["a6"] == "included: Ofri wants it" and reasons["a4"] == "labeled before the cutoff"
    assert {e["id"]: e["run_id"] for e in q["entries"]}["a3"] == "r2"


def test_order_first_then_competitor_and_score_then_noise(env):
    *_, q = env
    # firsts in order; then aws (a3) < github (a8) < snyk 5 (a2) < snyk 2 (a1); noise (a4) last
    assert _ids(q) == ["a5", "a6", "a3", "a8", "a2", "a1", "a4"]


def test_unknown_or_ambiguous_title_fails(env):
    _, labels, runs, *_ = env
    with pytest.raises(SystemExit):
        relabel.build(labels, runs, CUTOFF, first=["No such title"], include=[], include_reason="", queue_id="x")


def test_queue_is_not_a_run_file(env):
    client, _, runs, out, *_ = env
    assert sorted(p.name for p in runs.glob("*.jsonl")) == ["r1.jsonl", "r2.jsonl"]  # story_keys' glob
    assert [p.name for p in out.iterdir()] == ["v2.json"]
    assert relabel.RELABEL_DIR.parent == RUNS_DIR.parent and relabel.RELABEL_DIR != RUNS_DIR
    assert sorted(r["run_id"] for r in client.get("/api/runs").json()) == ["r1", "r2"]
    assert client.get("/api/meta").json()["relabel_queues"] == ["v2"]


def test_existing_queue_is_not_overwritten(env):
    *_, out, _, q = env
    with pytest.raises(SystemExit):
        relabel.write(q, out)


def test_cards_in_order_prefilled_with_the_current_label(env):
    client, *_ = env
    data = client.get("/api/relabel/v2").json()
    assert [c["id"] for c in data["items"]] == ["a5", "a6", "a3", "a8", "a2", "a1", "a4"]
    assert data["total"] == 7 and data["done"] == 0
    aws = next(c for c in data["items"] if c["id"] == "a3")
    assert aws["run_id"] == "r2" and aws["label"]["competitor"] == "aws" and aws["label"]["score"] == 3
    assert client.get("/api/relabel/nope").status_code == 404


def test_no_prediction_fields_in_the_payload(env):
    client, *_ = env
    card = next(c for c in client.get("/api/relabel/v2").json()["items"] if c["id"] == "a2")
    for k in ("mentions", "mentions_jfrog", "extraction_reasons", "prefilter", "teaser", "competitor"):
        assert k not in card
    assert set(card) <= set(relabel.ITEM_FIELDS) | {"label", "done", "jfrog"}


def test_jfrog_cell_only_on_scores_3_and_4(env):
    client, *_ = env
    cards = {c["id"]: c for c in client.get("/api/relabel/v2").json()["items"]}
    pricing = cards["a5"]["jfrog"]  # score 4, Pricing & Packaging
    assert [c["axis"] for c in pricing["cells"]] == ["pricing_model"] and pricing["cells"][0]["quote"] == "$50 / Month"
    assert pricing["cells"][0]["value"] == "Pro $50/month" and pricing["cells"][0]["as_of"].startswith("2026-10-30")
    assert [c["axis"] for c in cards["a3"]["jfrog"]["cells"]] == ["security_scanning", "curation_gating"]
    assert cards["a8"]["jfrog"]["axes"] == ["ai_mcp", "curation_gating", "pricing_model", "security_scanning"]
    assert cards["a2"]["jfrog"] is None and cards["a1"]["jfrog"] is None and cards["a4"]["jfrog"] is None


def test_missing_store_shows_no_baseline(env, tmp_path):
    _, labels, runs, out, *_ = env
    client = TestClient(create_app(runs_dir=runs, labels_path=labels, competitors=COMPETITORS, relabel_dir=out,
                                   changes_db=tmp_path / "missing.sqlite"))
    cards = {c["id"]: c for c in client.get("/api/relabel/v2").json()["items"]}
    assert cards["a5"]["jfrog"] == {"category": "Pricing & Packaging", "missing": True}


def _save(client, card_id, run_id, **kw):
    cur = {k: v for k, v in next(c for c in client.get("/api/relabel/v2").json()["items"]
                                 if c["id"] == card_id)["label"].items()}
    body = {k: cur.get(k) for k in ("competitor", "category", "score", "noise", "mentions_jfrog", "note")}
    body |= {"id": card_id, "run_id": run_id, "basis": "full", "bad_extraction": False} | kw
    return client.post("/api/labels", json=body)


def test_change_without_reason_is_422(env):
    client, labels, *_ = env
    before = labels.read_text()
    r = _save(client, "a2", "r1", score=4)
    assert r.status_code == 422 and "score" in r.json()["detail"]
    assert labels.read_text() == before
    r = _save(client, "a2", "r1", score=4, revision_reason="rubric v2: no direct threat")
    assert r.status_code == 200 and r.json()["relabel"] == {"queue_id": "v2", "changed": ["score"]}
    assert r.json()["revised_from"]["score"] == 5


def test_confirmation_without_reason_counts_as_reviewed(env):
    client, *_ = env
    r = _save(client, "a1", "r1")  # basis and bad_extraction were never set: filling them is no change
    assert r.status_code == 200 and r.json()["relabel"]["changed"] == [] and r.json()["revision_reason"] == ""
    data = client.get("/api/relabel/v2").json()
    assert data["done"] == 1 and next(c for c in data["items"] if c["id"] == "a1")["done"]


def test_save_uses_the_items_original_run(env):
    client, labels, *_ = env
    assert _save(client, "a3", "r1").status_code == 404  # a3 lives in r2
    assert _save(client, "a3", "r2").status_code == 200
    row = next(json.loads(line) for line in labels.read_text().splitlines() if json.loads(line)["id"] == "a3")
    assert row["run_id"] == "r2"


def test_reason_stays_optional_outside_the_queue(env):
    client, *_ = env
    body = {"id": "a7", "run_id": "r2", "competitor": "github", "category": "Security", "score": 1,
            "basis": "full"}  # a7 is not in any relabel queue: score 3 -> 1 with no reason
    r = client.post("/api/labels", json=body)
    assert r.status_code == 200 and "relabel" not in r.json()


def test_cli_writes_the_queue(env, tmp_path):
    _, labels, runs, *_ = env
    out = tmp_path / "cli_out"
    relabel.main(["--cutoff", CUTOFF, "--first", "Snyk high", "--include-title", "id:a7", "--queue-id", "c",
                  "--labels", str(labels), "--runs-dir", str(runs), "--out-dir", str(out)])
    q = json.loads((out / "c.json").read_text())
    assert _ids(q)[0] == "a2" and "a7" in _ids(q) and q["cutoff"].startswith("2026-10-30T15:30")
