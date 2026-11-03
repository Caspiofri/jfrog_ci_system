"""D74: run-metrics rows rebuilt from the item log, and the run vs after-actions counts in the API."""
import json
import sqlite3

import pytest

from ci import metrics_backfill as mb
from ci import run_metrics
from ci.store import Store
from tests.ci.test_api import RUN1, RUN2, build
from tests.ci.test_run_metrics import api  # noqa: F401


@pytest.fixture
def store(tmp_path):
    store_path, runs_dir, _ = build(tmp_path)
    return store_path, runs_dir


def set_report(path, run_id, report):
    with sqlite3.connect(path) as db:
        db.execute("UPDATE runs SET report = ? WHERE run_id = ?", (json.dumps(report), run_id))


def dump(path, skip=("run_metrics",)):
    db = sqlite3.connect(path)
    tables = [t for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'") if t not in skip]
    out = {t: sorted(map(repr, db.execute(f"SELECT * FROM {t}"))) for t in tables}
    db.close()
    return out


def test_counts_come_from_the_item_log_and_routing_is_left_empty(store):
    path, runs_dir = store
    m = mb.reconstruct(sqlite3.connect(path), RUN1, runs_dir)
    # RUN1 holds 7 items: 6 classified (1 noise) and 1 in the test split, never sent to the model
    assert m["items"] == {"collected": None, "kept": 7, "new": 7, "test_skip": 1, "to_model": 6, "noise": 1,
                          "non_noise": 5, "published": None, "held": None, "routed_n": None, "by_status": None,
                          "recovered": None}
    r = m["reconstructed"]
    assert r["decision"] == "D74" and r["label"] == "Reconstructed from the item log"
    assert set(r["sources"].values()) == {"item_log"} and "items.collected" in r["empty"]
    assert r["empty"]["items.published"].startswith("no routing ran")
    assert m["lens"] is None and m["steps"] == [] and m["llm_calls"] is None


def test_the_fetched_count_comes_from_the_runs_own_report_and_says_so(store):
    path, runs_dir = store
    set_report(path, RUN1, {"funnel": {"totals": {"collected": 307, "kept": 282}}})
    m = mb.reconstruct(sqlite3.connect(path), RUN1, runs_dir)
    assert m["items"]["collected"] == 307 and m["items"]["kept"] == 7  # kept is the item log's, not the report's
    assert m["reconstructed"]["sources"]["items.collected"] == "run_report"
    assert "items.collected" not in m["reconstructed"]["empty"]


def test_a_second_run_on_the_same_date_is_listed_not_chosen(store):
    path, runs_dir = store
    (runs_dir / "20261030T0836Z-cccccc.report.json").write_text("{}")
    with pytest.raises(mb.Refused, match=r"20261030T0836Z-cccccc.*20261030T1312Z-aaaaaa"):
        mb.reconstruct(sqlite3.connect(path), RUN1, runs_dir)


def test_the_override_must_name_exactly_the_other_runs_and_is_recorded(store):
    path, runs_dir = store
    (runs_dir / "20261030T0836Z-cccccc.report.json").write_text("{}")
    db = sqlite3.connect(path)
    m = mb.reconstruct(db, RUN1, runs_dir, not_this_run={"20261030T0836Z-cccccc": "never imported"})
    assert m["reconstructed"]["other_runs_same_date"] == [{"run_id": "20261030T0836Z-cccccc", "note": "never imported"}]
    with pytest.raises(mb.Refused, match="not on that date"):
        mb.reconstruct(db, RUN1, runs_dir, not_this_run={"20261030T0836Z-cccccc": "x", "20261029T0400Z-dddddd": "x"})
    assert mb.reconstruct(sqlite3.connect(path), RUN2, runs_dir)["reconstructed"]["other_runs_same_date"] == []


def test_the_cli_writes_under_the_collect_lock(store, tmp_path):
    from ci.runlock import run_lock
    path, runs_dir = store
    lock_dir = tmp_path / "locks"
    args = ["--store", str(path), "--run", RUN1, "--runs-dir", str(runs_dir), "--lock-dir", str(lock_dir), "--write"]
    with run_lock("collect", lock_dir):
        assert mb.main(args) == 1  # a daily run holds the lock: nothing written
    with Store(path, read_only=True) as s:
        assert s.run_metrics(RUN1) == []
    assert mb.main(args) == 0


def test_an_existing_row_is_never_overwritten_and_unknown_runs_are_refused(store):
    path, runs_dir = store
    with Store(path) as s:
        s.save_run_metrics(run_metrics.build(run_id=RUN2, kind="daily", status="ok", started_at="x",
                                             fingerprints={}, model="m", llm_calls=1, steps=run_metrics.Steps()))
    with pytest.raises(mb.Refused, match="already has a metrics row"):
        mb.reconstruct(sqlite3.connect(path), RUN2, runs_dir)
    with pytest.raises(mb.Refused, match="not in the store"):
        mb.reconstruct(sqlite3.connect(path), "nope", runs_dir)


def test_the_write_adds_one_row_and_touches_no_other_table(store):
    path, runs_dir = store
    before = dump(path)
    db = sqlite3.connect(path)
    m = mb.reconstruct(db, RUN1, runs_dir)
    mb.write(db, m)
    with pytest.raises(sqlite3.IntegrityError):
        mb.write(db, m)  # an INSERT, never a replace
    db.close()
    assert dump(path) == before
    with Store(path, read_only=True) as s:
        assert s.run_metrics(RUN1)[0]["reconstructed"]["decision"] == "D74"


def test_cli_prints_without_writing_unless_asked(store, capsys):
    path, runs_dir = store
    assert mb.main(["--store", str(path), "--run", RUN1, "--runs-dir", str(runs_dir)]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == RUN1
    with Store(path, read_only=True) as s:
        assert s.run_metrics(RUN1) == []
    assert mb.main(["--store", str(path), "--run", RUN1, "--runs-dir", str(runs_dir), "--lock-dir",
                    str(path.parent / "locks"), "--write"]) == 0
    assert mb.main(["--store", str(path), "--run", RUN1, "--runs-dir", str(runs_dir)]) == 1  # now refused


def test_new_rows_carry_reconstructed_null():
    m = run_metrics.build(run_id="r", kind="daily", status="ok", started_at="x", fingerprints={}, model="m",
                          llm_calls=0, steps=run_metrics.Steps())
    assert m["reconstructed"] is None


def test_api_keeps_run_values_and_after_actions_values_apart(api, tmp_path):  # noqa: F811
    c, _ = api
    path = tmp_path / "ci.sqlite"
    # a row written before the field existed has no "reconstructed" key: it is served as null
    with sqlite3.connect(path) as db:
        db.execute("UPDATE run_metrics SET metrics = json_remove(metrics, '$.reconstructed')")
    old = c.get(f"/api/v1/run-metrics/{RUN2}").json()
    assert old["reconstructed"] is None and old["items_after_actions"] is None  # no published count in that row
    # a run-written row for RUN1 with its end-of-run counts, then an analyst approval of a held item
    with Store(path) as s:
        s.save_run_metrics(run_metrics.build(
            run_id=RUN1, kind="import", status="ok", started_at=s.run(RUN1)["started_at"], fingerprints={},
            model="m", llm_calls=0, steps=run_metrics.Steps(),
            items={"published": 2, "held": 3, "by_status": {"auto_published": 2, "awaiting_review": 3, "dropped": 1}}))
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO item_state (item_id, decision, flagged, version, updated_at)"
                   " VALUES ('uv', 'approved', 0, 1, '2026-10-31T08:00:00+00:00')")
    row = c.get(f"/api/v1/run-metrics/{RUN1}").json()
    assert (row["items"]["published"], row["items"]["held"]) == (2, 3)  # the run's own values, untouched
    after = row["items_after_actions"]
    assert (after["published"], after["held"], after["n"]) == (3, 2, 6) and after["by_status"]["approved"] == 1
    assert c.get("/api/v1/health", params={"run_id": RUN1}).json()["run_metrics"]["items_after_actions"] == after


def test_api_serves_a_reconstructed_row_with_no_after_actions_numbers(api, tmp_path):  # noqa: F811
    c, _ = api
    path = tmp_path / "ci.sqlite"
    db = sqlite3.connect(path)
    mb.write(db, mb.reconstruct(db, RUN1, tmp_path / "runs"))
    db.close()
    row = c.get(f"/api/v1/run-metrics/{RUN1}").json()
    assert row["reconstructed"]["label"] == "Reconstructed from the item log"
    assert row["items"]["published"] is None and row["items_after_actions"] is None
