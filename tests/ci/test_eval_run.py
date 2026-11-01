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
    assert set(meta) == {"fingerprints", "sheet_sha", "models", "call_settings", "combined", "commit"}
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
