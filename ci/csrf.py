"""CSRF guard for the local servers (the CI API and the labeling page). They have no login, so any web page open in
the same browser could send them a POST, PUT, PATCH or DELETE. The guard refuses such a request when the browser says
it comes from another site:

- Sec-Fetch-Site (sent by every current browser) must be same-origin or none (typed by the user);
- without it, an Origin header must name a loopback host or the host the request was sent to.

Requests without either header (curl, scripts, tests) pass: they cannot be forged by a web page. Reads are never
blocked. Extra allowed origins (for example the UI over Tailscale) go in CI_ALLOWED_ORIGINS, comma-separated.
"""
import os
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAFE_FETCH_SITES = frozenset({"same-origin", "none"})
LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
ENV_VAR = "CI_ALLOWED_ORIGINS"


def _origin_host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower()


def allowed_origins(env: dict[str, str] | None = None) -> frozenset[str]:
    env = os.environ if env is None else env
    return frozenset(o.strip().rstrip("/").lower() for o in env.get(ENV_VAR, "").split(",") if o.strip())


def refusal(method: str, headers: dict[str, str], extra: frozenset[str] = frozenset()) -> str | None:
    """Why the request is refused, or None when it may go on. headers: lower-case names."""
    if method.upper() not in UNSAFE:
        return None
    origin = headers.get("origin", "").strip().rstrip("/").lower()
    if origin and origin in extra:
        return None
    site = headers.get("sec-fetch-site", "").strip().lower()
    if site:
        return None if site in SAFE_FETCH_SITES else f"cross-site request refused (Sec-Fetch-Site: {site})"
    if not origin:
        return None
    if origin == "null":
        return "cross-site request refused (Origin: null)"
    host = _origin_host(origin)
    request_host = _origin_host("//" + headers.get("host", ""))
    if host in LOOPBACK or (request_host and host == request_host):
        return None
    return f"cross-site request refused (Origin: {origin})"


class CSRFMiddleware:
    """ASGI middleware: answers 403 to a cross-site state-changing request, before any route runs."""

    def __init__(self, app: ASGIApp, extra_origins: frozenset[str] | None = None):
        self.app = app
        self.extra = allowed_origins() if extra_origins is None else extra_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            reason = refusal(scope.get("method", "GET"), headers, self.extra)
            if reason:
                body = {"error": {"code": "csrf_refused", "message": reason, "details": {}}}
                await JSONResponse(body, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
