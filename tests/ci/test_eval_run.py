"""The thin eval runner (D53) and the run metadata, offline and on the TRAIN split only: the frozen eval writes its
report unchanged, the runner adds <report>.inputs.json, and LangSmith tracing is off for the whole eval (D51)."""
import json
import os
from pathlib import Path

import pytest

from ci import eval_golden, eval_run, run_meta, tracing
from ci.llm import FakeLLM
from tests.ci.test_eval_golden import CFG, _offline_embeddings, _respond, golden  # noqa: F401  (fixtures)


@pytest.fixture
def train_only(golden, tmp_path):  # noqa: F811
    labels, runs, out = golden
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"version": 1, "sides": {"a": "train", "b": "train", "c": "train"}}))
    return labels, runs, out, split


def test_the_runner_writes_the_report_unchanged_and_its_inputs_next_to_it(train_only):
    labels, runs, out, split = train_only
    kw = dict(split="train", live=True, labels_path=labels, runs_dir=runs, llm=FakeLLM(_respond), cfg=CFG,
              split_path=split)
    report = eval_run.run(out_dir=out, **kw)
    assert report["split"] == "train" and report["n"] == 3
    plain = eval_golden.run(out_dir=None, **{**kw, "llm": FakeLLM(_respond)})
    assert report["fingerprint"] == plain["fingerprint"] and report["metrics"] == plain["metrics"]
    inputs = json.loads(Path(report["inputs_path"]).read_text())
    assert report["inputs_path"] == report["path"].removesuffix(".json") + ".inputs.json"
    assert (inputs["split"], inputs["n"], inputs["report_fingerprint"]) == ("train", 3, report["fingerprint"])
    meta = inputs["metadata"]
    assert meta["fingerprints"]["classify_rank"] == report["fingerprint"]
    assert set(meta) == {"fingerprints", "sheet_sha", "models", "call_settings", "combined", "commit",
                         "portable", "fingerprint_changes"}
    assert meta["models"]["llm"] == report["model"] and meta["call_settings"]["temperature"] == 0.0
    assert len(meta["sheet_sha"]) == 12 and len(meta["commit"]["sha"]) == 40
    assert not (out / "test_runs.log").exists()  # train only: nothing was logged as a test run


def test_no_inputs_file_when_the_eval_wrote_no_report(tmp_path):
    report = eval_run.run(split="train", labels_path=tmp_path / "none.jsonl", runs_dir=tmp_path, out_dir=tmp_path,
                          cfg=CFG)
    assert report["n"] == 0 and report["inputs_path"] is None


def test_tracing_is_off_during_every_eval_whatever_the_env(train_only, monkeypatch):
    labels, runs, out, split = train_only
    for k in (*tracing.SDK_VARS, tracing.ENV_VAR):
        monkeypatch.setenv(k, "true")
    assert tracing.enabled("daily")
    seen = {}

    def spy(prompt, schema):
        seen["enabled"] = tracing.enabled("daily")
        seen["env"] = {k: os.environ[k] for k in (*tracing.SDK_VARS, tracing.ENV_VAR)}
        return _respond(prompt, schema)

    eval_run.run(split="train", live=True, labels_path=labels, runs_dir=runs, out_dir=None, llm=FakeLLM(spy),
                 cfg=CFG, split_path=split)
    assert seen["enabled"] is False and set(seen["env"].values()) == {"false"}
    assert os.environ["LANGSMITH_TRACING"] == "true"  # restored after the eval


def test_tracing_is_off_by_default_and_never_for_an_eval():
    assert not tracing.enabled("daily", {})
    assert not tracing.enabled("daily", {"LANGSMITH_TRACING": "true"})  # the newsletter project's variable
    assert tracing.enabled("daily", {"CI_LANGSMITH_TRACING": "true"})
    for kind in ("eval", "eval_golden", "insights_eval", "refresh"):
        assert not tracing.enabled(kind, {"CI_LANGSMITH_TRACING": "true"})


def test_no_ci_module_reaches_langsmith_except_through_the_switch():
    import re
    from pathlib import Path

    root = Path(eval_run.__file__).parent
    imports = re.compile(r"^\s*(?:import|from)\s+(?:langsmith|langchain)\b|import_module\(\s*[\"']langsmith", re.M)
    users = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                   if imports.search(p.read_text(encoding="utf-8")) and p.name != "tracing.py")
    assert users == [], f"only ci/tracing.py may name langsmith: {users}"


def test_metadata_combines_everything_but_the_commit(tmp_path):
    a = run_meta.collect(fingerprints={"classify_rank": "c", "lens": "l", "insights": "i"}, model="m")
    b = run_meta.collect(fingerprints={"classify_rank": "c", "lens": "l", "insights": "i"}, model="m",
                         repo=tmp_path)  # not a git checkout: no commit, same combined fingerprint
    assert a["combined"] == b["combined"] and b["commit"] == {"sha": None, "dirty": None}
    sheet = tmp_path / "sheet.md"
    sheet.write_text("other sheet")
    c = run_meta.collect(fingerprints={"classify_rank": "c", "lens": "l", "insights": "i"}, model="m",
                         sheet_path=sheet)
    assert c["sheet_sha"] != a["sheet_sha"] and c["combined"] != a["combined"]
    assert run_meta.collect(fingerprints={"classify_rank": "c", "lens": "l", "insights": "i"},
                            model="other")["combined"] != a["combined"]


def test_the_recorded_fingerprint_changes_end_at_the_current_values():
    """D51/D53/D59: each deliberate change is recorded old -> new. The legacy classify_rank value hashes absolute
    paths, so it is checked as recorded; the portable value is recomputed here, in whatever checkout runs the test."""
    from ci import insights, lens

    latest = {c["fingerprint"]: c for c in run_meta.FINGERPRINT_CHANGES}
    assert latest["insights"]["new"] == insights.fingerprint()
    cr = latest["classify_rank"]
    assert (cr["old"], cr["new"]) == ("c837f4fdaf70", "99b79890ceea") and cr["prompt_diff"]["differences"] == 0
    assert run_meta.portable_classify_rank() == cr["portable"]
    assert lens.fingerprint() == cr["lens_unchanged"] == "1692c04ba7df"


def _moved_checkout(tmp_path, monkeypatch, rubric_edit=""):
    """The four path constants pointed at a copy of the repo under tmp_path, as in another checkout."""
    from ci import classify, rank

    root = tmp_path / "elsewhere" / "agent_backbone"
    (root / "config").mkdir(parents=True)
    (root / "output" / "runs").mkdir(parents=True)
    (root / "config" / "rubric_v2.md").write_text(rank.RUBRIC_PATH.read_text(encoding="utf-8") + rubric_edit,
                                                  encoding="utf-8")
    monkeypatch.setattr(classify, "OUTPUT_DIR", root / "output")
    monkeypatch.setattr(classify, "RUNS_DIR", root / "output" / "runs")
    monkeypatch.setattr(rank, "CONFIG_DIR", root / "config")
    monkeypatch.setattr(rank, "RUBRIC_PATH", root / "config" / "rubric_v2.md")
    return root


def test_the_portable_fingerprint_is_equal_in_another_checkout_where_the_legacy_one_is_not(tmp_path, monkeypatch):
    here_portable, here_legacy = run_meta.portable_classify_rank(), eval_golden.fingerprint()
    root = _moved_checkout(tmp_path, monkeypatch)
    assert run_meta.portable_classify_rank(repo=root) == here_portable
    assert eval_golden.fingerprint() != here_legacy  # the D59 finding, kept as the legacy behaviour


def test_the_portable_fingerprint_changes_with_the_rubric(tmp_path, monkeypatch):
    here = run_meta.portable_classify_rank()
    root = _moved_checkout(tmp_path, monkeypatch, rubric_edit="\n- one more line\n")
    assert run_meta.portable_classify_rank(repo=root) != here


def test_the_portable_fingerprint_changes_with_a_relevant_config_value():
    from ci import config as ci_config

    cfg = ci_config.load()
    other = cfg.model_copy(deep=True)
    other.competitors[0].name = other.competitors[0].name + " Inc."
    assert run_meta.portable_classify_rank(cfg) != run_meta.portable_classify_rank(other)


def test_the_metadata_records_both_fingerprints():
    meta = run_meta.collect()
    assert meta["portable"]["classify_rank"] == run_meta.portable_classify_rank()
    assert meta["fingerprints"]["classify_rank"] == eval_golden.fingerprint()  # the legacy value, as before
    assert meta["portable"]["combined"] and meta["portable"]["combined"] != meta["combined"]
