"""Which addresses the labeling page listens on: localhost plus the Tailscale IP, never the whole LAN by default."""
import logging
import os
import socket
import subprocess
from collections.abc import Callable

log = logging.getLogger(__name__)

LOCALHOST = "127.0.0.1"
ENV_VAR = "LABELING_HOSTS"  # comma-separated, e.g. 127.0.0.1,100.103.185.9
WILDCARDS = {"0.0.0.0", "::"}


def tailscale_ip() -> str | None:
    """This machine's Tailscale IPv4, or None when tailscale is missing, down or slow."""
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=3, check=True).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("tailscale ip -4 failed (%s); listening on %s only", e, LOCALHOST)
        return None
    ip = next((line.strip() for line in out.splitlines() if line.strip()), None)
    if ip is None:
        log.warning("tailscale ip -4 printed nothing; listening on %s only", LOCALHOST)
    return ip


def resolve_hosts(cli_hosts: list[str] | None, env: dict[str, str] | None = None,
                  detect: Callable[[], str | None] = tailscale_ip) -> list[str]:
    """--host values win, then LABELING_HOSTS, then localhost + the Tailscale IP. Deduplicated, order kept."""
    env = os.environ if env is None else env
    if cli_hosts:
        hosts = cli_hosts
    elif env.get(ENV_VAR, "").strip():
        hosts = [h.strip() for h in env[ENV_VAR].split(",") if h.strip()]
    else:
        hosts = [LOCALHOST, *filter(None, [detect()])]
    return list(dict.fromkeys(hosts))


def wildcard_warning(hosts: list[str]) -> str | None:
    if WILDCARDS & set(hosts):
        return ("WARNING: listening on all interfaces, so anyone on the network can read and write labels. "
                "Use this only inside a container whose published port is restricted.")
    return None


def bind(hosts: list[str], port: int) -> list[socket.socket]:
    """One listening socket per host, for uvicorn.Server.run(sockets=...)."""
    socks = []
    for host in hosts:
        family = socket.AF_INET6 if ":" in host else socket.AF_INET
        s = socket.socket(family, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            s.close()
            for opened in socks:
                opened.close()
            raise
        s.listen(128)
        s.set_inheritable(True)
        socks.append(s)
    return socks
