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


# ---- Host allowlist (DNS rebinding, D59) ------------------------------------------------------------------------

@pytest.mark.parametrize("header, name", [("127.0.0.1:8011", "127.0.0.1"), ("localhost", "localhost"),
                                          ("[::1]:8011", "::1"), ("Evil.Example:8011", "evil.example")])
def test_host_of(header, name):
    assert csrf.host_of(header) == name


def test_trusted_hosts_are_loopback_plus_what_the_server_listens_on_plus_the_env():
    assert csrf.trusted_hosts(env={}) == {"localhost", "127.0.0.1", "::1"}
    assert csrf.trusted_hosts(["100.1.2.3", "0.0.0.0", "pi"], env={"CI_TRUSTED_HOSTS": "api, ui"}) == {
        "localhost", "127.0.0.1", "::1", "100.1.2.3", "pi", "api", "ui"}  # a wildcard is never a name


def _api(tmp_path, hosts):
    from ci.api.app import create_app
    from tests.ci.test_api import CFG, build

    store_path, runs_dir, split = build(tmp_path)
    return TestClient(create_app(store_path=store_path, runs_dir=runs_dir, split_path=split, cfg=CFG,
                                 trusted_hosts=hosts))


def test_the_api_refuses_a_rebound_host_and_serves_its_own(tmp_path):
    c = _api(tmp_path, csrf.trusted_hosts(env={}))
    r = c.get("/api/v1/meta", headers={"Host": "evil.example:8011"})  # a DNS-rebound page reading the API
    assert r.status_code == 400 and r.json()["error"]["code"] == "untrusted_host"
    w = c.put(LEVEL, json={"level": "relaxed"}, headers={"Host": "evil.example:8011", "Origin": "http://evil.example:8011",
                                                         "Sec-Fetch-Site": "same-origin"})
    assert w.status_code == 400  # the write the CSRF check alone let through
    for host in ("127.0.0.1:8011", "localhost:8011"):  # direct, the ssh tunnel, and the Next dev proxy
        assert c.get("/api/v1/meta", headers={"Host": host}).status_code == 200, host
    assert c.put(LEVEL, json={"level": "relaxed"}, headers={"Host": "localhost:3011",
                                                            "Origin": "http://localhost:3011",
                                                            "Sec-Fetch-Site": "same-origin"}).status_code == 200


def test_the_compose_ui_reaches_the_api_by_its_service_name(tmp_path):
    c = _api(tmp_path, csrf.trusted_hosts(env={"CI_TRUSTED_HOSTS": "api"}))
    assert c.get("/api/v1/meta", headers={"Host": "api:8011"}).status_code == 200


def test_the_labeling_and_review_server_allows_the_addresses_it_listens_on(tmp_path):
    c = TestClient(create_labeling_app(runs_dir=tmp_path / "runs", labels_path=tmp_path / "l.jsonl", competitors=[],
                                       hosts=["127.0.0.1", "100.103.185.9", "pi"]))
    assert c.get("/reliability", headers={"Host": "100.103.185.9:8765"}).status_code == 200
    assert c.get("/reliability", headers={"Host": "pi:8765"}).status_code == 200
    assert c.get("/reliability", headers={"Host": "evil.example:8765"}).status_code == 400
