"""Writable demo (D111): each start copies the snapshot stores to a new temporary folder, a guard proves the startup
changed 0 rows there, every action writes only there, Health and evaluation numbers read the untouched snapshot, and
Refresh insights is refused with no LLM call. Offline; the real committed snapshot (demo/snapshot) where it matters."""
import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ci import demo
from ci.api import __main__ as api_main
from ci.api.app import create_app
from ci.classify import CATEGORIES
from ci.store import STORE_PATH
from config.settings import DATA_DIR, EVALS_DIR, ROOT
from tests.ci.test_api import CFG, build

SNAPSHOT = ROOT / "demo" / "snapshot"
FROZEN_READS = ("/api/v1/health", "/api/v1/run-metrics", "/api/v1/runs", "/api/v1/evals/test")


def tree_sha(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def frozen(c: TestClient) -> dict:
    out = {}
    for path in FROZEN_READS:
        r = c.get(path)
        assert r.status_code == 200, path
        out[path] = r.json()
    return out


def do_actions(c: TestClient) -> dict:
    """Approve, Flag, Unflag, Dismiss, Reopen, Edit, the autonomy control, Trust this source and a changed cell,
    on the real snapshot; returns {action: status code}."""
    review = c.get("/api/v1/review", params={"limit": 200}).json()["items"]
    held = [r["item"]["item_id"] for r in review if r["kind"] == "item"]
    published = [i["item_id"] for i in c.get("/api/v1/brief", params={"limit": 200}).json()["items"]["items"]]
    assert len(held) >= 2 and published, "the snapshot needs held and published items"
    a, b, p = held[0], held[1], published[0]
    cat = next(x for x in CATEGORIES if x != c.get(f"/api/v1/items/{p}").json()["item"]["category"])
    level = c.get("/api/v1/settings/autonomy-level").json()["level"]
    codes = {
        "approve": c.post(f"/api/v1/items/{a}/approve", json={"note": "demo"}).status_code,
        "flag": c.post(f"/api/v1/items/{p}/flag", json={}).status_code,
        "unflag": c.delete(f"/api/v1/items/{p}/flag").status_code,
        "flag_again": c.post(f"/api/v1/items/{p}/flag", json={}).status_code,
        "dismiss": c.post(f"/api/v1/items/{b}/dismiss", json={"reason": "not_relevant"}).status_code,
        "reopen": c.post(f"/api/v1/items/{b}/reopen", json={}).status_code,
        "dismiss_again": c.post(f"/api/v1/items/{b}/dismiss", json={"reason": "duplicate"}).status_code,
        "edit": c.patch(f"/api/v1/items/{p}", json={"category": cat, "note": "demo"}).status_code,
        "level": c.put("/api/v1/settings/autonomy-level",
                       json={"level": "strict" if level != "strict" else "relaxed"}).status_code,
        "trust": c.post("/api/v1/sources/trust", json={"host": "demo-example.org"}).status_code,
        "untrust": c.delete("/api/v1/sources/trust/demo-example.org").status_code,
    }
    changes = [r for r in review if r["kind"] == "change"]
    if changes:
        codes["change_approve"] = c.post(f"/api/v1/changes/{changes[0]['change_id']}/approve", json={}).status_code
    return codes


@pytest.fixture
def tmp_root(tmp_path):
    d = tmp_path / "tmp"
    d.mkdir()
    return d


def test_the_guard_passes_on_the_real_snapshot_and_actions_write_only_the_copy(tmp_root, monkeypatch):
    before_snapshot = tree_sha(SNAPSHOT)
    before_evals = tree_sha(EVALS_DIR)
    opened: list[str] = []
    real_connect = sqlite3.connect

    def spy(target, *a, **k):
        opened.append(str(target))
        return real_connect(target, *a, **k)

    monkeypatch.setattr(sqlite3, "connect", spy)
    m = demo.prepare(SNAPSHOT, read_only=False, tmp_root=tmp_root)
    assert m["writable"] and m["guard"]["ok"] and m["guard"]["changed"] == []
    assert m["guard"]["tables"] > 0 and m["guard"]["rows"] > 0
    copy_dir = m["copy_dir"]
    assert copy_dir.parent == tmp_root and m["store_path"].parent == copy_dir

    c = TestClient(create_app(demo=m))
    meta = c.get("/api/v1/meta").json()
    assert meta["demo_writable"] is True and meta["meta"]["mode"] == "demo" and meta["meta"]["snapshot"]["date"]
    frozen_before = frozen(c)
    codes = do_actions(c)
    assert all(v == 200 for v in codes.values()), codes
    assert c.post("/api/v1/items/x/approve").json()["meta"]["mode"] == "demo"  # every meta block says demo
    assert frozen(c) == frozen_before  # Health, evaluation and run numbers do not move
    log = c.get("/api/v1/log", params={"limit": 200}).json()
    assert any(r["flagged"] for r in log["items"])  # the actions are visible where they belong

    assert tree_sha(SNAPSHOT) == before_snapshot  # byte-identical
    assert tree_sha(EVALS_DIR) == before_evals  # Edit's candidate label went to the copy, not evals/
    assert (copy_dir / demo.LABELS_FILE).read_text().strip()
    live = {str(STORE_PATH), str(DATA_DIR / "ci" / "changes.sqlite")}
    assert not live & {t.split("?")[0].removeprefix("file:") for t in opened}  # the live store is never opened
    for t in opened:  # every connection that may write is on the copy; the snapshot only ever immutable
        path = t.split("?")[0].removeprefix("file:")
        assert path.startswith(str(copy_dir)) or "mode=ro" in t, t


def test_a_restart_resets_every_action(tmp_root):
    m1 = demo.prepare(SNAPSHOT, read_only=False, tmp_root=tmp_root)
    c1 = TestClient(create_app(demo=m1))
    pristine = {p: c1.get(p, params={"limit": 200}).json() for p in ("/api/v1/review", "/api/v1/log",
                                                                     "/api/v1/brief", "/api/v1/sources")}
    assert all(v == 200 for v in do_actions(c1).values())
    assert c1.get("/api/v1/review", params={"limit": 200}).json() != pristine["/api/v1/review"]
    m2 = demo.prepare(SNAPSHOT, read_only=False, tmp_root=tmp_root)  # the next start
    assert m2["copy_dir"] != m1["copy_dir"] and not m1["copy_dir"].exists()  # an old copy is never reused
    c2 = TestClient(create_app(demo=m2))
    for p, body in pristine.items():
        assert c2.get(p, params={"limit": 200}).json() == body, p


def test_refresh_insights_is_refused_with_no_llm_call_even_with_a_key(tmp_root, monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "a-key-that-must-not-be-used")
    monkeypatch.delenv(demo.READ_ONLY_ENV, raising=False)
    monkeypatch.setattr("tempfile.tempdir", str(tmp_root))

    def no_llm(*a, **k):
        raise AssertionError("no LLM in the demo")

    monkeypatch.setattr("ci.llm.GeminiLLM.__init__", no_llm)
    monkeypatch.setattr("ci.insights.generate", no_llm)
    c = TestClient(api_main.build_app(SNAPSHOT))  # the container's own path: python -m ci.api --demo
    date = c.get("/api/v1/meta").json()["latest_brief_date"]
    assert c.get("/api/v1/meta").json()["demo_writable"] is True
    r = c.post(f"/api/v1/brief/{date}/insights/refresh")
    assert r.status_code == 403 and r.json()["error"]["code"] == "insights_frozen_demo"
    assert "frozen in this demo" in r.json()["error"]["message"]
    ro = TestClient(create_app(demo=demo.prepare(SNAPSHOT, read_only=True)))  # read-only demo: the same code
    assert ro.post(f"/api/v1/brief/{date}/insights/refresh").json()["error"]["code"] == "insights_frozen_demo"


def test_a_write_off_the_allowlist_is_refused_in_the_writable_demo(tmp_root):
    c = TestClient(create_app(demo=demo.prepare(SNAPSHOT, read_only=False, tmp_root=tmp_root)))
    for method, path in (("POST", "/api/v1/anything"), ("DELETE", "/api/v1/items/x"), ("PUT", "/api/v1/meta"),
                         ("POST", "/api/v1/settings/autonomy-level")):
        r = c.request(method, path, json={})
        assert r.status_code == 403 and r.json()["error"]["code"] == "demo_read_only", (method, path)


@pytest.fixture
def small_snapshot(tmp_path):
    store_path, _, _ = build(tmp_path)
    out = tmp_path / "demo"
    demo.build(out, store_path, tmp_path / "no-changes.sqlite", label="test")
    return out


def test_the_guard_fails_and_the_demo_falls_back_to_read_only_when_startup_would_change_a_row(small_snapshot,
                                                                                          tmp_root):
    db = sqlite3.connect(small_snapshot / demo.STORE_FILE)  # a row _repair_future_published() would fix
    db.execute("UPDATE items SET published_at = '2099-01-01T00:00:00+00:00' WHERE item_id = 'pub1'")
    db.commit()
    db.close()
    before = tree_sha(small_snapshot)
    m = demo.prepare(small_snapshot, read_only=False, tmp_root=tmp_root)
    assert not m["writable"] and m["read_only_reason"] == "guard_failed"
    assert m["guard"]["changed"] == ["ci.sqlite:items"]
    assert list(tmp_root.iterdir()) == []  # the failed copy is removed
    c = TestClient(create_app(cfg=CFG, demo=m))
    meta = c.get("/api/v1/meta").json()
    assert meta["demo_writable"] is False and meta["meta"]["mode"] == "demo"
    r = c.post("/api/v1/items/pub1/approve", json={})
    assert r.status_code == 403 and r.json()["error"]["code"] == "demo_read_only"
    assert tree_sha(small_snapshot) == before


def test_the_demo_falls_back_to_read_only_when_the_copy_fails(small_snapshot, tmp_path):
    m = demo.prepare(small_snapshot, read_only=False, tmp_root=tmp_path / "missing")
    assert not m["writable"] and m["read_only_reason"].startswith("copy_failed")
    assert m["store_path"] == small_snapshot / demo.STORE_FILE  # served immutable, as before D111
    assert TestClient(create_app(cfg=CFG, demo=m)).get("/api/v1/meta").json()["demo_writable"] is False


def test_read_only_stays_available_as_a_setting(small_snapshot, tmp_root, monkeypatch):
    monkeypatch.setenv(demo.READ_ONLY_ENV, "1")
    m = demo.prepare(small_snapshot, tmp_root=tmp_root)
    assert not m["writable"] and m["read_only_reason"] == "setting" and list(tmp_root.iterdir()) == []
    monkeypatch.setenv(demo.READ_ONLY_ENV, "0")
    assert demo.prepare(small_snapshot, tmp_root=tmp_root)["writable"]


def test_the_guard_digest_sees_any_changed_row(small_snapshot):
    a = demo.table_digest(small_snapshot / demo.STORE_FILE)
    db = sqlite3.connect(small_snapshot / demo.STORE_FILE)
    db.execute("UPDATE items SET title = 'x' WHERE item_id = 'pub1'")
    db.commit()
    db.close()
    b = demo.table_digest(small_snapshot / demo.STORE_FILE)
    assert demo.changed_tables(a, b) == ["items"]
    assert demo.changed_tables(a, a | {"new_empty": {"rows": 0, "sha256": ""}}) == []
    assert demo.changed_tables(a, a | {"new_full": {"rows": 1, "sha256": "x"}}) == ["new_full"]


def test_live_mode_says_not_writable(tmp_path):
    store_path, runs_dir, split = build(tmp_path)
    c = TestClient(create_app(store_path=store_path, runs_dir=runs_dir, split_path=split, cfg=CFG,
                              labels_out=tmp_path / "labels.jsonl", changes_path=tmp_path / "none.sqlite"))
    meta = c.get("/api/v1/meta").json()
    assert meta["demo_writable"] is False and meta["meta"]["mode"] == "live" and "snapshot" not in meta["meta"]


def test_a_changed_cell_decided_in_the_demo_writes_only_the_copy(tmp_path, tmp_root):
    from ci.changes.diff import CellStore
    from tests.ci.test_changes_review import T0, T1, cell, change

    store_path, _, _ = build(tmp_path)
    cs = CellStore(tmp_path / "changes.sqlite")
    old, new = cell("Team $25/month", "Team $25", T0), cell("Team $30/month", "Team $30", T1)
    cs.put(old, "r1", "baseline")
    cs.put(new, "r2", "changed", change(old, new))
    cs._db.execute("CREATE TABLE snapshots (path TEXT)")  # the page-snapshot table a real changes store has
    cs._db.commit()
    cs.close()
    out = tmp_path / "demo"
    demo.build(out, store_path, tmp_path / "changes.sqlite", label="test")
    before = tree_sha(out)
    m = demo.prepare(out, read_only=False, tmp_root=tmp_root)
    assert m["writable"]
    c = TestClient(create_app(cfg=CFG, demo=m))
    assert c.post("/api/v1/changes/chg1/approve", json={}).status_code == 200
    assert c.post("/api/v1/changes/chg1/approve", json={}).status_code == 409  # decided, on the copy
    assert tree_sha(out) == before
    assert CellStore(m["changes_path"]).change("chg1")[1]["status"] == "approved"
