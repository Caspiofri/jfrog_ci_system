"""The reproducibility pack (D59), offline: built from labels, the split and saved reports; no article text, no
keys, no train/test leakage; recompute gives the reported numbers back with no LLM call."""
import json

import pytest

from ci import eval_golden, repro
from ci.llm import FakeLLM
from tests.ci.test_eval_golden import CFG, _offline_embeddings, _respond, golden  # noqa: F401  (fixtures)

EVENT = {"competitor": "github", "source_kind": "feed", "in_window": True}
COVERAGE = {"run_id": "r", "events": [{**EVENT, "id": "a", "captured": True, "expected_importance": 4},
                                      {**EVENT, "id": "b", "captured": False, "expected_importance": 3}],
            "overall": {"events": 2, "captured": 1}, "high_importance": {"min": 4, "events": 1, "captured": 1},
            "by_competitor": {"github": {"events": 2, "captured": 1}},
            "by_source_kind": {"feed": {"events": 2, "captured": 1}},
            "runs_dir": "/home/someone/agent_backbone/output/runs",
            "events_file": "/home/someone/agent_backbone/.claude/worktrees/x/evals/coverage_events.yaml"}


@pytest.fixture
def pack(golden, tmp_path):  # noqa: F811
    labels, runs, out = golden
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"version": 1, "sides": {"a": "train", "b": "train", "c": "train"}}))
    eval_golden.run(split="train", live=True, labels_path=labels, runs_dir=runs, out_dir=out, llm=FakeLLM(_respond),
                    cfg=CFG, split_path=split)
    cov = tmp_path / "coverage"
    cov.mkdir()
    (cov / "r.json").write_text(json.dumps(COVERAGE))
    p = tmp_path / "pack"
    repro.build(p, labels_path=labels, split_path=split, evals_dir=out, coverage_dir=cov)
    return p, labels


def test_the_pack_holds_labels_without_article_text(pack):
    p, labels = pack
    rows = [json.loads(x) for x in (p / "labels.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == ["a", "b", "c"] and all(r["split"] == "train" for r in rows)
    latest = eval_golden.latest_labels(labels)
    for r in rows:  # label values copied as they are
        assert r["label"] == {k: latest[r["id"]].get(k) for k in repro.LABEL_FIELDS}
        assert "text" not in json.dumps(r).replace("text_sha256", "") and len(r["text_sha256"]) == 64
    manifest = json.loads((p / "manifest.json").read_text())
    assert len(manifest["eval_reports"]) == 1 and manifest["labels"] == 3
    assert repro.check(p) == []


def test_recompute_gives_every_reported_number_back(pack):
    p, _ = pack
    res = repro.recompute(p)
    [ev] = [v for k, v in res.items() if k.startswith("evals/")]
    assert ev["split"] == "train" and all(m["same"] for m in ev["metrics"].values())
    assert set(ev["metrics"]) == {name for name, *_ in repro.HEADLINE}
    assert ev["sections"] and all(ev["sections"].values())  # every metrics section, by_basis included
    assert {"by_basis", "by_bad_extraction"} <= set(ev["sections"]) and "extraction_detector" not in ev["sections"]
    cov = res["coverage/r.json"]["metrics"]
    assert cov["overall"] == {"captured": 1, "n": 2, "reported": 1, "reported_n": 2, "same": True}
    assert cov["high_importance"]["same"] and cov["competitor.github"]["same"] and cov["source_kind.feed"]["same"]


def test_a_changed_number_is_reported_as_different(pack):
    p, _ = pack
    path = next((p / "reports" / "evals").glob("*.json"))
    r = json.loads(path.read_text())
    r["metrics"]["category"]["accuracy"] = 0.123
    path.write_text(json.dumps(r))
    [ev] = [v for k, v in repro.recompute(p).items() if k.startswith("evals/")]
    assert ev["metrics"]["category_accuracy"]["same"] is False


def test_check_finds_keys_article_text_and_leakage(pack):
    p, _ = pack
    path = next((p / "reports" / "evals").glob("*.json"))
    r = json.loads(path.read_text())
    r["items"][0]["title"] = "x" * 700
    r["items"][1]["reason"] = "AIza" + "B" * 35
    path.write_text(json.dumps(r))
    split = json.loads((p / "split_assignments.json").read_text())
    split["sides"]["a"] = "test"  # a test item inside a train report
    (p / "split_assignments.json").write_text(json.dumps(split))
    problems = repro.check(p)
    assert any("700 characters" in x for x in problems) and any("looks like a key" in x for x in problems)
    assert any("not on its split side" in x for x in problems)
    assert not repro.SECRET_RE.search("https://aws.amazon.com/whats-new/amazon-msk-connect-pause-resume-workers")


def test_the_pack_drops_local_paths_and_check_flags_any_left(pack):
    p, _ = pack
    path = p / "reports" / "coverage" / "r.json"
    r = json.loads(path.read_text())
    assert not set(repro.LOCAL_PATH_KEYS) & set(r) and "/home/" not in path.read_text()
    assert repro.recompute(p)["coverage/r.json"]["metrics"]["overall"]["same"]  # the numbers don't need the paths
    r["note"] = "made from /home/someone/evals/coverage_events.yaml"
    path.write_text(json.dumps(r))
    assert repro.check(p) == ["reports/coverage/r.json.note: a local file path"]
    for ok in ("https://www.businesswire.com/news/home/2026/en/GitLab", "see evals/coverage_events.yaml"):
        assert not repro.LOCAL_PATH_RE.search(ok)


def test_the_breakdowns_take_basis_and_bad_extraction_from_the_pack_labels(pack):
    p, _ = pack
    path = next((p / "reports" / "evals").glob("*.json"))
    r = json.loads(path.read_text())
    assert not set(repro.JOINED_LABEL_FIELDS) & set(r["items"][0]["label"])  # the report doesn't carry them
    rows = [json.loads(x) for x in (p / "labels.jsonl").read_text().splitlines()]
    rows[0]["label"]["basis"] = "partial" if rows[0]["label"]["basis"] == "full" else "full"
    (p / "labels.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    [ev] = [v for k, v in repro.recompute(p).items() if k.startswith("evals/")]
    assert ev["sections"]["by_basis"] is False and ev["sections"]["competitor"] is True
