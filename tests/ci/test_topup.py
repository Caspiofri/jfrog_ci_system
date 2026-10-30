"""Top-up labeling queue: model-independent selection, exclusions, one item per story, the queue file, and the
required Bad-extraction answer on page and server. No classifier, ranker or LLM is ever called."""
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from ci import coverage, eval_golden
from ci.config import CIConfig, Competitor, Feed
from ci.labeling import stratified, topup
from ci.labeling.app import create_app

RUN = "20261030T1312Z-abc123"
CFG = CIConfig(competitors=[
    Competitor(key="snyk", name="Snyk", feeds=[Feed(url="https://updates.snyk.io/rss/")]),
    Competitor(key="aws", name="AWS", aliases=["CodeArtifact", "Amazon ECR"],
               feeds=[Feed(url="https://aws.amazon.com/about-aws/whats-new/recent/feed/")]),
    Competitor(key="github", name="GitHub", feeds=[Feed(url="https://github.blog/changelog/feed/")]),
    Competitor(key="industry", name="Industry")])
GOOD = ("The release adds new checks and fixes several bugs reported by customers in the last month. " * 6)


def _it(i, title, competitor="industry", source="google_news", origin="q", publisher="Pub", text=None,
        text_status="full", text_source="page", **kw):
    text = f"{title}. {GOOD}" if text is None else text  # a real article names its own subject
    return {"id": f"i{i}", "run_id": RUN, "title": title, "competitor": competitor, "source": source,
            "origin": origin, "publisher": publisher, "url": f"https://pub{i}.example/{i}", "text": text,
            "text_status": text_status, "text_source": text_source, **kw}


SNYK_FEED = {"source": "vendor_feed", "origin": "https://updates.snyk.io/rss/", "competitor": "snyk"}
AWS_FEED = {"source": "vendor_feed", "origin": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
            "competitor": "aws"}


def _items():
    return [
        _it(1, "Snyk launches Evo remediation agent", **SNYK_FEED),
        _it(2, "Snyk Evo launch coverage", publisher="Other"),  # same story as i1 (keys_fn), another publisher
        _it(3, "Snyk CLI v1.2 released", **SNYK_FEED),
        _it(4, "Snyk secrets inventory", **SNYK_FEED),
        _it(5, "Snyk API checks cover hosts", **SNYK_FEED),
        _it(6, "Snyk for Serverless", **SNYK_FEED),
        _it(10, "Amazon ECR adds replication backfill", **AWS_FEED),
        _it(11, "Amazon EMR cuts its charge", **AWS_FEED),
        _it(12, "CodeArtifact supports Cargo"),  # alias match, prefilled industry
        _it(20, "GitHub package firewall pricing per seat", competitor="github"),
        _it(21, "Acme raises $40M Series B to secure agents"),
        _it(30, "Menu page", text="Menu\nHome\nSign in\nAccept all cookies\nSubscribe\n© 2026 All rights reserved",
            text_status="junk"),
        _it(31, "Another wall", text="Please enable JavaScript in your browser.\nReload Page", text_status="junk"),
        _it(32, "Junk copy of the menu page", text_status="junk", text="Menu\nHome\nSign in\nSubscribe"),
        _it(40, "GitHub Actions lockfiles generally available", competitor="github", source="vendor_feed",
            origin="https://github.blog/changelog/feed/"),
        _it(41, "Workflow lockfiles reach GA for GitHub Actions", competitor="github"),  # same coverage event
        _it(50, "Already labeled story, another copy"),
        *[_it(60 + n, f"Plain story number {n} about supply chains") for n in range(8)],
    ]


STORY = {"i2": "i1", "i32": "i30", "i50": "lab"}  # near-copies the grouping joins


def _keys(items):
    return {it["id"]: STORY.get(it["id"], it["id"]) for it in items}


EVENTS = [coverage.Event(id="gh-lockfiles", competitor="github", date=date(2026, 10, 28),
                         title="GitHub Actions workflow lockfiles are generally available",
                         official_url="https://github.blog/changelog/x", category="Security", expected_importance=4,
                         keyword_groups=[["lockfiles"]])]


@pytest.fixture
def no_models(monkeypatch):
    """Selection must never construct a classifier or call an LLM."""
    import ci.classify
    import ci.llm

    def boom(*a, **k):
        raise AssertionError("a model was used in queue building")

    monkeypatch.setattr(ci.classify.Classifier, "__init__", boom)
    monkeypatch.setattr(ci.llm.GeminiLLM, "complete", boom)
    monkeypatch.setattr(ci.llm.FakeLLM, "complete", boom)
    import ci.rank

    monkeypatch.setattr(ci.rank.Ranker, "__init__", boom)


def _build(labeled=(), target=30, unflagged=4):
    return topup.build_topup(RUN, _items(), list(labeled), CFG, EVENTS, _keys, target, unflagged)


def _by_bucket(q):
    out = {}
    for e in q["entries"]:
        out.setdefault(e["bucket"], []).append(e["id"])
    return out


def test_buckets_from_model_independent_signals(no_models):
    q = _build([{"id": "lab", "title": "Already labeled story"}])
    b = _by_bucket(q)
    assert set(b["extraction_check"]) >= {"i30", "i31"} and "i32" not in b["extraction_check"]  # one per story
    sample = [i for i in b["extraction_check"] if i not in ("i30", "i31")]
    assert len(sample) == 4
    assert b["pricing"] == ["i20"] and b["funding_ma"] == ["i21"]
    assert len(b["snyk"]) == 4 and "i2" not in b["snyk"]
    assert b["aws"][0] in ("i10", "i12")  # title names an AWS product: first
    assert {"i10", "i12"} <= set(b["aws"]) | set(b.get("likely_important", []))
    assert q["mode"] == "topup" and q["require_bad_extraction"] is True


def test_one_item_per_story_and_coverage_events_count_as_one_story(no_models):
    ids = [e["id"] for e in _build()["entries"]]
    assert len(ids) == len(set(ids))
    assert not ({"i1", "i2"} <= set(ids)) and not ({"i30", "i32"} <= set(ids))
    assert len({"i40", "i41"} & set(ids)) <= 1  # both match the lockfiles event


def test_golden_set_stories_are_skipped(no_models):
    q = _build([{"id": "lab", "title": "Already labeled story"}])
    assert "i50" not in {e["id"] for e in q["entries"]} and q["summary"]["excluded_golden_stories"] == 1
    q2 = _build([{"id": "x", "title": "GitHub Actions workflow lockfiles GA", "url": "https://x"}])
    assert not {"i40", "i41"} & {e["id"] for e in q2["entries"]}  # its coverage event is already labeled


def test_unmet_targets_are_reported_not_padded(no_models):
    lone = _it(1, "Snyk launches thing", text_source="feed", **SNYK_FEED)  # feed text: not in the extraction sample
    q = topup.build_topup(RUN, [lone], [], CFG, [], _keys, 30)
    notes = " ".join(q["summary"]["notes"])
    assert "snyk: 1 of 4" in notes and "aws: 0 of 4" in notes and "under the ~30 target; not padded" in notes
    assert q["summary"]["total"] == 1


def test_cli_dry_run_writes_nothing_then_writes_once(tmp_path, monkeypatch, no_models, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN}.jsonl").write_text("".join(json.dumps(i) + "\n" for i in _items()), encoding="utf-8")
    labels = tmp_path / "golden.jsonl"
    labels.write_text("", encoding="utf-8")
    monkeypatch.setattr(topup.ci_config, "load", lambda: CFG)
    monkeypatch.setattr(topup.coverage, "load_events", lambda: EVENTS)
    cache_paths = []
    monkeypatch.setattr(topup.eval_golden, "story_keys",
                        lambda items, runs_dir, cache_path=None: cache_paths.append(cache_path) or _keys(items))
    args = [RUN, "--runs-dir", str(runs), "--labels", str(labels)]
    assert topup.main([*args, "--dry-run"]) == 0 and not stratified.queue_path(runs, RUN).exists()
    assert cache_paths[-1] == eval_golden.EMBED_CACHE_PATH  # the eval's embedding cache, not a re-embed
    assert topup.main(args) == 0
    q = json.loads(stratified.queue_path(runs, RUN).read_text(encoding="utf-8"))
    assert q["mode"] == "topup" and q["require_bad_extraction"] and q["version"] == stratified.QUEUE_VERSION
    assert topup.main(args) == 1  # never overwritten without --force
    assert "top-up queue" in capsys.readouterr().out


def _server(tmp_path, queue):
    runs = tmp_path / "runs"
    runs.mkdir()
    pk = {"source": "google_news", "origin": "q", "competitor": "snyk", "url": "https://a/1", "original_url": "u",
          "text": "t", "text_status": "full", "publisher": "A", "in_24h": True, "published_at": "2026-10-29T10:00:00Z"}
    (runs / f"{RUN}.jsonl").write_text("".join(json.dumps({**pk, "id": i, "run_id": RUN, "title": i}) + "\n"
                                               for i in ("q1", "q2")), encoding="utf-8")
    (runs / "other.jsonl").write_text(json.dumps({**pk, "id": "o1", "run_id": "other", "title": "o"}) + "\n",
                                      encoding="utf-8")
    if queue:
        stratified.queue_path(runs, RUN).write_text(json.dumps(queue), encoding="utf-8")
    return TestClient(create_app(runs_dir=runs, labels_path=tmp_path / "labels.jsonl", competitors=["snyk"]))


TOPUP_QUEUE = {"version": stratified.QUEUE_VERSION, "mode": "topup", "run_id": RUN, "require_bad_extraction": True,
               "rules_hash": "t", "buckets": [{"name": "pricing", "nominal": 1, "target": 1}],
               "entries": [{"id": "q1", "bucket": "pricing", "why": "pricing words"}], "summary": {}}


def _label(item_id, run_id=RUN, **kw):
    return {"id": item_id, "run_id": run_id, "competitor": "snyk", "category": "Security", "score": 3,
            "basis": "full", "note": "checked", **kw}


def test_server_requires_an_explicit_bad_extraction_answer_in_a_topup_queue(tmp_path):
    client = _server(tmp_path, TOPUP_QUEUE)
    r = client.post("/api/labels", json=_label("q1"))
    assert r.status_code == 422 and "bad_extraction" in r.text
    assert client.post("/api/labels", json=_label("q1", bad_extraction=False)).json()["bad_extraction"] is False
    assert client.post("/api/labels", json=_label("q2")).json()["bad_extraction"] is False  # not in the queue
    assert client.post("/api/labels", json=_label("o1", "other")).json()["bad_extraction"] is False  # other run


def test_a_topup_queue_is_served_as_stored_never_rebuilt_and_never_stale(tmp_path):
    client = _server(tmp_path, TOPUP_QUEUE)
    q = client.get(f"/api/runs/{RUN}/queue").json()
    assert q["mode"] == "topup" and q["require_bad_extraction"] and q["stale"] is False
    assert client.post(f"/api/runs/{RUN}/queue/rebuild").json()["mode"] == "topup"


def test_page_shows_a_required_yes_no_and_blocks_save_until_answered(tmp_path):
    page = _server(tmp_path, None).get("/").text
    assert "QUEUE.require_bad_extraction" in page and "Answer Bad extraction: Yes or No" in page
    assert 'requiresBad(item) ? null : false' in page  # unset by default only in such a queue
    assert '"queue · "' not in page  # cards keep the plain queue marker; bucket names only in the chips


def test_story_grouping_is_the_evals():
    assert topup.eval_golden.story_keys is eval_golden.story_keys


def test_unflagged_sample_defaults_to_10_and_has_a_cli_flag(tmp_path, monkeypatch, no_models):
    assert topup.UNFLAGGED_SAMPLE == 10
    many = [_it(100 + n, f"Plain page story number {n} about registries") for n in range(15)]
    q = topup.build_topup(RUN, many, [], CFG, [], _keys)
    assert q["buckets"][0]["unflagged_sample"] == 10
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / f"{RUN}.jsonl").write_text("".join(json.dumps(i) + "\n" for i in many), encoding="utf-8")
    (tmp_path / "g.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(topup.ci_config, "load", lambda: CFG)
    monkeypatch.setattr(topup.coverage, "load_events", lambda: [])
    monkeypatch.setattr(topup.eval_golden, "story_keys", lambda items, runs_dir, cache_path=None: _keys(items))
    topup.main([RUN, "--runs-dir", str(runs), "--labels", str(tmp_path / "g.jsonl"), "--unflagged", "3"])
    q = json.loads(stratified.queue_path(runs, RUN).read_text(encoding="utf-8"))
    assert q["buckets"][0]["unflagged_sample"] == 3


def test_a_coverage_event_moves_the_whole_story(no_models):
    """Reproduction: i1 and i2 are one story; only i1 matches the event that i3 (another story) also matches.
    Moving i1 alone left i2 behind as its own story, so two items of one story could be picked."""
    items = [_it(1, "Workflow lockfiles land in Actions", competitor="github"),
             _it(2, "Actions gets a new dependency pinning feature", competitor="github"),
             _it(3, "GitHub lockfiles: what changes for CI", competitor="github")]
    keys = {"i3": "s-a", "i1": "s-b", "i2": "s-b"}  # the event is first seen in s-a; s-b must move whole
    q = topup.build_topup(RUN, items, [], CFG, EVENTS, lambda its: {it["id"]: keys[it["id"]] for it in its}, 30, 0)
    assert len([e for e in q["entries"] if e["id"] in {"i1", "i2", "i3"}]) == 1
    assert q["summary"]["stories"] == 1


def test_a_story_member_without_a_title_does_not_break_pricing(no_models):
    items = [_it(1, "Snyk pricing per seat changes", competitor="snyk"), {**_it(2, "x", competitor="snyk")}]
    del items[1]["title"]
    q = topup.build_topup(RUN, items, [], CFG, [], lambda its: {it["id"]: "s" for it in its}, 30, 0)
    assert [e["id"] for e in q["entries"] if e["bucket"] == "pricing"] == ["i1"]
