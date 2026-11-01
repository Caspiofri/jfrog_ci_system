"""Demo mode (D34, D59): a snapshot of the real store built with the field allowlist, served read-only by the same
API with no model, no writes and a visible demo marker. Offline."""
import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from ci import demo
from ci.api import service as svc
from ci.api.app import create_app
from tests.ci.test_api import CFG, LONG, build


@pytest.fixture
def snap(tmp_path):
    store_path, runs_dir, _ = build(tmp_path)
    out = tmp_path / "demo"
    manifest = demo.build(out, store_path, tmp_path / "no-changes.sqlite", label="test")
    return out, manifest, store_path


def test_the_snapshot_keeps_only_the_allowlist_and_the_excerpt(snap):
    out, manifest, store_path = snap
    live = {i: json.loads(r) for i, r in sqlite3.connect(store_path).execute("SELECT item_id, raw FROM items")}
    db = sqlite3.connect(out / demo.STORE_FILE)
    rows = {i: json.loads(r) for i, r in db.execute("SELECT item_id, raw FROM items")}
    assert set(rows) == set(live) and manifest["items"] == len(live)
    pub = rows["pub1"]
    assert LONG not in json.dumps(rows) and len(pub["text"]) <= svc.EXCERPT_CHARS  # no article text
    assert pub["text"] == svc.excerpt(live["pub1"]) and pub["title"] == live["pub1"]["title"]
    assert pub["chars_used_for_scoring"] == svc.text_basis(live["pub1"])["chars_used_for_scoring"]
    assert set(pub) <= {*demo.ALLOWED_RAW, "text", "teaser", "chars_used_for_scoring"}
    assert manifest["date"] and manifest["commit"] and manifest["runs"]
    with pytest.raises(FileExistsError):  # a frozen snapshot is never rebuilt in place
        demo.build(out, store_path)


def test_the_demo_api_serves_the_snapshot_read_only_with_a_marker(snap):
    out, manifest, _ = snap
    for p in out.iterdir():
        os.chmod(p, 0o444)
    os.chmod(out, 0o555)  # as on a read-only mount: no journal or lock file can be created
    try:
        c = TestClient(create_app(cfg=CFG, demo=demo.load(out)))
        meta = c.get("/api/v1/meta").json()["meta"]
        assert meta["mode"] == "demo" and meta["snapshot"]["date"] == manifest["date"]
        assert meta["now"] == svc.iso(svc.parse_ts(manifest["as_of"]))  # the clock stands at the snapshot
        b = c.get("/api/v1/brief").json()
        assert b["status"] == "ok" and b["items"]["total"] >= 1 and b["meta"]["mode"] == "demo"
        for path in ("/api/v1/review", "/api/v1/briefs", "/api/v1/health", "/api/v1/competitors", "/api/v1/runs"):
            r = c.get(path)
            assert r.status_code == 200 and r.json()["meta"]["snapshot"]["date"] == manifest["date"], path
        assert c.get("/api/v1/items/nope").json()["meta"]["snapshot"]["date"] == manifest["date"]  # route errors too
        item = c.get("/api/v1/items/pub1").json()["item"]
        assert len(item["excerpt"]) <= svc.EXCERPT_CHARS
        for method, path in (("post", "/api/v1/items/pub1/approve"), ("put", "/api/v1/settings/autonomy-level"),
                             ("post", f"/api/v1/brief/{manifest['date']}/insights/refresh"),
                             ("post", "/api/v1/sources/trust"), ("delete", "/api/v1/items/pub1/flag")):
            r = c.request(method.upper(), path, json={})
            assert r.status_code == 403 and r.json()["error"]["code"] == "demo_read_only", path
    finally:
        os.chmod(out, 0o755)
    assert sorted(p.name for p in out.iterdir()) == [demo.STORE_FILE, demo.MANIFEST_FILE]  # nothing was written


def test_check_refuses_a_snapshot_with_article_text(snap):
    out, _, _ = snap
    db = sqlite3.connect(out / demo.STORE_FILE)
    db.execute("UPDATE items SET raw = ? WHERE item_id = 'pub1'", (json.dumps({"id": "pub1", "text": LONG}),))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="longer than the excerpt"):
        demo.check(out)
