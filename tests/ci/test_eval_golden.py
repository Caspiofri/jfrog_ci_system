"""Golden-set eval, offline: metrics on a hand-built mini set with known answers, the split, and the end-to-end run."""
import hashlib
import json
from collections import Counter

import numpy as np
import pytest

from ci import eval_golden
from ci.classify import Classification
from ci.config import CIConfig, Competitor
from ci.eval_golden import assign_sides, assign_split, evaluate, format_report, normalize_title, run, story_keys
from ci.llm import FakeLLM, GeminiLLM
from ci.rank import Ranked

CFG = CIConfig(competitors=[Competitor(key="snyk", name="Snyk"), Competitor(key="gitlab", name="GitLab"),
                            Competitor(key="industry", name="Industry")])


def _random_embed(texts):
    """Fake embedding: a pseudo-random 64-d vector per text, so unrelated texts are far below the threshold."""
    return [np.random.default_rng(int(hashlib.sha1(t.encode()).hexdigest()[:8], 16)).normal(size=64).tolist()
            for t in texts]


def _topic_embed(topics):
    """Fake embedding with controlled similarity: texts containing a topic word share that topic's vector, plus a
    small per-text offset (cosine about 0.9 between copies); other texts get random vectors."""
    def embed(texts):
        out = []
        for t, rand in zip(texts, _random_embed(texts), strict=True):
            hit = next((i for i, w in enumerate(topics) if w in t.lower()), None)
            if hit is None:
                out.append(rand)
            else:
                base = np.zeros(64)
                base[hit] = 1.0
                out.append((base + 0.3 * np.array(rand) / np.linalg.norm(rand)).tolist())
        return out
    return embed


@pytest.fixture(autouse=True)
def _offline_embeddings(monkeypatch, tmp_path):
    """No ONNX model and no writes to data/ci in tests."""
    monkeypatch.setattr(eval_golden, "default_embedding_fn", lambda: _random_embed)
    monkeypatch.setattr(eval_golden, "EMBED_CACHE_PATH", tmp_path / "embed_cache.json")
    monkeypatch.setattr(eval_golden, "SPLIT_ASSIGNMENTS_PATH", tmp_path / "split_assignments.json")


def _label(i, competitor, category=None, score=None, noise=False, run_id="run1", **item):
    return {"id": i, "run_id": run_id, "competitor": competitor, "category": category, "score": score,
            "noise": noise, "mentions_jfrog": False, "note": "", "labeled_at": "2026-10-30T12:00:00+00:00",
            "item": {"title": f"Title {i}", "url": f"https://x/{i}", "source": "google_news", "origin": "q",
                     "publisher": "", "published_at": "2026-10-29T10:00:00Z", "text": "t" * 800,
                     "competitor": competitor, **item}}


def _cls(i, competitor, category, noise=False, method="llm"):
    return Classification(id=i, competitor=competitor, category=category, noise=noise, mentions_jfrog=False,
                          confidence=0.5, method=method)


def _ranked(i, score):
    return Ranked(id=i, raw_score=score, score=score, reason="", confidence=0.5)


def test_metrics_on_a_mini_golden_set_with_known_answers():
    labels = [_label("a", "snyk", "Security", 5), _label("b", "gitlab", "AI & Agents", 3),
              _label("c", "snyk", noise=True), _label("d", "industry", "Security", 4)]
    cls = [_cls("a", "snyk", "Security", method="rules"), _cls("b", "snyk", "AI & Agents"),
           _cls("c", "snyk", "Security", noise=True), _cls("d", "industry", "Product & Features", noise=True)]
    ranked = [_ranked("a", 5), _ranked("b", 2), _ranked("c", 1), _ranked("d", 1)]
    m = evaluate(labels, cls, ranked)

    assert m["competitor"]["accuracy"] == 2 / 3  # non-noise only: a, b, d
    assert m["competitor"]["per_competitor"] == {
        "gitlab": {"n": 1, "correct": 0, "accuracy": 0.0},
        "industry": {"n": 1, "correct": 1, "accuracy": 1.0},
        "snyk": {"n": 1, "correct": 1, "accuracy": 1.0}}
    assert m["competitor"]["on_noise"] == {"n": 1, "correct": 1, "accuracy": 1.0}
    assert (m["category"]["correct"], m["category"]["n"]) == (2, 3)  # noise label c is not scored on category
    assert m["noise"] == {"tp": 1, "fp": 1, "fn": 0, "tn": 2, "precision": 0.5, "precision_n": 2, "recall": 1.0,
                          "recall_n": 1}
    # rubric v2: noise has no score. Agreement only over a (5 vs 5) and b (3 vs 2); c (noise/noise) and d (4 vs
    # predicted noise) are excluded because one side is noise
    assert m["score"] == {"n": 2, "exact": 0.5, "within_1": 1.0, "missing": 0, "excluded_noise": 2,
                          "excluded_noise_n": 4}
    # important = score >= 4: a (5 vs 5) is a hit; d (labeled 4, predicted noise) a miss: noise is never important
    assert m["important"] == {"min": 4, "n": 4, "missing": 0, "tp": 1, "fp": 0, "fn": 1, "precision": 1.0,
                              "precision_n": 1, "recall": 0.5, "recall_n": 2}
    assert "precision_at_k" not in m  # P@k is not an eval metric any more
    assert m["by_method"]["rules"] == {"n": 1, "competitor": {"n": 1, "correct": 1, "accuracy": 1.0},
                                       "category": {"n": 1, "correct": 1, "accuracy": 1.0},
                                       "noise": {"n": 1, "correct": 1, "accuracy": 1.0}}
    # llm settled b (competitor wrong), c (noise right) and d (category wrong, noise wrong)
    assert m["by_method"]["llm"] == {"n": 3, "competitor": {"n": 2, "correct": 1, "accuracy": 0.5},
                                     "category": {"n": 2, "correct": 1, "accuracy": 0.5},
                                     "noise": {"n": 3, "correct": 2, "accuracy": 2 / 3}}
    assert m["confusion"]["competitor"] == [{"label": "gitlab", "pred": "snyk", "n": 1}]
    assert m["confusion"]["category"] == [{"label": "Security", "pred": "Product & Features", "n": 1}]


def test_precision_at_k_is_kept_for_daily_run_reports():
    labels = [_label(str(i), "snyk", "Security", 5 if i < 3 else 2) for i in range(12)]
    good_first = [_ranked(str(i), 5 - i // 3) for i in range(12)]
    assert eval_golden.precision_at_k(labels, good_first)["10"] == {"k": 10, "hits": 3, "precision": 0.3, "n": 10}
    bad_first = list(reversed(good_first))
    assert eval_golden.precision_at_k(labels, bad_first)["10"]["precision"] == 1 / 10


def test_undefined_metrics_are_none_not_zero():
    m = evaluate([_label("a", "snyk", "Security", 3)], [_cls("a", "snyk", "Security")], [_ranked("a", 3)])
    assert m["noise"]["precision"] is None and m["noise"]["recall"] is None
    assert (m["noise"]["precision_n"], m["noise"]["recall_n"]) == (0, 0)
    assert m["important"]["precision"] is None and m["important"]["recall"] is None


def test_split_is_deterministic_and_about_a_quarter():
    ids = [f"story {i}" for i in range(2000)]
    first = [assign_split(i) for i in ids]
    assert first == [assign_split(i) for i in ids]
    assert 0.2 < first.count("test") / len(ids) < 0.3
    assert set(first) == {"train", "test"}


def _respond(prompt, schema):
    """Classifier batches get 'snyk / Security'; ranker batches get score 5."""
    props = schema["properties"]["items"]["items"]["properties"]
    ids = props["id"]["enum"]
    if "score" in props:
        return {"items": [{"id": i, "score": 5, "reason": "head-on"} for i in ids]}
    return {"items": [{"id": i, "competitor": "snyk", "category": "Security", "noise": False, "confidence": 0.9}
                      for i in ids]}


@pytest.fixture
def golden(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    production = {"id": "a", "run_id": "run1", "title": "Title a", "source": "google_news", "competitor": "snyk",
                  "text": "PRODUCTION " + "p" * 3000, "text_status": "snippet", "publisher": ""}
    (runs / "run1.jsonl").write_text(json.dumps(production) + "\n", encoding="utf-8")
    labels = tmp_path / "golden_set.jsonl"
    rows = [_label("a", "gitlab", "AI & Agents", 2),
            _label("a", "snyk", "Security", 3),  # relabeled: the later line wins
            _label("b", "snyk", "Security", 5, run_id="gone"),
            _label("c", "snyk", noise=True, run_id="gone", text="short")]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n", encoding="utf-8")
    return labels, runs, tmp_path / "out"


def test_run_end_to_end_with_a_fake_llm(golden):
    labels, runs, out = golden
    llm = FakeLLM(_respond)
    report = run(split="all", live=True, labels_path=labels, runs_dir=runs, out_dir=out, llm=llm, cfg=CFG)
    assert report["n"] == 3 and report["labels_total"] == 3 and not report["aborted"]
    items = {it["id"]: it for it in report["items"]}
    assert items["a"]["label"]["competitor"] == "snyk"  # latest label
    assert items["a"]["text_status"] == "snippet" and not items["a"]["snapshot_text"]  # from the run file
    assert items["b"]["snapshot_text"] and report["snapshot_text_used"] == 2
    assert items["a"]["pred"]["score"] == 4 and items["a"]["pred"]["raw_score"] == 5  # snippet cap
    assert items["a"]["pred"]["review_reasons"] == ["snippet-only item scored >= 4"]
    assert items["b"]["text_status"] == "full" and items["c"]["text_status"] == "snippet"  # inferred from length
    m = report["metrics"]
    assert m["competitor"]["accuracy"] == 1.0 and m["category"]["accuracy"] == 1.0
    assert m["noise"]["fn"] == 1
    assert len(llm.calls) == 2  # one classifier batch, one ranker batch
    assert "PRODUCTION " + "p" * 1400 in llm.calls[0][0]  # the classifier saw the run file's text, not the snapshot
    written = json.loads((out / report["path"].split("/")[-1]).read_text(encoding="utf-8"))
    assert written["metrics"] == json.loads(json.dumps(m))
    table = format_report(report)
    assert "Competitor accuracy" in table and "Precision@" not in table
    assert "Important (score >= 4) precision" in table and "(n=" in table


def test_offline_default_runs_without_an_api_key(golden, monkeypatch):
    labels, runs, out = golden
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    report = run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, cfg=CFG)
    assert report["metrics"]["n"] == 3 and report["path"] is None
    assert {it["pred"]["method"] for it in report["items"]} <= {"rules", "fallback"}  # the abstaining LLM
    assert not report["aborted"]  # offline fallbacks are the baseline, not a failure


def test_empty_or_missing_golden_set_is_graceful(tmp_path, capsys, monkeypatch):
    report = run(split="test", labels_path=tmp_path / "missing.jsonl", runs_dir=tmp_path, out_dir=tmp_path / "o",
                 cfg=CFG)
    assert report["n"] == 0 and report["metrics"] is None and not (tmp_path / "o").exists()
    assert "No labeled items" in format_report(report)
    monkeypatch.setattr(eval_golden, "LABELS_PATH", tmp_path / "missing.jsonl")
    monkeypatch.setattr(eval_golden, "EVALS_OUT_DIR", tmp_path / "o")
    assert eval_golden.main(["--split", "all"]) == 0
    assert "No labeled items" in capsys.readouterr().out


def test_unknown_split_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run(split="dev", labels_path=tmp_path / "x", out_dir=None, cfg=CFG)


def _boom():
    raise RuntimeError("no network in tests")


def test_live_run_with_failing_llm_aborts_and_writes_nothing(golden):
    labels, runs, out = golden
    llm = GeminiLLM(model="m", client_factory=_boom, sleep=lambda s: None)
    report = run(split="all", live=True, labels_path=labels, runs_dir=runs, out_dir=out, llm=llm, cfg=CFG)
    assert report["aborted"] and report["path"] is None and not out.exists()
    assert report["fallbacks"]["classify"] >= 1 and report["fallbacks"]["rank"] >= 1
    assert "WARNING" in format_report(report) and "ABORTED" in format_report(report)


def test_allow_fallback_scores_a_degraded_live_run(golden):
    labels, runs, out = golden
    llm = GeminiLLM(model="m", client_factory=_boom, sleep=lambda s: None)
    report = run(split="all", live=True, labels_path=labels, runs_dir=runs, out_dir=None, llm=llm, cfg=CFG,
                 allow_fallback=True)
    assert not report["aborted"] and report["metrics"]["by_method"]["fallback"]["n"] >= 1
    assert "WARNING" in format_report(report)


def test_main_exits_nonzero_on_live_fallback(golden, monkeypatch, capsys):
    labels, runs, out = golden
    monkeypatch.setattr(eval_golden, "LABELS_PATH", labels)
    monkeypatch.setattr(eval_golden, "RUNS_DIR", runs)
    monkeypatch.setattr(eval_golden, "EVALS_OUT_DIR", out)
    monkeypatch.setattr(eval_golden, "GeminiLLM", lambda: GeminiLLM(model="m", client_factory=_boom,
                                                                    sleep=lambda s: None))
    monkeypatch.setattr(eval_golden.ci_config, "load", lambda: CFG)
    assert eval_golden.main(["--split", "all", "--live"]) == 2
    assert "ABORTED" in capsys.readouterr().out
    assert eval_golden.main(["--split", "all", "--live", "--allow-fallback"]) == 0


@pytest.mark.parametrize("a,b", [
    ("GitLab Orbit is GA!", "gitlab orbit is ga"),
    ("Ruby fixes RCE - The Hacker News", "Ruby fixes RCE"),
    ("Copilot   Fusion: launches", "copilot fusion launches"),
])
def test_normalize_title(a, b):
    assert normalize_title(a) == normalize_title(b)


def test_copies_of_a_story_share_a_key_and_a_side(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    dropped = [  # dedupe drops from two runs: x2 -> x1 in run A, x3 -> x2 in run B (a chain across runs)
        {"id": "x2", "title": "Totally reworded headline", "duplicate_of": "x1"},
        {"id": "x3", "title": "Third wording", "duplicate_of": "x2"},
    ]
    (runs / "A.dropped.jsonl").write_text(json.dumps(dropped[0]) + "\n", encoding="utf-8")
    (runs / "B.dropped.jsonl").write_text(json.dumps(dropped[1]) + "\n", encoding="utf-8")
    items = [{"id": "x1", "title": "GitLab Orbit GA"}, {"id": "x3", "title": "Third wording"},
             {"id": "y1", "title": "Ruby RCE fixed - SecurityWeek", "publisher": "SecurityWeek"},
             {"id": "y2", "title": "Ruby RCE fixed!"}, {"id": "z", "title": "Unrelated"}]
    keys = story_keys(items, runs)
    assert keys["x1"] == keys["x3"]  # joined through the duplicate_of chain
    assert keys["y1"] == keys["y2"]  # same normalized title
    assert len({keys["x1"], keys["y1"], keys["z"]}) == 3
    assert story_keys([{"id": "e1", "title": ""}, {"id": "e2", "title": "!!"}], runs) == \
        {"e1": "e1", "e2": "e2"}  # empty titles never merge
    for _ in range(3):
        sides = {i: assign_split(k) for i, k in story_keys(items, runs).items()}
        assert sides["x1"] == sides["x3"] and sides["y1"] == sides["y2"]


def test_split_in_run_keeps_story_copies_together(tmp_path):
    labels = tmp_path / "golden.jsonl"
    rows = [_label(f"copy{i}", "gitlab", "AI & Agents", 4, title="GitLab Orbit is GA") for i in range(5)]
    rows += [_label(f"other{i}", "snyk", "Security", 3, title=f"Story number {i}") for i in range(40)]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    test = run(split="test", labels_path=labels, runs_dir=tmp_path / "no-runs", out_dir=None, cfg=CFG)
    train = run(split="train", labels_path=labels, runs_dir=tmp_path / "no-runs", out_dir=None, cfg=CFG)
    assert test["n"] + train["n"] == 45 and test["stories"] == 41
    copies = [r for r in (test, train) if any(it["id"].startswith("copy") for it in r["items"])]
    assert len(copies) == 1 and sum(it["id"].startswith("copy") for it in copies[0]["items"]) == 5


def test_fingerprint_is_stable_and_tracks_prompts_and_rules(monkeypatch):
    from ci import classify, rank

    base = eval_golden.fingerprint(CFG)
    assert base == eval_golden.fingerprint(CFG) and len(base) == 12
    monkeypatch.setattr(classify, "CATEGORY_PATTERNS", {**classify.CATEGORY_PATTERNS, "Security": "cve"})
    assert eval_golden.fingerprint(CFG) != base
    monkeypatch.undo()
    monkeypatch.setattr(rank, "RUBRIC", rank.RUBRIC + " ")
    assert eval_golden.fingerprint(CFG) != base
    monkeypatch.undo()
    other = CIConfig(competitors=[*CFG.competitors, Competitor(key="x", name="X")])
    assert eval_golden.fingerprint(other) != base  # the competitor list is in the prompt


def test_test_split_runs_are_logged_with_the_fingerprint(tmp_path):
    labels = tmp_path / "golden.jsonl"
    rows = [_label(f"i{i}", "snyk", "Security", 3, title=f"Story {i}") for i in range(30)]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "out"
    for split in ("test", "train", "test"):
        report = run(split=split, labels_path=labels, runs_dir=tmp_path / "none", out_dir=out, cfg=CFG)
        assert report["fingerprint"] == eval_golden.fingerprint(CFG)
    lines = [json.loads(x) for x in (out / "test_runs.log").read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2  # only the test runs
    assert lines[0]["fingerprint"] == report["fingerprint"] and lines[0]["n"] == report["n"]
    assert set(lines[0]["metrics"]) >= {"competitor", "category", "noise_precision", "score_exact"}
    table = format_report(report)
    assert report["fingerprint"] in table and "test_runs.log" in table


def test_mentions_jfrog_precision_and_recall():
    labels = [_label("a", "snyk", "Security", 3), _label("b", "snyk", "Security", 3),
              _label("c", "snyk", "Security", 3)]
    labels[0]["mentions_jfrog"] = labels[1]["mentions_jfrog"] = True
    cls = [_cls(i, "snyk", "Security") for i in "abc"]
    cls[0].mentions_jfrog = cls[2].mentions_jfrog = True
    m = evaluate(labels, cls, [_ranked(i, 3) for i in "abc"])
    assert m["mentions_jfrog"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "precision_n": 2, "recall": 0.5,
                                   "recall_n": 2}


def test_offline_run_suppresses_the_llm_only_metrics(golden):
    labels, runs, _ = golden
    report = run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, cfg=CFG)
    # offline, only noise items get a score: important and score agreement would measure just those
    assert report["metrics"]["important"] == {"suppressed": "LLM-only metric, offline"}
    assert report["metrics"]["score"] == {"suppressed": "LLM-only metric, offline"}
    table = format_report(report)
    assert "Precision@" not in table and table.count("LLM-only metric, offline") == 2
    assert "Important (score >= 4) recall" not in table and "Score exact" not in table


def test_reworded_copies_join_by_embedding_similarity(tmp_path):
    items = [{"id": "o1", "title": "GitLab Orbit is GA: higher agent accuracy"},
             {"id": "o2", "title": "GitLab Inc. announces general availability of GitLab Orbit"},
             {"id": "o3", "title": "Orbit, now generally available, makes agents cheaper"},
             {"id": "r1", "title": "Ruby fixes the Onigmo regexp bugs behind GitLab CVEs"},
             {"id": "r2", "title": "Ruby fixes three regex engine bugs behind a critical RCE"},
             {"id": "u1", "title": "Unrelated story one"}, {"id": "u2", "title": "Unrelated story two"}]
    embed = _topic_embed(["orbit", "ruby"])
    keys = story_keys(items, tmp_path / "none", embed_fn=lambda: embed, cache_path=tmp_path / "c.json")
    assert keys["o1"] == keys["o2"] == keys["o3"] == "o1"  # smallest member id
    assert keys["r1"] == keys["r2"] == "r1"
    assert len({keys["o1"], keys["r1"], keys["u1"], keys["u2"]}) == 4
    sides = {i: assign_split(k) for i, k in keys.items()}
    assert sides["o1"] == sides["o2"] == sides["o3"] and sides["r1"] == sides["r2"]
    strict = story_keys(items, tmp_path / "none", embed_fn=lambda: embed, threshold=0.999)
    assert strict["o1"] != strict["o2"]  # below the threshold they stay apart


def test_embeddings_are_cached(tmp_path):
    calls = []

    def factory():
        calls.append(1)
        return _random_embed

    items = [{"id": "a", "title": "One", "text": "x"}, {"id": "b", "title": "Two", "text": "y"}]
    cache = tmp_path / "cache.json"
    story_keys(items, tmp_path / "none", embed_fn=factory, cache_path=cache)
    story_keys(items, tmp_path / "none", embed_fn=factory, cache_path=cache)
    assert calls == [1] and len(json.loads(cache.read_text(encoding="utf-8"))) == 2


def test_story_similarity_is_in_the_fingerprint(monkeypatch):
    base = eval_golden.fingerprint(CFG)
    monkeypatch.setattr(eval_golden, "STORY_SIMILARITY", 0.9)
    assert eval_golden.fingerprint(CFG) != base


def test_fingerprint_is_identical_across_processes():
    import subprocess
    import sys

    code = ("from ci.config import CIConfig, Competitor; from ci.eval_golden import fingerprint; "
            "print(fingerprint(CIConfig(competitors=[Competitor(key='snyk', name='Snyk')])))")
    runs = {subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
            for _ in range(3)}
    assert len(runs) == 1


def test_fingerprint_tracks_review_rules(monkeypatch):
    from ci import rank

    base = eval_golden.fingerprint(CFG)
    monkeypatch.setattr(rank, "REVIEW_RULES", [*rank.REVIEW_RULES, ("x", lambda item, cls, score: False)])
    assert eval_golden.fingerprint(CFG) != base


def test_persisted_sides_never_change_when_labels_and_merges_arrive(tmp_path):
    path = tmp_path / "sides.json"
    first = {f"id{i:02d}": f"id{i:02d}" for i in range(40)}  # 40 singleton stories
    sides1, conflicts = assign_sides(first, path)
    assert not conflicts and {"train", "test"} == set(sides1.values())
    persisted = json.loads(path.read_text(encoding="utf-8"))["sides"]
    assert persisted == sides1
    # more labels arrive, and a new run merges stories: every id now belongs to a group keyed "id00"
    second = {f"id{i:02d}": "id00" for i in range(60)}
    sides2, conflicts = assign_sides(second, path)
    assert all(sides2[i] == sides1[i] for i in sides1)  # no persisted side changed
    assert conflicts and set(conflicts[0]["ids"]) == set(second)
    majority = Counter(sides1.values()).most_common(1)[0][0]
    assert all(sides2[f"id{i:02d}"] == majority for i in range(40, 60))  # newcomers follow the group
    after = json.loads(path.read_text(encoding="utf-8"))["sides"]
    assert {k: after[k] for k in sides1} == sides1 and len(after) == 60


def test_new_member_takes_its_groups_persisted_side(tmp_path):
    path = tmp_path / "sides.json"
    path.write_text(json.dumps({"version": 1, "sides": {"a": "test"}}), encoding="utf-8")
    sides, conflicts = assign_sides({"a": "a", "b": "a"}, path)  # whatever the hash of "a" says
    assert sides == {"a": "test", "b": "test"} and not conflicts


def test_split_conflicts_are_reported_in_the_eval(tmp_path):
    labels = tmp_path / "golden.jsonl"
    rows = [_label("p", "snyk", "Security", 3, title="Same story"), _label("q", "snyk", "Security", 3,
                                                                       title="Same story!")]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    split = tmp_path / "sides.json"
    split.write_text(json.dumps({"version": 1, "sides": {"p": "train", "q": "test"}}), encoding="utf-8")
    report = run(split="all", labels_path=labels, runs_dir=tmp_path / "none", out_dir=None, cfg=CFG,
                 split_path=split)
    assert report["split_conflicts"][0]["ids"] == ["p", "q"]
    assert "SPLIT CONFLICT: 1 story groups" in format_report(report)
    assert json.loads(split.read_text(encoding="utf-8"))["sides"] == {"p": "train", "q": "test"}


def test_fingerprint_tracks_the_config_and_eval_knobs(tmp_path, monkeypatch):
    import yaml

    from ci import config as ci_config

    def cfg_with(feed):
        path = tmp_path / f"c{abs(hash(feed))}.yaml"
        path.write_text(yaml.safe_dump({"competitors": [{"key": "snyk", "name": "Snyk", "feeds": [{"url": feed}]}]}),
                        encoding="utf-8")
        return ci_config.load(path)

    base = eval_golden.fingerprint(cfg_with("https://updates.snyk.io/rss/"))
    assert eval_golden.fingerprint(cfg_with("https://updates.snyk.io/rss/")) == base
    assert eval_golden.fingerprint(cfg_with("https://snyk.io/blog/feed/")) != base  # a feed change counts
    for knob in ("EMBED_TEXT_CHARS", "TEST_PERCENT", "IMPORTANT_MIN"):
        monkeypatch.setattr(eval_golden, knob, getattr(eval_golden, knob) + 1)
        assert eval_golden.fingerprint(cfg_with("https://updates.snyk.io/rss/")) != base, knob
        monkeypatch.undo()


def test_fingerprint_tracks_module_source(monkeypatch):
    import inspect

    from ci import classify

    base = eval_golden.fingerprint(CFG)
    real = inspect.getsource
    monkeypatch.setattr(eval_golden.inspect, "getsource",
                        lambda obj: real(obj) + "# edited" if obj is classify else real(obj))
    assert eval_golden.fingerprint(CFG) != base


def test_errors_are_broken_down_by_label_basis():
    labels = [_label("a", "snyk", "Security", 5), _label("b", "gitlab", "AI & Agents", 3),
              _label("c", "snyk", noise=True), _label("d", "industry", "Security", 4)]
    labels[0]["basis"] = labels[1]["basis"] = "full"
    labels[2]["basis"] = "partial"
    labels[3]["basis"] = "skimmed"  # unknown values count as unknown, like labels without a basis
    cls = [_cls("a", "snyk", "Security"), _cls("b", "snyk", "Security"),
           _cls("c", "snyk", "Security", noise=False), _cls("d", "industry", "Security")]
    m = evaluate(labels, cls, [_ranked("a", 5), _ranked("b", 1), _ranked("c", 3), _ranked("d", 4)])
    assert m["by_basis"]["full"] == {
        "n": 2, "competitor": {"n": 2, "errors": 1, "error_rate": 0.5},
        "category": {"n": 2, "errors": 1, "error_rate": 0.5}, "noise": {"n": 2, "errors": 0, "error_rate": 0.0},
        "score": {"n": 2, "errors": 1, "error_rate": 0.5, "off_by_2_plus": 1, "off_by_2_plus_rate": 0.5,
                  "missing": 0}}
    assert m["by_basis"]["partial"] == {  # c: labeled noise, so it has no score to compare
        "n": 1, "competitor": {"n": 0, "errors": 0, "error_rate": None},
        "category": {"n": 0, "errors": 0, "error_rate": None}, "noise": {"n": 1, "errors": 1, "error_rate": 1.0},
        "score": {"n": 0, "errors": 0, "error_rate": None, "off_by_2_plus": 0, "off_by_2_plus_rate": None,
                  "missing": 0}}
    assert m["by_basis"]["unknown"]["n"] == 1 and m["by_basis"]["unknown"]["score"]["errors"] == 0
    report = {"split": "all", "live": True, "model": "m", "fingerprint": "f", "n": 4, "labels_total": 4,
              "stories": 4, "split_counts": {}, "aborted": False, "fallbacks": {"classify": 0, "rank": 0},
              "metrics": m}
    assert "Error rate by label basis" in format_report(report)


def test_eval_uses_the_mentions_side_file(golden):
    labels, runs, _ = golden
    (runs / "run1.mentions.json").write_text(json.dumps(
        {"a": {"mentions": {"snyk": 1, "gitlab": 7}, "mentions_jfrog": True, "fetched": True}}), encoding="utf-8")
    llm = FakeLLM(_respond)
    report = run(split="all", live=True, labels_path=labels, runs_dir=runs, out_dir=None, llm=llm, cfg=CFG)
    assert report["full_page_mentions"] == 1
    assert '"full_text_mentions": "gitlab×7, snyk×1"' in llm.calls[0][0]
    assert {it["id"]: it["pred"]["mentions_jfrog"] for it in report["items"]}["a"] is True


def test_side_file_hash_is_in_the_eval_fingerprint(golden):
    labels, runs, _ = golden
    base = run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, cfg=CFG)
    (runs / "run1.mentions.json").write_text(json.dumps({"a": {"mentions": {"snyk": 1}}}), encoding="utf-8")
    one = run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, cfg=CFG)
    (runs / "run1.mentions.json").write_text(json.dumps({"a": {"mentions": {"snyk": 2}}}), encoding="utf-8")
    two = run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, cfg=CFG)
    assert len({base["fingerprint"], one["fingerprint"], two["fingerprint"]}) == 3
    assert set(two["mention_side_files"]) == {"run1"}


def test_default_split_is_train_and_test_needs_asking(golden, monkeypatch, capsys):
    import inspect

    labels, runs, out = golden
    assert inspect.signature(run).parameters["split"].default == "train"
    monkeypatch.setattr(eval_golden, "LABELS_PATH", labels)
    monkeypatch.setattr(eval_golden, "RUNS_DIR", runs)
    monkeypatch.setattr(eval_golden, "EVALS_OUT_DIR", out)
    monkeypatch.setattr(eval_golden.ci_config, "load", lambda: CFG)
    assert eval_golden.main([]) == 0
    assert "split=train" in capsys.readouterr().out
    assert not (out / "test_runs.log").exists()  # nothing peeked at test
    eval_golden.main(["--split", "test"])
    assert "split=test" in capsys.readouterr().out


def test_degraded_ranker_items_are_missing_not_a_midpoint_score():
    labels = [_label("a", "snyk", "Security", 3), _label("b", "snyk", "Security", 5)]
    cls = [_cls("a", "snyk", "Security"), _cls("b", "snyk", "Security")]
    ranked = [_ranked("a", 3), Ranked(id="b", raw_score=None, degraded=True, score=None, reason="", confidence=0.5,
                                       needs_review=True, review_reasons=["ranker unavailable: LLMError"])]
    m = evaluate(labels, cls, ranked)
    assert m["score"] == {"n": 1, "exact": 1.0, "within_1": 1.0, "missing": 1, "excluded_noise": 0,
                          "excluded_noise_n": 1}
    assert m["important"]["n"] == 1 and m["important"]["missing"] == 1  # the unscored item is left out


GOOD_TEXT = ("Sonatype launched Nexus Repository Pro+ with AI model screening on Tuesday, adding checks for "
             "poisoned models to its repository manager. ") * 6
JUNK_TEXT = "\n".join(["Menu", "Home", "Sign in", "We use cookies. Accept all", "Subscribe",
                       "© 2026 All rights reserved"] * 6)


def test_errors_by_bad_extraction_flag_and_detector_precision_recall():
    labels = [_label(i, "snyk", "Security", 4) for i in "abcde"]
    for row, flag in zip(labels, [True, True, False, False, None], strict=True):
        if flag is not None:
            row["bad_extraction"] = flag
    cls = [_cls(i, "gitlab" if i == "a" else "snyk", "Security") for i in "abcde"]
    m = evaluate(labels, cls, [_ranked(i, 4) for i in "abcde"])
    assert m["by_bad_extraction"]["true"]["n"] == 2 and m["by_bad_extraction"]["true"]["competitor"]["errors"] == 1
    assert m["by_bad_extraction"]["false"]["n"] == 2 and m["by_bad_extraction"]["false"]["competitor"]["errors"] == 0
    assert m["by_bad_extraction"]["unknown"]["n"] == 1

    title = "Sonatype launches Nexus Repository Pro+ AI model screening"
    items = [{"id": "a", "title": title, "text": JUNK_TEXT},   # flagged bad, detected: TP
             {"id": "b", "title": title, "text": GOOD_TEXT},   # flagged bad, not detected: FN
             {"id": "c", "title": title, "text": JUNK_TEXT},   # not flagged, detected: FP
             {"id": "d", "title": title, "text": GOOD_TEXT},   # TN
             {"id": "e", "title": title, "text": JUNK_TEXT}]   # no flag: not counted
    det = eval_golden.detector_vs_flags(labels, items)
    assert (det["tp"], det["fp"], det["fn"], det["tn"], det["n"]) == (1, 1, 1, 1, 4)
    assert det["precision"] == 0.5 and det["recall"] == 0.5
    assert {x["id"] for x in det["misses"]} == {"b", "c"}


def test_detector_runs_on_the_run_file_text_in_the_eval(golden):
    labels, runs, _ = golden
    rows = [json.loads(x) for x in labels.read_text(encoding="utf-8").splitlines() if x.startswith("{")]
    for row in rows:
        row["bad_extraction"] = row["id"] == "b"
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    report = run(split="all", live=True, labels_path=labels, runs_dir=runs, out_dir=None, llm=FakeLLM(_respond),
                 cfg=CFG)
    det = report["metrics"]["extraction_detector"]
    assert det["n"] == 3 and det["fn"] == 1  # 'b' is flagged by the labeler; its text looks like an article
    assert "Junk detector vs Bad extraction flags" in format_report(report)


def test_detector_thresholds_are_in_the_fingerprint(monkeypatch):
    from ci import extraction_quality

    base = eval_golden.fingerprint(CFG)
    monkeypatch.setattr(extraction_quality, "TITLE_MIN_COVERAGE", 0.5)
    assert eval_golden.fingerprint(CFG) != base


def test_every_rate_in_the_table_carries_its_n():
    import re

    labels = [_label("a", "snyk", "Security", 5), _label("b", "gitlab", "AI & Agents", 3),
              _label("c", "snyk", noise=True), _label("d", "industry", "Security", 4)]
    labels[0]["basis"] = "full"
    labels[1]["bad_extraction"] = True
    cls = [_cls("a", "snyk", "Security", method="rules"), _cls("b", "snyk", "AI & Agents"),
           _cls("c", "snyk", "Security", noise=True), _cls("d", "industry", "Product & Features", noise=True)]
    m = evaluate(labels, cls, [_ranked("a", 5), _ranked("b", 2), _ranked("c", 1), _ranked("d", 1)])
    report = {"split": "all", "live": True, "model": "m", "fingerprint": "f", "n": 4, "labels_total": 4,
              "stories": 4, "split_counts": {}, "aborted": False, "fallbacks": {"classify": 0, "rank": 0},
              "metrics": m}
    table = format_report(report)
    rates = re.findall(r"(?<![\w.])(?:\d\.\d\d|n/a)(?: \(n=\d+\))?", table)
    assert rates and all("(n=" in r for r in rates), [r for r in rates if "(n=" not in r]
    assert "0.67 (n=3)" in table  # competitor accuracy, non-noise
    assert "%" not in table
    for row in (m["by_basis"]["full"], m["by_bad_extraction"]["true"]):
        assert all("error_rate" in row[k] and "n" in row[k] for k in ("competitor", "category", "noise", "score"))


def test_metric_code_is_in_the_fingerprint(monkeypatch):
    base = eval_golden.fingerprint(CFG)
    real = eval_golden.inspect.getsource
    monkeypatch.setattr(eval_golden.inspect, "getsource",
                        lambda obj: real(obj) + "#" if obj is eval_golden.evaluate else real(obj))
    assert eval_golden.fingerprint(CFG) != base


def test_a_noise_label_predicted_important_is_a_false_positive():
    labels = [_label("a", "snyk", noise=True), _label("b", "snyk", "Security", 4)]
    cls = [_cls("a", "snyk", "Security"), _cls("b", "snyk", "Security")]
    m = evaluate(labels, cls, [_ranked("a", 4), _ranked("b", 4)])
    assert (m["important"]["tp"], m["important"]["fp"], m["important"]["fn"]) == (1, 1, 0)
    assert m["important"]["precision"] == 0.5 and m["important"]["precision_n"] == 2


def test_important_recall_line_shows_the_unscored_items():
    labels = [_label("a", "snyk", "Security", 5), _label("b", "snyk", "Security", 5)]
    ranked = [_ranked("a", 5), Ranked(id="b", raw_score=None, degraded=True, score=None, reason="", confidence=0.5)]
    m = evaluate(labels, [_cls("a", "snyk", "Security"), _cls("b", "snyk", "Security")], ranked)
    report = {"split": "all", "live": True, "model": "m", "fingerprint": "f", "n": 2, "labels_total": 2,
              "stories": 2, "split_counts": {}, "aborted": False, "fallbacks": {"classify": 0, "rank": 0},
              "metrics": m}
    line = next(x for x in format_report(report).splitlines() if "Important (score >= 4) recall" in x)
    assert "1.00 (n=1)" in line and "1 unscored (degraded) left out" in line


def test_test_split_log_carries_each_rate_with_its_n(tmp_path):
    labels = tmp_path / "golden.jsonl"
    rows = [_label(f"i{i}", "snyk", "Security", 4, title=f"Story {i}") for i in range(30)]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "out"
    run(split="test", live=True, labels_path=labels, runs_dir=tmp_path / "none", out_dir=out, cfg=CFG,
        llm=FakeLLM(_respond))
    entry = json.loads((out / "test_runs.log").read_text(encoding="utf-8").splitlines()[0])
    assert {"important_precision", "important_recall"} <= set(entry["metrics"])
    assert all(set(v) == {"value", "n"} for v in entry["metrics"].values())
    assert entry["metrics"]["important_recall"]["n"] >= 1


def test_pr_and_label_score_are_in_the_fingerprint(monkeypatch):
    base = eval_golden.fingerprint(CFG)
    real = eval_golden.inspect.getsource
    for fn in (eval_golden._pr, eval_golden.label_score):
        monkeypatch.setattr(eval_golden.inspect, "getsource", lambda obj, fn=fn: real(obj) + "#" if obj is fn
                            else real(obj))
        assert eval_golden.fingerprint(CFG) != base
        monkeypatch.undo()


def test_label_noise_predicted_noise_is_not_in_agreement_but_counts_in_noise_pr():
    labels = [_label("a", "snyk", noise=True), _label("b", "snyk", "Security", 3)]
    cls = [_cls("a", "snyk", "Security", noise=True), _cls("b", "snyk", "Security")]
    m = evaluate(labels, cls, [_ranked("a", 1), _ranked("b", 3)])
    assert (m["score"]["n"], m["score"]["excluded_noise"]) == (1, 1)
    assert (m["noise"]["tp"], m["noise"]["fp"], m["noise"]["fn"]) == (1, 0, 0)
    assert m["important"]["fp"] == 0  # noise is never important


def test_a_routine_1_predicted_noise_is_a_noise_false_positive_outside_agreement():
    labels = [_label("a", "gitlab", "Product & Features", 1), _label("b", "snyk", "Security", 3)]
    cls = [_cls("a", "gitlab", "Product & Features", noise=True), _cls("b", "snyk", "Security")]
    m = evaluate(labels, cls, [_ranked("a", 1), _ranked("b", 3)])
    assert (m["noise"]["fp"], m["noise"]["tp"]) == (1, 0)
    assert (m["score"]["n"], m["score"]["exact"], m["score"]["excluded_noise"]) == (1, 1.0, 1)
    table = format_report({"split": "all", "live": True, "model": "m", "fingerprint": "f", "n": 2,
                           "labels_total": 2, "stories": 2, "split_counts": {}, "aborted": False,
                           "fallbacks": {"classify": 0, "rank": 0}, "metrics": m})
    assert "excluded: one side noise" in table and "(n=2)" in table


def test_the_rubric_file_hash_is_in_the_fingerprint(monkeypatch, tmp_path):
    from ci import rank

    base = eval_golden.fingerprint(CFG)
    assert len(eval_golden.rubric_sha()) == 12
    other = tmp_path / "rubric.md"
    other.write_text(rank.RUBRIC_PATH.read_text(encoding="utf-8") + "\nedited", encoding="utf-8")
    monkeypatch.setattr(rank, "RUBRIC_PATH", other)
    assert eval_golden.fingerprint(CFG) != base
