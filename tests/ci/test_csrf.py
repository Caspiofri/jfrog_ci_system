"""The CSRF guard on the CI API and the labeling server: a cross-site write is refused before any route runs; the UI's
own same-origin calls, the dev proxy, and scripts without browser headers pass. Offline."""
import pytest
from fastapi.testclient import TestClient

from ci import csrf
from ci.labeling.app import create_app as create_labeling_app
from tests.ci.test_api import env  # noqa: F401  (the fixture)

LEVEL = "/api/v1/settings/autonomy-level"


@pytest.mark.parametrize("headers, refused", [
    ({}, False),                                                     # curl, scripts, tests
    ({"sec-fetch-site": "same-origin"}, False),                      # the UI calling its own /api/v1
    ({"sec-fetch-site": "none"}, False),                             # typed into the address bar
    ({"sec-fetch-site": "cross-site", "origin": "https://evil.example"}, True),
    ({"sec-fetch-site": "same-site", "origin": "http://localhost:9999"}, True),
    ({"origin": "http://localhost:3011", "host": "127.0.0.1:8011"}, False),  # dev proxy, no Sec-Fetch-Site
    ({"origin": "http://pi:8000", "host": "pi:8000"}, False),                # same host as the request
    ({"origin": "https://evil.example", "host": "127.0.0.1:8011"}, True),
    ({"origin": "null"}, True),                                      # sandboxed iframe or file:// page
])
def test_refusal_rules(headers, refused):
    assert (csrf.refusal("POST", headers) is not None) is refused
    assert csrf.refusal("GET", headers) is None  # reads are never blocked


def test_extra_origins_come_from_the_env():
    extra = csrf.allowed_origins({"CI_ALLOWED_ORIGINS": "http://pi:3011/, http://100.1.2.3:3011"})
    assert extra == {"http://pi:3011", "http://100.1.2.3:3011"}
    assert csrf.refusal("PUT", {"sec-fetch-site": "cross-site", "origin": "http://pi:3011"}, extra) is None


def test_the_api_refuses_a_cross_site_write_and_changes_nothing(env):  # noqa: F811
    c, _, _ = env
    evil = {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"}
    r = c.put(LEVEL, json={"level": "relaxed"}, headers=evil)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_refused"
    assert c.get("/api/v1/meta").json()["level"] == "strict"
    assert c.put(LEVEL, json={"level": "relaxed"}, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_the_labeling_server_refuses_a_cross_site_label(tmp_path):
    labels = tmp_path / "labels.jsonl"
    c = TestClient(create_labeling_app(runs_dir=tmp_path / "runs", labels_path=labels, competitors=[]))
    r = c.post("/api/labels", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not labels.exists()
