"""Labeling page hosts: localhost plus Tailscale by default, env and --host overrides, a warning for 0.0.0.0."""
import subprocess

from ci.labeling import hosts


def test_default_is_localhost_plus_tailscale():
    assert hosts.resolve_hosts(None, env={}, detect=lambda: "100.103.185.9") == ["127.0.0.1", "100.103.185.9"]


def test_no_tailscale_means_localhost_only():
    assert hosts.resolve_hosts(None, env={}, detect=lambda: None) == ["127.0.0.1"]


def test_env_list_then_cli_take_precedence():
    env = {"LABELING_HOSTS": " 127.0.0.1, 10.0.0.5 ,"}
    assert hosts.resolve_hosts(None, env=env, detect=lambda: "x") == ["127.0.0.1", "10.0.0.5"]
    assert hosts.resolve_hosts(["0.0.0.0", "0.0.0.0"], env=env, detect=lambda: "x") == ["0.0.0.0"]


def test_wildcard_warns():
    assert hosts.wildcard_warning(["0.0.0.0"]) and hosts.wildcard_warning(["::"])
    assert hosts.wildcard_warning(["127.0.0.1", "100.103.185.9"]) is None


def test_tailscale_ip_parses_and_survives_failures(monkeypatch, caplog):
    def ok(*a, **kw):
        return subprocess.CompletedProcess(a, 0, stdout="100.103.185.9\n", stderr="")
    monkeypatch.setattr(hosts.subprocess, "run", ok)
    assert hosts.tailscale_ip() == "100.103.185.9"

    def missing(*a, **kw):
        raise FileNotFoundError("tailscale")
    monkeypatch.setattr(hosts.subprocess, "run", missing)
    assert hosts.tailscale_ip() is None and "127.0.0.1 only" in caplog.text

    def down(*a, **kw):
        raise subprocess.CalledProcessError(1, "tailscale")
    monkeypatch.setattr(hosts.subprocess, "run", down)
    assert hosts.tailscale_ip() is None


def test_bind_opens_one_socket_per_host():
    socks = hosts.bind(["127.0.0.1"], 0)
    try:
        assert len(socks) == 1 and socks[0].getsockname()[0] == "127.0.0.1"
    finally:
        for s in socks:
            s.close()
