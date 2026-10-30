

def test_topup_saves_meet_and_carry_the_current_standard(tmp_path):
    """A top-up-queue save needs basis, note and an explicit Bad-extraction answer, and is stamped rubric-v2,
    so labels made now under v2 don't show as 'not reviewed under v2'."""
    import json

    from fastapi.testclient import TestClient

    from ci.labeling.app import create_app

    runs = tmp_path / "runs"
    runs.mkdir()
    item = {"id": "t1", "run_id": "run_t", "source": "google_news", "origin": "q", "competitor": "snyk",
            "title": "Snyk adds X", "url": "https://snyk.io/x", "original_url": "https://snyk.io/x", "text": "t"}
    (runs / "run_t.jsonl").write_text(json.dumps(item) + "\n", encoding="utf-8")
    (runs / "run_t.queue.json").write_text(json.dumps({"version": 1, "mode": "topup", "run_id": "run_t",
                                                       "require_bad_extraction": True, "buckets": [],
                                                       "entries": [{"id": "t1", "bucket": "snyk"}]}), encoding="utf-8")
    labels = tmp_path / "golden.jsonl"
    client = TestClient(create_app(runs_dir=runs, labels_path=labels, competitors=["snyk", "industry"],
                                   relabel_dir=tmp_path / "relabel"))
    base = {"id": "t1", "run_id": "run_t", "competitor": "snyk", "category": "Security", "score": 3,
            "basis": "partial", "bad_extraction": False}
    assert client.post("/api/labels", json={**base, "note": ""}).status_code == 422  # note required here
    row = client.post("/api/labels", json={**base, "note": "sub-feature of existing scanning"}).json()
    assert row["standard"] == "rubric-v2" and row["bad_extraction_explicit"] is True and row["reviewed_at"]
    assert "not_reviewed_v2" not in row["issues"]
