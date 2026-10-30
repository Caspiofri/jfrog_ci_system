import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlparse

import requests

_DEAD_STATUSES = {404, 410}


_CL0 = re.compile(r"^https?://[^/]*tldrnewsletter\.com/CL0/(https?[:%][^/]+)/", re.IGNORECASE)


def unwrap_tracking(url: str) -> str:
    """Unwrap TLDR-style click-tracking links (.../CL0/<percent-encoded target>/...) to the real target."""
    m = _CL0.match(url)
    return unquote(m.group(1)) if m else url


_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "_hsenc", "_hsmi", "ref", "source"}
# Links that hide the real article address behind a per-email redirect id: (host, path prefix).
_REDIRECTORS = (("substack.com", "/redirect/"), ("www.substack.com", "/redirect/"))


def _is_redirector(url: str) -> bool:
    p = urlparse(url)
    return any(p.hostname == host and p.path.startswith(prefix) for host, prefix in _REDIRECTORS)


def _strip_tracking(url: str) -> str:
    """Drop the fragment and tracking query parameters (utm_*, fbclid, ...); other parameters keep their order."""
    p = urlparse(unwrap_tracking(url))
    kept = [kv for kv in p.query.split("&")
            if kv and not (kv.split("=", 1)[0].lower().startswith("utm_")
                           or kv.split("=", 1)[0].lower() in _TRACKING_PARAMS)]
    return p._replace(query="&".join(kept), fragment="").geturl()


def canonical_url(original: str, final_url: str) -> str:
    """The one address an article should be known by.

    A known redirector (e.g. substack.com/redirect/<per-email id>) is replaced by the address it led to;
    everything else keeps its own URL. Tracking parameters and the fragment are stripped either way.
    Never raises: on any problem the original comes back.
    """
    try:
        if final_url and _is_redirector(original) and urlparse(final_url).hostname != urlparse(original).hostname:
            return _strip_tracking(final_url)
        return _strip_tracking(original)
    except Exception:
        return original


def resolve_link(url: str, timeout: int = 8) -> tuple[str, str]:
    """Follow redirects once and return (status, final_url).

    status: "dead" (404/410), "unverified" (Cloudflare bot challenge, so we cannot tell), else "ok".
    Other 403s and network errors count as "ok": many sites block scripts but work in a browser.
    final_url is where the redirects ended, or url itself when the request failed.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; newsletter-agent/1.0)"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        resp.close()
    except requests.RequestException:
        return "ok", url
    final = getattr(resp, "url", None) or url
    if resp.status_code in _DEAD_STATUSES:
        return "dead", final
    if resp.headers.get("cf-mitigated", "").lower() == "challenge":
        return "unverified", final
    return "ok", final


def check_link(url: str, timeout: int = 8) -> str:
    """Classify a link: "dead", "unverified" or "ok" (see resolve_link)."""
    return resolve_link(url, timeout)[0]


def resolve_links(urls: list[str], max_workers: int = 16) -> dict[str, tuple[str, str]]:
    """Map each url to its resolve_link (status, final_url)."""
    unique = list(dict.fromkeys(urls))
    if not unique:
        return {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return dict(zip(unique, pool.map(resolve_link, unique), strict=True))
