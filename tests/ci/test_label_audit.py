"""Label audit: each issue code, the stricter relabel-queue saves and their stamp, the API counts, the CLI, the eval."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ci import eval_golden
from ci.labeling import audit, relabel
from ci.labeling.app import create_app

BUILT = "2026-10-30T15:30:00+00:00"
BEFORE, AFTER = "2026-10-30T10:00:00+00:00", "2026-10-30T16:00:00+00:00"
COMPETITORS = ["snyk", "github", "industry"]


def _complete(**kw) -> dict:
    return {"id": "x", "run_id": "r1", "competitor": "snyk", "category": "Security", "score": 3, "noise": False,
            "mentions_jfrog": False, "basis": "full", "bad_extraction": False, "bad_extraction_explicit": True,
            "note": "why", "standard": "rubric-v2", "labeled_at": AFTER, **kw}


def test_a_complete_label_has_no_issues():
    assert audit.issues(_complete(), BUILT) == []


@pytest.mark.parametrize("change, code", [
    ({"standard": None}, "not_reviewed_v2"),
    ({"bad_extraction": None}, "bad_extraction_unanswered"),
    ({"bad_extraction_explicit": None}, "bad_extraction_unanswered"),  # an old False may be the page default
    ({"basis": None}, "no_basis"),
    ({"note": "  "}, "no_note"),
    ({"score": 1, "labeled_at": BEFORE}, "score1_pre_v2"),
    ({"noise": True, "score": 2}, "noise_fields"),
    ({"score": None}, "missing_score_or_category"),
    ({"category": None}, "missing_score_or_category"),
])
def test_each_issue_code(change, code):
    assert code in audit.issues(_complete(**change), BUILT)


def test_score1_after_v2_or_noise_is_fine_and_topup_answers_count():
    assert audit.issues(_complete(score=1), BUILT) == []  # saved after the queue: v2's routine 1
    assert audit.issues(_complete(noise=True, category=None, score=None), BUILT) == []
    old_false = _complete(bad_extraction_explicit=None)
    assert "bad_extraction_unanswered" not in audit.issues(old_false, BUILT, topup_required=True)


# ---- the API ------------------------------------------------------------------------------------------------


def _packet(i, title):
    return {"id": i, "run_id": "r1", "source": "google_news", "origin": "q", "competitor": "snyk", "title": title,
            "url": f"https://a.com/{i}", "original_url": f"https://a.com/{i}", "url_resolved": True,
            "published_at": BEFORE, "text": "body " * 50, "text_status": "full", "publisher": "A", "in_24h": True}


def _old_label(i, title, **kw):  # a label from before the current standard
    return {"id": i, "run_id": "r1", "competitor": "snyk", "category": "Security", "score": 3, "noise": False,
            "mentions_jfrog": False, "note": "", "bad_extraction": False, "labeled_at": BEFORE,
            "item": {"title": title}, **kw}


@pytest.fixture
def env(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    titles = {"a": "Old score one", "b": "Old noise", "c": "Outside the queue"}
    (runs / "r1.jsonl").write_text("".join(json.dumps(_packet(i, t)) + "\n" for i, t in titles.items()),
                                   encoding="utf-8")
    labels = tmp_path / "golden_set.jsonl"
    rows = [_old_label("a", titles["a"], score=1), _old_label("b", titles["b"], noise=True, score=None,
                                                             category=None),
            _old_label("c", titles["c"], labeled_at=AFTER)]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    out = tmp_path / "relabel"
    relabel.write(relabel.build(labels, runs, "2026-10-30T15:30:00Z", [], [], "", "v2"), out)
    client = TestClient(create_app(runs_dir=runs, labels_path=labels, competitors=COMPETITORS, relabel_dir=out,
                                   changes_db=tmp_path / "none.sqlite"))
    return client, labels, runs, out


def _body(i, **kw):
    return {"id": i, "run_id": "r1", "competitor": "snyk", "category": "Security", "score": 1, "noise": False,
            "mentions_jfrog": False, "basis": "full", "bad_extraction": False, "note": "routine patch", **kw}


def test_cards_carry_issues_and_the_api_counts_them(env):
    client, *_ = env
    data = client.get("/api/relabel/v2").json()
    cards = {c["id"]: c for c in data["items"]}
    assert cards["a"]["issues"] == ["not_reviewed_v2", "bad_extraction_unanswered", "no_basis", "no_note",
                                    "score1_pre_v2"]
    assert data["audit"]["needs_attention"] == 2 and data["audit"]["per_issue"]["score1_pre_v2"] == 1
    items = {i["id"]: i for i in client.get("/api/runs/r1/items").json()}
    assert "no_note" in items["c"]["issues"]  # badges show on normal runs too
    totals = client.get("/api/audit").json()
    assert totals["total"] == 3 and totals["complete"] == 0 and totals["per_issue"]["not_reviewed_v2"] == 3
    assert client.get("/api/audit", params={"relabel_queue": "v2"}).json()["total"] == 2
    assert client.get("/api/meta").json()["issue_names"]["score1_pre_v2"] == "score 1 from before v2"


@pytest.mark.parametrize("missing", [{"basis": None}, {"bad_extraction": None}, {"note": "  "}])
def test_relabel_queue_requires_basis_bad_extraction_and_note(env, missing):
    client, labels, *_ = env
    before = labels.read_text()
    assert client.post("/api/labels", json=_body("a", **missing)).status_code == 422
    assert labels.read_text() == before


def test_relabel_save_stamps_and_clears_the_issues(env):
    client, labels, *_ = env
    r = client.post("/api/labels", json=_body("a"))  # a confirmation: answering unset fields is no change
    assert r.status_code == 200 and r.json()["relabel"]["changed"] == []
    row = next(json.loads(line) for line in labels.read_text().splitlines() if json.loads(line)["id"] == "a")
    assert row["standard"] == "rubric-v2" and row["bad_extraction_explicit"] is True
    assert row["reviewed_at"] == row["labeled_at"]
    assert r.json()["issues"] == []
    assert client.get("/api/relabel/v2").json()["audit"]["needs_attention"] == 1


def test_a_change_still_needs_a_reason(env):
    client, *_ = env
    assert client.post("/api/labels", json=_body("a", score=3)).status_code == 422
    assert client.post("/api/labels", json=_body("a", score=3, revision_reason="v2")).status_code == 200


def test_outside_the_queue_nothing_is_stricter_or_stamped(env):
    client, *_ = env
    r = client.post("/api/labels", json=_body("c", note="", bad_extraction=None))
    assert r.status_code == 200
    assert "standard" not in r.json() and "bad_extraction_explicit" not in r.json()
    assert "not_reviewed_v2" in r.json()["issues"]


# ---- the page --------------------------------------------------------------------------------------------------

PAGE = Path(__file__).parents[2] / "ci" / "labeling" / "page.html"
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("issues, stored, expected", [
    (["bad_extraction_unanswered"], False, None),  # not explicit: the toggle starts unset
    ([], True, True),  # explicit: keep the answer
])
def test_relabel_toggle_starts_unset_without_an_explicit_answer(issues, stored, expected):
    src = PAGE.read_text(encoding="utf-8")
    funcs = [re.search(rf"^function {name}\(.*?^}}", src, re.S | re.M).group(0)
             for name in ("requiresBad", "draftFrom")]
    item = {"id": "a", "competitor": "snyk", "issues": issues,
            "label": {"competitor": "snyk", "category": "Security", "score": 3, "noise": False, "basis": "full",
                      "bad_extraction": stored, "note": ""}}
    script = ("let QUEUE = null, inQueue = new Map(); const relabeling = () => true;"
              "const issuesOf = (item) => item.issues || [];\n" + "\n".join(funcs)
              + f"\nprocess.stdout.write(JSON.stringify(draftFrom({json.dumps(item)}).bad_extraction));")
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    assert json.loads(out.stdout) == expected


# ---- CLI and eval ------------------------------------------------------------------------------------------------


def test_cli_prints_the_table(env, capsys):
    _, labels, runs, out = env
    audit.main(["--labels", str(labels), "--runs-dir", str(runs), "--relabel-dir", str(out)])
    text = capsys.readouterr().out
    assert re.search(r"not_reviewed_v2\s+3", text) and re.search(r"score1_pre_v2\s+1", text)
    assert "complete under current standard: 0 of 3" in text


def test_eval_warns_and_records_the_audit(env, capsys):
    _, labels, runs, out = env
    report = eval_golden.run(split="all", labels_path=labels, runs_dir=runs, out_dir=None, relabel_dir=out,
                             embed_fn=lambda: (lambda texts: [[1.0, 0.0]] * len(texts)), embed_cache=None,
                             split_path=None)
    assert report["label_audit"]["needs_attention"] == 3
    assert "WARNING: 3 of 3 labels not complete under rubric v2: not_reviewed_v2 3" in capsys.readouterr().err
