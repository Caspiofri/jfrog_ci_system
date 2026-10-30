"""Coverage check: of the real competitor events in a period, how many did a collection run capture (coverage recall).

    python -m ci.coverage <run_id> [--runs-dir DIR] [--events PATH] [--out-dir DIR]

The ground truth is evals/coverage_events.yaml, hand-curated from official sources. An event counts as captured when
any item of the run, kept or dropped, matches it:

  - URL: the item's normalized url or original_url (ci.dedupe.normalize_url: scheme and host lowercased, fragment,
    utm_*/ref/source params and trailing slash dropped) equals the normalized official_url or one of match.urls; or
  - keywords: the item's TITLE contains ALL keywords of ANY one group in match.title_keywords. Matching is
    case-insensitive, on word boundaries (whitespace inside a keyword matches any whitespace), and a trailing *
    matches a word prefix ("exploit*" matches "exploited"). The text is deliberately not searched: on the Oct 30 run,
    matching the opening 500 chars as well pulled in listicles and other posts from the same vendor that merely
    mentioned the event (a "Snyk vs Mend vs Socket" roundup, a different Sonatype eMudhra post). A story whose
    title doesn't name the event is not coverage of it.

Recall is over the events dated inside the run's window (started_at - window_days, by calendar date, through the
start date). Events outside it are reported separately with whether anything matched them, and excluded from recall.
A captured event found only in dropped items (deduped) is flagged: the run saw it, but the kept stream lost the copy.
Writes output/coverage/<run_id>.json and prints a table. Read-only on the run files.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from ci import config as ci_config
from ci.classify import CATEGORIES, _host, own_sources
from ci.config import canonical_item, canonical_key
from ci.dedupe import normalize_url
from config.settings import EVALS_DIR, OUTPUT_DIR

EVENTS_PATH = EVALS_DIR / "coverage_events.yaml"
COVERAGE_DIR = OUTPUT_DIR / "coverage"
RUNS_DIR = OUTPUT_DIR / "runs"
HIGH_IMPORTANCE = 4  # expected_importance at or above this gets its own recall line
RUN_ID_RE = re.compile(r"^(\d{8}T\d{4}Z)-")


@dataclass
class Event:
    id: str
    competitor: str
    date: date
    title: str
    official_url: str
    category: str
    expected_importance: int
    urls: list[str] = field(default_factory=list)
    keyword_groups: list[list[str]] = field(default_factory=list)

    def url_keys(self) -> set[str]:
        return {normalize_url(u) for u in [self.official_url, *self.urls]}


def load_events(path: Path = EVENTS_PATH) -> list[Event]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))["events"]
    events, seen = [], set()
    for e in raw:
        if e["id"] in seen:
            raise ValueError(f"duplicate event id {e['id']}")
        seen.add(e["id"])
        if e["category"] not in CATEGORIES:
            raise ValueError(f"{e['id']}: category {e['category']!r} is not one of the D11 categories")
        if not 1 <= int(e["expected_importance"]) <= 5:
            raise ValueError(f"{e['id']}: expected_importance must be 1-5")
        match = e.get("match") or {}
        groups = [[str(k) for k in g] for g in match.get("title_keywords") or []]
        if any(not g for g in groups):
            raise ValueError(f"{e['id']}: empty keyword group")
        d = e["date"] if isinstance(e["date"], date) else date.fromisoformat(str(e["date"]))
        events.append(Event(id=e["id"], competitor=canonical_key(e["competitor"]), date=d, title=e["title"],
                            official_url=e["official_url"], category=e["category"],
                            expected_importance=int(e["expected_importance"]), urls=list(match.get("urls") or []),
                            keyword_groups=groups))
    return events


def keyword_re(keyword: str) -> re.Pattern:
    """Case-insensitive, word-bounded; whitespace matches any whitespace; a trailing * leaves the end open."""
    prefix = keyword.endswith("*")
    body = keyword[:-1] if prefix else keyword
    pattern = r"\s+".join(re.escape(w) for w in body.split())
    return re.compile(rf"(?<!\w){pattern}" + ("" if prefix else r"(?!\w)"), re.IGNORECASE)


def group_matches(group: list[str], text: str) -> bool:
    return all(keyword_re(k).search(text) for k in group)


def match_item(event: Event, item: dict) -> str | None:
    """Why the item matches the event ("url" or "keywords: kw + kw"), or None."""
    item_urls = {normalize_url(u) for u in (item.get("url"), item.get("original_url")) if u}
    if item_urls & event.url_keys():
        return "url"
    title = item.get("title") or ""
    for group in event.keyword_groups:
        if group_matches(group, title):
            return "keywords: " + " + ".join(group)
    return None


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    # split on "\n" only: splitlines() also breaks on U+2028/U+2029/NEL inside scraped text
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def run_window(run_id: str, runs_dir: Path, default_days: int = 7) -> tuple[date, date, int]:
    """(first date, last date, window_days) of the run, from its report, else from the run id's timestamp."""
    report_path = runs_dir / f"{run_id}.report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        started = datetime.fromisoformat(report["started_at"])
        days = int(report.get("window_days", default_days))
    else:
        m = RUN_ID_RE.match(run_id)
        if not m:
            raise ValueError(f"no report for {run_id} and its id carries no timestamp")
        started = datetime.strptime(m.group(1), "%Y%m%dT%H%MZ")
        days = default_days
    return (started - timedelta(days=days)).date(), started.date(), days


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _recall_rows(rows: list[dict], key) -> dict:
    groups: dict = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return {str(k): {"events": len(v), "captured": sum(r["captured"] for r in v),
                     "recall": _ratio(sum(r["captured"] for r in v), len(v))}
            for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


FEED_FILE_RE = re.compile(r"^(?:feed|rss|atom)$|\.(?:xml|rss|atom)$", re.IGNORECASE)


def _site_prefix(url: str) -> tuple[str, str]:
    """(host, path prefix) of the pages a feed or listing covers: its URL minus a trailing feed file or feed dir."""
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if parts and FEED_FILE_RE.search(parts[-1]):
        parts = parts[:-1]
    return _host(url), "/" + "".join(f"{p}/" for p in parts)


def read_sites(cfg: ci_config.CIConfig) -> set[tuple[str, str]]:
    """Every (host, path prefix) the tool reads: configured feeds (their `site` when set) and listing pages."""
    sites = set()
    for c in cfg.competitors:
        sites |= {_site_prefix(f.site or f.url) for f in c.feeds}
        sites |= {_site_prefix(page.url) for page in c.listing_pages}
    return sites


def source_kind(url: str, cfg: ci_config.CIConfig) -> str:
    """"feed" when the event's official page is in a section of a site the tool reads (a configured feed's or
    listing page's host and path prefix: aws.amazon.com/blogs/security/ does not cover .../blogs/publicsector/), or
    in one of the configured GitHub repos; else "external"."""
    host, path = _host(url), urlsplit(url).path
    path = path if path.endswith("/") else path + "/"
    if any(host == h and path.startswith(prefix) for h, prefix in read_sites(cfg)):
        return "feed"
    repos = set().union(*(own_sources(c) for c in cfg.competitors))
    parts = path.strip("/").split("/")
    if host == "github.com" and len(parts) >= 2 and f"repo:{parts[0]}/{parts[1]}".lower() in repos:
        return "feed"
    return "external"


def evaluate(events: list[Event], kept: list[dict], dropped: list[dict], window: tuple[date, date],
             cfg: ci_config.CIConfig | None = None) -> dict:
    first, last = window
    cfg = cfg or ci_config.load()
    rows = []
    for ev in events:
        hits = []
        for status, items in (("kept", kept), ("dropped", dropped)):
            for item in items:
                reason = match_item(ev, item)
                if reason:
                    hits.append({"status": status, "id": item.get("id", ""), "title": item.get("title", ""),
                                 "url": item.get("url", ""), "competitor": item.get("competitor", ""),
                                 "reason": reason})
        statuses = {h["status"] for h in hits}
        rows.append({"id": ev.id, "competitor": ev.competitor, "date": ev.date.isoformat(), "title": ev.title,
                     "official_url": ev.official_url, "source_kind": source_kind(ev.official_url, cfg),
                     "category": ev.category,
                     "expected_importance": ev.expected_importance, "in_window": first <= ev.date <= last,
                     "captured": bool(hits), "kept": "kept" in statuses,
                     "dropped_only": statuses == {"dropped"}, "matches": hits})
    scored = [r for r in rows if r["in_window"]]
    high = [r for r in scored if r["expected_importance"] >= HIGH_IMPORTANCE]
    captured = sum(r["captured"] for r in scored)
    return {
        "window": {"first": first.isoformat(), "last": last.isoformat()},
        "items": {"kept": len(kept), "dropped": len(dropped)},
        "overall": {"events": len(scored), "captured": captured, "recall": _ratio(captured, len(scored)),
                    "captured_in_kept": sum(r["kept"] for r in scored),
                    "captured_dropped_only": sum(r["dropped_only"] for r in scored)},
        "high_importance": {"min": HIGH_IMPORTANCE, "events": len(high),
                            "captured": sum(r["captured"] for r in high),
                            "recall": _ratio(sum(r["captured"] for r in high), len(high))},
        "by_competitor": _recall_rows(scored, lambda r: r["competitor"]),
        "by_importance": _recall_rows(scored, lambda r: r["expected_importance"]),
        # "feed": the event's page is on a source the tool reads, so a miss is a pipeline miss; "external": the tool
        # can only see it through news search or HN
        "by_source_kind": _recall_rows(scored, lambda r: r["source_kind"]),
        "missed": [{k: r[k] for k in ("id", "title", "competitor", "expected_importance", "official_url")}
                   for r in scored if not r["captured"]],
        "dropped_only": [{"id": r["id"], "title": r["title"]} for r in scored if r["dropped_only"]],
        "out_of_window": [{k: r[k] for k in ("id", "date", "title", "competitor", "expected_importance",
                                             "captured")} for r in rows if not r["in_window"]],
        "events": rows,
    }


def _pct(v: float | None) -> str:
    return "  n/a" if v is None else f"{v * 100:4.0f}%"


def format_report(report: dict) -> str:
    o, h, w = report["overall"], report["high_importance"], report["window"]
    out = [f"coverage {report['run_id']}  window {w['first']}..{w['last']}  "
           f"({report['items']['kept']} kept, {report['items']['dropped']} dropped items)",
           f"recall {_pct(o['recall'])}  {o['captured']}/{o['events']} events  "
           f"(in kept {o['captured_in_kept']}, dropped only {o['captured_dropped_only']})",
           f"importance >= {h['min']}: {_pct(h['recall'])}  {h['captured']}/{h['events']}", "",
           f"{'competitor':<18}{'events':>7}{'captured':>9}{'recall':>8}"]
    out += [f"{k:<18}{v['events']:>7}{v['captured']:>9}{_pct(v['recall']):>8}"
            for k, v in report["by_competitor"].items()]
    for title, key in (("importance", "by_importance"), ("source", "by_source_kind")):
        out += ["", f"{title:<18}{'events':>7}{'captured':>9}{'recall':>8}"]
        out += [f"{k:<18}{v['events']:>7}{v['captured']:>9}{_pct(v['recall']):>8}" for k, v in report[key].items()]
    out += ["", "missed:"] + ([f"  [{m['expected_importance']}] {m['id']}: {m['title']}" for m in report["missed"]]
                              or ["  (none)"])
    out += ["", "captured only in dropped items (deduped):"]
    out += [f"  {m['id']}: {m['title']}" for m in report["dropped_only"]] or ["  (none)"]
    out += ["", "outside the run window (not in recall):"]
    out += [f"  {m['date']} [{m['expected_importance']}] {m['id']}: "
            f"{'matched' if m['captured'] else 'no match'}" for m in report["out_of_window"]] or ["  (none)"]
    return "\n".join(out)


def run(run_id: str, runs_dir: Path = RUNS_DIR, events_path: Path = EVENTS_PATH,
        out_dir: Path = COVERAGE_DIR, cfg: ci_config.CIConfig | None = None) -> dict:
    kept_path = runs_dir / f"{run_id}.jsonl"
    if not kept_path.exists():
        raise FileNotFoundError(f"no kept items for run {run_id} in {runs_dir}")
    first, last, days = run_window(run_id, runs_dir)
    kept = [canonical_item(r) for r in read_jsonl(kept_path)]  # old runs carry aws_codeartifact
    dropped = [canonical_item(r) for r in read_jsonl(runs_dir / f"{run_id}.dropped.jsonl")]
    report = {"run_id": run_id, "runs_dir": str(runs_dir), "events_file": str(events_path), "window_days": days,
              **evaluate(load_events(events_path), kept, dropped, (first, last), cfg)}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{run_id}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    parser.add_argument("--events", type=Path, default=EVENTS_PATH)
    parser.add_argument("--out-dir", type=Path, default=COVERAGE_DIR)
    args = parser.parse_args(argv)
    report = run(args.run_id, args.runs_dir, args.events, args.out_dir)
    print(format_report(report))
    print(f"\nwrote {args.out_dir / (args.run_id + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
