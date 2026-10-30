"""Labeling API over a tmp runs dir and a tmp labels file: runs, items, labels, validation."""
import json
import os

import pytest
from fastapi.testclient import TestClient

from ci.labeling.app import create_app
from ci.packet import NON_COMPETITOR

COMPETITORS = ["snyk", "sonatype", "industry"]


def _packet(i: int, competitor: str = "snyk", **kw) -> dict:
    return {"id": f"id{i}", "run_id": "", "source": "google_news", "origin": '"Snyk"', "competitor": competitor,
            "title": f"Story {i}", "url": f"https://a.com/{i}", "original_url": f"https://news.google.com/{i}",
            "url_resolved": True, "published_at": "2026-10-29T10:00:00+00:00", "text": "x" * 3000,
            "text_status": "full", "publisher": "A", "in_24h": True, **kw}


def _write_run(runs_dir, run_id, packets, mtime):
    path = runs_dir / f"{run_id}.jsonl"
    path.write_text("".join(json.dumps({**p, "run_id": run_id}) + "\n" for p in packets), encoding="utf-8")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def env(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    _write_run(runs, "run_old", [_packet(9)], 1_000)
    _write_run(runs, "run_new", [_packet(1), _packet(2, competitor="industry")], 2_000)
    labels = tmp_path / "evals" / "golden_set.jsonl"
    client = TestClient(create_app(runs_dir=runs, labels_path=labels, competitors=COMPETITORS))
    return client, labels


def _label(**kw) -> dict:
    return {"id": "id1", "run_id": "run_new", "competitor": "snyk", "category": "Security", "score": 4,
            "mentions_jfrog": False, "basis": "partial", **kw}


def test_list_runs_newest_first(env):
    client, _ = env
    assert client.get("/api/runs").json() == [{"run_id": "run_new", "items": 2, "status": "ok"},
                                              {"run_id": "run_old", "items": 1, "status": "ok"}]
    meta = client.get("/api/meta").json()
    assert meta["default_run"] == "run_new" and len(meta["categories"]) == 7
    assert meta["competitors"] == [*COMPETITORS, NON_COMPETITOR]


def test_page_and_items(env):
    client, _ = env
    assert "CI Labeling" in client.get("/").text
    items = client.get("/api/runs/run_new/items").json()
    assert [i["id"] for i in items] == ["id1", "id2"] and all(i["label"] is None for i in items)
    assert client.get("/api/runs/nope/items").status_code == 404


def test_run_id_guard_blocks_hidden_and_traversal(env, tmp_path):
    client, _ = env
    _write_run(tmp_path / "runs", ".hidden", [_packet(5)], 3_000)
    (tmp_path / "secret.jsonl").write_text(json.dumps(_packet(6)) + "\n")
    assert client.get("/api/runs/.hidden/items").status_code == 404
    assert client.post("/api/labels", json=_label(id="id6", run_id="../secret")).status_code == 404
    assert [r["run_id"] for r in client.get("/api/runs").json()] == ["run_new", "run_old"]


def test_side_files_are_not_runs(env, tmp_path):
    client, _ = env
    runs = tmp_path / "runs"
    _write_run(runs, "run_new.dropped", [_packet(7)], 5_000)  # newer than every run
    (runs / "run_new.report.json").write_text("{}")
    assert [r["run_id"] for r in client.get("/api/runs").json()] == ["run_new", "run_old"]
    assert client.get("/api/meta").json()["default_run"] == "run_new"
    assert client.post("/api/labels", json=_label()).status_code == 200


def test_malformed_label_lines_are_skipped(env):
    client, labels = env
    labels.parent.mkdir(parents=True)
    labels.write_text('not json\n["a list"]\n{"no_id": 1}\n', encoding="utf-8")
    assert client.get("/api/runs/run_new/items").status_code == 200
    assert client.get("/api/stats").json()["labeled"] == 0


def test_append_after_unterminated_line(env):
    client, labels = env
    labels.parent.mkdir(parents=True)
    labels.write_text('{"id": "half', encoding="utf-8")  # crash mid-write
    assert client.post("/api/labels", json=_label()).status_code == 200
    lines = labels.read_text(encoding="utf-8").splitlines()
    assert lines[0] == '{"id": "half' and json.loads(lines[1])["id"] == "id1"
    assert client.get("/api/runs/run_new/items").json()[0]["label"]["score"] == 4


def test_save_label_appends_with_snapshot(env):
    client, labels = env
    r = client.post("/api/labels", json=_label(note="pricing change", mentions_jfrog=True))
    assert r.status_code == 200
    row = json.loads(labels.read_text().splitlines()[0])
    assert row["category"] == "Security" and row["score"] == 4 and row["noise"] is False and row["mentions_jfrog"]
    assert row["labeled_at"].endswith("+00:00")
    assert row["item"]["title"] == "Story 1" and row["item"]["competitor"] == "snyk"
    assert len(row["item"]["text"]) == 2000
    items = client.get("/api/runs/run_new/items").json()
    assert items[0]["label"]["score"] == 4 and items[1]["label"] is None


def test_relabel_latest_wins(env):
    client, labels = env
    client.post("/api/labels", json=_label(score=2))
    client.post("/api/labels", json=_label(score=5, competitor="sonatype"))
    assert len(labels.read_text().splitlines()) == 2  # append-only
    label = client.get("/api/runs/run_new/items").json()[0]["label"]
    assert label["score"] == 5 and label["competitor"] == "sonatype"
    assert client.get("/api/stats").json()["labeled"] == 1


def test_non_competitor_is_offered_and_accepted(env):
    client, _ = env
    assert client.get("/api/meta").json()["competitors"][-1] == NON_COMPETITOR
    r = client.post("/api/labels", json=_label(competitor=NON_COMPETITOR))
    assert r.status_code == 200 and r.json()["competitor"] == NON_COMPETITOR
    assert client.get("/api/runs/run_new/items").json()[0]["label"]["competitor"] == NON_COMPETITOR


def test_noise_label_needs_no_category_or_score(env):
    client, _ = env
    r = client.post("/api/labels", json={"id": "id2", "run_id": "run_new", "competitor": "industry", "noise": True,
                                             "basis": "full"})
    assert r.status_code == 200 and r.json()["category"] is None and r.json()["score"] is None
    # noise drops whatever category/score the client sent
    r = client.post("/api/labels", json=_label(noise=True, category="Security", score=3))
    assert r.status_code == 200 and r.json()["category"] is None and r.json()["score"] is None
    stats = client.get("/api/stats").json()
    assert stats["noise"] == 2 and stats["relevant"] == 0


@pytest.mark.parametrize("bad", [
    {"category": "Weather"},
    {"score": 0},
    {"score": 6},
    {"competitor": "jfrog"},
    {"category": None},  # non-noise needs a category
    {"score": None},  # and a score
    {"basis": "skimmed"},
    {"basis": None},  # basis is required
])
def test_validation_errors(env, bad):
    client, labels = env
    assert client.post("/api/labels", json=_label(**bad)).status_code == 422
    assert not labels.exists()


def test_unknown_item_or_run(env):
    client, _ = env
    assert client.post("/api/labels", json=_label(id="nope")).status_code == 404
    assert client.post("/api/labels", json=_label(run_id="nope")).status_code == 404


def test_basis_is_stored_and_counted(env):
    client, labels = env
    assert client.post("/api/labels", json=_label(basis="full")).status_code == 200
    assert json.loads(labels.read_text())["basis"] == "full"
    assert client.get("/api/runs/run_new/items").json()[0]["label"]["basis"] == "full"
    assert client.get("/api/stats").json()["per_basis"] == {"full": 1, "partial": 0, "unknown": 0}


def test_missing_basis_is_rejected_but_old_lines_read_back_as_none(env):
    client, labels = env
    body = _label()
    del body["basis"]
    assert client.post("/api/labels", json=body).status_code == 422
    labels.parent.mkdir(parents=True)
    old = {k: v for k, v in _label().items() if k != "basis"} | {"noise": False, "labeled_at": "2026-10-30T09:00Z"}
    labels.write_text(json.dumps(old) + "\n", encoding="utf-8")  # a line written before `basis` existed
    label = client.get("/api/runs/run_new/items").json()[0]["label"]
    assert label["basis"] is None and label["score"] == 4
    assert client.get("/api/stats").json()["per_basis"] == {"full": 0, "partial": 0, "unknown": 1}


def test_side_files_never_list_as_runs(env, tmp_path):
    client, _ = env
    runs = tmp_path / "runs"
    for name in ("run_new.mentions.json", "run_new.queue.json", "run_new.report.json", "run_new.anything.json",
                 "run_new.dropped.jsonl", "run_new.mentions.jsonl"):
        (runs / name).write_text("{}\n", encoding="utf-8")
    assert [r["run_id"] for r in client.get("/api/runs").json()] == ["run_new", "run_old"]


def test_mentions_come_from_the_packet_or_the_side_file(env, tmp_path):
    client, _ = env
    side = {"id1": {"mentions": {"sonatype": 3, "snyk": 1}, "mentions_jfrog": False}, "id2": {"gitlab": 2}}
    (tmp_path / "runs" / "run_new.mentions.json").write_text(json.dumps(side), encoding="utf-8")
    items = {i["id"]: i for i in client.get("/api/runs/run_new/items").json()}
    assert items["id1"]["mentions"] == {"sonatype": 3, "snyk": 1} and items["id2"]["mentions"] == {"gitlab": 2}
    (tmp_path / "runs" / "run_new.mentions.json").write_text("not json", encoding="utf-8")
    assert client.get("/api/runs/run_new/items").json()[0]["mentions"] is None


@pytest.mark.parametrize("make_failed", ["empty", "report"])
def test_failed_or_empty_run_is_listed_but_never_the_default(env, tmp_path, make_failed):
    client, _ = env
    runs = tmp_path / "runs"
    if make_failed == "empty":
        _write_run(runs, "run_newest", [], 3_000)
    else:
        _write_run(runs, "run_newest", [_packet(3)], 3_000)
        (runs / "run_newest.report.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    status = "empty" if make_failed == "empty" else "failed"
    listed = client.get("/api/runs").json()
    assert listed[0] == {"run_id": "run_newest", "items": 0 if status == "empty" else 1, "status": status}
    meta = client.get("/api/meta").json()
    assert meta["default_run"] == "run_new" and meta["run_status"]["run_newest"] == status


def test_only_failed_runs_still_give_a_default(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    _write_run(runs, "only", [], 1_000)
    client = TestClient(create_app(runs_dir=runs, labels_path=tmp_path / "l.jsonl", competitors=COMPETITORS))
    assert client.get("/api/meta").json()["default_run"] == "only"  # nothing better to open
