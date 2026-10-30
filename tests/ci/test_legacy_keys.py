"""The aws_codeartifact -> aws rename: every reader maps the legacy key; stored files are never rewritten."""
import json
import sqlite3

from fastapi.testclient import TestClient

from ci import config, coverage, eval_golden, mentions
from ci.classify import aliases
from ci.config import Competitor, canonical_counts, canonical_item, canonical_key
from ci.labeling import stratified
from ci.labeling.app import create_app, latest_labels

RUN = "20261030T0836Z-abc123"
OLD = "aws_codeartifact"


def _row(i="id1", competitor=OLD, **kw):
    return {"id": i, "run_id": RUN, "source": "google_news", "origin": "CodeArtifact", "competitor": competitor,
            "title": "Amazon ECR adds pull-through cache rules", "url": f"https://a/{i}", "original_url": f"https://a/{i}",
            "text": "Amazon ECR now supports pull-through cache rules.", "text_status": "full", "publisher": "AWS",
            "in_24h": True, "published_at": "2026-10-29T10:00:00Z", **kw}


def _label(competitor=OLD, **kw):
    return {"id": "id1", "run_id": RUN, "competitor": competitor, "category": "Product & Features", "score": 3,
            "noise": False, "mentions_jfrog": False, "basis": "full", "item": _row(), **kw}


def test_helpers_map_only_the_legacy_key():
    assert canonical_key(OLD) == "aws" and canonical_key("snyk") == "snyk" and canonical_key(None) is None
    assert canonical_counts({OLD: 2, "aws": 1, "snyk": 3}) == {"aws": 3, "snyk": 3}
    row = canonical_item({"competitor": OLD, "mentions": {OLD: 1}, "item": {"competitor": OLD}})
    assert row == {"competitor": "aws", "mentions": {"aws": 1}, "item": {"competitor": "aws"}}


def test_aws_aliases_never_include_a_bare_company_name():
    aws = config.load().by_key()["aws"]
    names = set(aliases(aws))
    assert {"codeartifact", "amazon ecr", "elastic container registry", "amazon inspector"} <= names
    assert not names & {"aws", "amazon"}
    assert set(aliases(Competitor(key="aws", name="AWS"))) == set()  # the 3-letter key/name add nothing
    assert "amazon" not in aliases(Competitor(key="amzn", name="Amazon", aliases=["Amazon", "AWS"]))


def _app(tmp_path, rows, labels=None):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    labels_path = tmp_path / "golden.jsonl"
    if labels:
        labels_path.write_text("".join(json.dumps(r) + "\n" for r in labels), encoding="utf-8")
    cfg = config.CIConfig(competitors=[Competitor(key="aws", name="AWS", aliases=["Amazon ECR"]),
                                       Competitor(key="industry", name="Industry")])
    return TestClient(create_app(runs_dir=runs, labels_path=labels_path, cfg=cfg)), runs, labels_path


def test_labeling_maps_old_run_items_labels_and_mentions_and_saves_with_aws(tmp_path):
    client, runs, labels_path = _app(tmp_path, [_row()], [_label()])
    (runs / f"{RUN}.mentions.json").write_text(json.dumps({"id1": {"mentions": {OLD: 4}}}), encoding="utf-8")
    before = labels_path.read_text(encoding="utf-8")
    [item] = client.get(f"/api/runs/{RUN}/items").json()
    assert item["competitor"] == "aws" and item["label"]["competitor"] == "aws"
    assert item["mentions"] == {"aws": 4}
    assert labels_path.read_text(encoding="utf-8") == before  # reading never rewrites
    assert "aws" in client.get("/api/meta").json()["competitors"]
    body = {k: v for k, v in _label("aws").items() if k != "item"}
    assert client.post("/api/labels", json=body).status_code == 200
    assert latest_labels(labels_path)["id1"]["competitor"] == "aws"


def test_old_labels_load_as_aws(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text(json.dumps(_label()) + "\n", encoding="utf-8")
    label = latest_labels(path)["id1"]
    assert label["competitor"] == "aws" and label["item"]["competitor"] == "aws"


def test_stored_queue_buckets_are_mapped_but_the_file_is_kept(tmp_path):
    path = stratified.queue_path(tmp_path, RUN)
    stored = {"version": stratified.QUEUE_VERSION, "run_id": RUN, "rules_hash": "x",
              "buckets": [{"name": OLD, "nominal": 6, "target": 1}],
              "entries": [{"id": "id1", "bucket": OLD, "why": "w"}]}
    path.write_text(json.dumps(stored), encoding="utf-8")
    q = stratified.load_or_build(tmp_path, RUN, [], set(), config.CIConfig(competitors=[]))
    assert q["buckets"][0]["name"] == "aws" and q["entries"][0]["bucket"] == "aws"
    assert json.loads(path.read_text(encoding="utf-8")) == stored


def test_mentions_side_file_keys_are_mapped(tmp_path):
    (tmp_path / f"{RUN}.mentions.json").write_text(json.dumps({"id1": {"mentions": {OLD: 2}}}), encoding="utf-8")
    [item] = mentions.attach([{"id": "id1", "run_id": RUN}], tmp_path)
    assert item["mentions"] == {"aws": 2}


def test_eval_rebuilds_old_items_and_snapshots_with_aws(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN}.jsonl").write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    item, used_snapshot = eval_golden.rebuild_item(_label(), runs, {})
    assert item["competitor"] == "aws" and not used_snapshot
    gone = {**_label(), "run_id": "gone"}
    item, used_snapshot = eval_golden.rebuild_item(gone, runs, {})
    assert item["competitor"] == "aws" and used_snapshot


def test_coverage_maps_old_events_and_run_items(tmp_path):
    events = tmp_path / "events.yaml"
    events.write_text("""events:
  - id: ecr-cache
    competitor: aws_codeartifact
    date: 2026-10-29
    title: Amazon ECR adds pull-through cache rules
    official_url: https://aws.amazon.com/about-aws/whats-new/2026/10/ecr-cache/
    category: Product & Features
    expected_importance: 3
    match:
      title_keywords: [[ECR], [pull-through]]
""", encoding="utf-8")
    [ev] = coverage.load_events(events)
    assert ev.competitor == "aws"
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN}.jsonl").write_text(json.dumps(_row()) + "\n", encoding="utf-8")
    report = coverage.run(RUN, runs_dir=runs, events_path=events, out_dir=tmp_path / "out")
    assert report["by_competitor"]["aws"]["captured"] == 1
    assert report["events"][0]["matches"][0]["competitor"] == "aws"


def test_change_detection_stores_migrate_legacy_rows(tmp_path):
    from ci.changes.diff import CellStore
    from ci.changes.snapshot import SnapshotStore

    db = tmp_path / "cells.sqlite"
    CellStore(db)  # create the tables
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO cells (competitor, axis, value) VALUES (?, 'pricing_model', 'pay per use')", (OLD,))
    store = CellStore(db)
    rows = store._db.execute("SELECT competitor FROM cells").fetchall()
    assert rows == [("aws",)]
    snaps = tmp_path / "snaps.sqlite"
    SnapshotStore(snaps, tmp_path / "s")
    with sqlite3.connect(snaps) as con:
        con.execute("INSERT INTO snapshots VALUES (?, 'pricing', 'u', 'h', '2026-10-30T00:00:00+00:00', 'p')", (OLD,))
    assert SnapshotStore(snaps, tmp_path / "s")._db.execute("SELECT competitor FROM snapshots").fetchall() == [("aws",)]
