"""Top-up labeling queue: ~30 more items from a run, picked only by model-independent signals.

    python -m ci.labeling.topup <run_id> [--target 30] [--unflagged 10] [--runs-dir DIR] [--labels PATH]
                                         [--dry-run] [--force]

No classifier, ranker or LLM decides what gets labeled: selecting by a model's own output would hide exactly the
items it gets wrong. The signals are:
- first_party: the item comes from the competitor's own feed or repo
- event_kw: launch, GA, acquisition, pricing, funding or partnership words in the title
- multi_source: several publishers carry the story
- coverage: the item matches an event in evals/coverage_events.yaml

Stories already in the golden set are skipped (the eval's story grouping over labeled items + candidates), and each
story gives at most one item. Buckets, in the order they claim stories:
- extraction_check: every story the junk detector flags (one bucket with the unflagged sample below, so the
  progress chips never reveal the detector's verdict)
- pricing, funding_ma: every candidate
- aws, snyk: at least COMPETITOR_MIN each (prefilled competitor or a title alias match)
- likely_important: by signal count
- then a small unflagged page-text sample, into extraction_check, from what is left
A target that cannot be met is reported in the queue's summary; nothing is padded. The queue uses the stratified
queue's file format (<run_id>.queue.json), with mode "topup" and require_bad_extraction: true.
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections.abc import Callable
from pathlib import Path

from ci import config as ci_config
from ci import coverage, eval_golden, extraction_quality
from ci.classify import _alias_re, _host, aliases, own_sources
from ci.labeling import stratified
from ci.labeling.app import LABELS_PATH, RUNS_DIR, latest_labels, read_jsonl
from ci.packet import INDUSTRY

TARGET = 30
COMPETITOR_MIN = 4
FOCUS_COMPETITORS = ("aws", "snyk")
IMPORTANT_TARGET = 10
UNFLAGGED_SAMPLE = 10  # raised from 4 in a manual review
EXTRACTION, PRICING, FUNDING, IMPORTANT = "extraction_check", "pricing", "funding_ma", "likely_important"

EVENT_RE = re.compile(r"\b(?:launch(?:es|ed)?|generally available|ga|acquir(?:es|ed|e)|acquisition|pricing|prices?|"
                      r"raises|funding|partnership|partners with)\b", re.IGNORECASE)
PRICING_RE = re.compile(r"\b(?:pricing|prices?|price (?:change|cut|increase)|per seat|free tier|paid (?:plan|tier)s?|"
                        r"new plans?|subscription)\b", re.IGNORECASE)
FUNDING_RE = re.compile(r"\b(?:acquir(?:es|ed|e|ing)|acquisition|merger|merges|raises|funding|series [a-f]|ipo|"
                        r"invest(?:s|ed|ment))\b", re.IGNORECASE)
STATUS_RANK = {"full": 0, "partial": 1, "snippet": 2, "junk": 3}


def _seeded(values: list, seed: str) -> list:
    out = list(values)
    random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16)).shuffle(out)
    return out


def is_first_party(item: dict, own: dict[str, set[str]]) -> bool:
    sources = own.get(item.get("competitor") or "", set())
    if item.get("source") == "github_releases":
        return f"repo:{(item.get('origin') or '').lower()}" in sources
    return item.get("source") == "vendor_feed" and _host(item.get("origin") or "") in sources


def junk_flagged(item: dict) -> bool:
    """The junk detector's verdict: set by the pipeline, or recomputed for page text from older runs."""
    if item.get("text_status") == "junk":
        return True
    return item.get("text_source") == "page" and not extraction_quality.assess(item.get("title") or "",
                                                                               item.get("text") or "").ok


def build_topup(run_id: str, items: list[dict], labeled_items: list[dict], cfg: ci_config.CIConfig,
                events: list[coverage.Event], keys_fn: Callable[[list[dict]], dict[str, str]],
                target: int = TARGET, unflagged: int = UNFLAGGED_SAMPLE) -> dict:
    labeled_ids = {it["id"] for it in labeled_items}
    candidates = [it for it in items if it["id"] not in labeled_ids]
    keys = keys_fn([*labeled_items, *candidates])
    def event_of(it: dict) -> str | None:
        return next((ev.id for ev in events if coverage.match_item(ev, it)), None)

    # a coverage event is one story too, even when the headlines are worded too differently to group: stories that
    # share an event merge whole (every member moves, not only the one that matched)
    done_stories = {keys[it["id"]] for it in labeled_items}
    done_events = {e for e in map(event_of, labeled_items) if e}
    groups: dict[str, list[dict]] = {}
    for it in candidates:
        groups.setdefault(keys[it["id"]], []).append(it)
    parent = {k: k for k in groups}

    def root(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    events_of = {k: {e for e in map(event_of, g) if e} for k, g in groups.items()}
    first_story: dict[str, str] = {}
    for k in sorted(groups):
        for ev in sorted(events_of[k]):
            if ev in first_story:
                a, b = root(k), root(first_story[ev])
                parent[max(a, b)] = min(a, b)
            else:
                first_story[ev] = k
    merged: dict[str, list[str]] = {}
    for k in sorted(groups):
        merged.setdefault(root(k), []).append(k)
    stories: dict[str, list[dict]] = {}
    for r, members in merged.items():
        if any(k in done_stories or events_of[k] & done_events for k in members):
            continue  # already in the golden set, by story or by coverage event
        stories[r] = [it for k in members for it in groups[k]]

    own = {c.key: own_sources(c) for c in cfg.competitors}
    names = {c.key: _alias_re(aliases(c)) for c in cfg.competitors if c.key != INDUSTRY}

    def signals(group: list[dict]) -> list[str]:
        out = []
        if any(is_first_party(it, own) for it in group):
            out.append("first_party")
        if any(EVENT_RE.search(it.get("title") or "") for it in group):
            out.append("event_kw")
        if len({it.get("publisher") or _host(it.get("url") or "") for it in group}) >= 2:
            out.append("multi_source")
        hits = [ev.id for ev in events for it in group if coverage.match_item(ev, it)]
        if hits:
            out.append(f"coverage:{hits[0]}")
        return out

    def names_competitor(group: list[dict], key: str) -> bool:
        return any(it.get("competitor") == key or (key in names and names[key].search(it.get("title") or ""))
                   for it in group)

    def best(group: list[dict], pick=None) -> dict:
        pool = [it for it in group if pick(it)] if pick else group
        return min(pool, key=lambda it: (not is_first_party(it, own), STATUS_RANK.get(it.get("text_status"), 4),
                                         it["id"]))

    sig = {k: signals(g) for k, g in stories.items()}
    taken: set[str] = set()
    entries: list[dict] = []
    buckets: list[dict] = []
    notes: list[str] = []

    def take(bucket: str, story_keys: list[str], why_of, pick=None, cap: int | None = None) -> int:
        n = 0
        for k in story_keys:
            if k in taken or (cap is not None and n >= cap):
                continue
            it = best(stories[k], pick)
            taken.add(k)
            entries.append({"id": it["id"], "bucket": bucket, "why": why_of(k)})
            n += 1
        return n

    def why(extra: str):
        return lambda k: "; ".join([extra, *sig[k]]) if sig[k] else extra

    order = sorted(stories)  # deterministic base order; buckets shuffle with a seed where they sample
    flagged = [k for k in order if any(junk_flagged(it) for it in stories[k])]
    n_flagged = take(EXTRACTION, flagged, why("extraction check"), pick=junk_flagged)
    extraction = {"name": EXTRACTION, "nominal": n_flagged + unflagged, "target": n_flagged,
                  "flagged": n_flagged, "unflagged_sample": 0}
    buckets.append(extraction)

    for bucket, rx in ((PRICING, PRICING_RE), (FUNDING, FUNDING_RE)):
        hits = [k for k in order if any(rx.search(it.get("title") or "") for it in stories[k])]
        n = take(bucket, hits, why(f"{bucket} words in the title"),
                 pick=lambda it, rx=rx: rx.search(it.get("title") or ""))
        buckets.append({"name": bucket, "nominal": n, "target": n})
        if not n:
            notes.append(f"{bucket}: no candidate found")

    def by_signals(keys_: list[str], seed: str) -> list[str]:
        return sorted(_seeded(keys_, seed), key=lambda k: (-any(s.startswith("coverage") for s in sig[k]),
                                                           -len(sig[k])))

    def title_names(group: list[dict], key: str) -> bool:
        return key in names and any(names[key].search(it.get("title") or "") for it in group)

    for comp in FOCUS_COMPETITORS:  # stories whose title names the competitor's products come first
        pool = by_signals([k for k in order if names_competitor(stories[k], comp)], f"{run_id}:{comp}")
        pool = sorted(pool, key=lambda k, comp=comp: not title_names(stories[k], comp))
        n = take(comp, pool, why(f"{comp} story"), cap=COMPETITOR_MIN)
        buckets.append({"name": comp, "nominal": COMPETITOR_MIN, "target": n})
        if n < COMPETITOR_MIN:
            notes.append(f"{comp}: {n} of {COMPETITOR_MIN} found")

    pool = by_signals([k for k in order if sig[k]], f"{run_id}:{IMPORTANT}")
    n = take(IMPORTANT, pool, why("signals"), cap=IMPORTANT_TARGET)
    buckets.append({"name": IMPORTANT, "nominal": IMPORTANT_TARGET, "target": n})
    if n < IMPORTANT_TARGET:
        notes.append(f"{IMPORTANT}: {n} of {IMPORTANT_TARGET} found")

    # last, from what no other bucket claimed: a few unflagged page texts, so the detector's misses get labeled too
    page_ok = [k for k in _seeded(order, f"{run_id}:sample") if k not in taken
               and any(it.get("text_source") == "page" and not junk_flagged(it) for it in stories[k])]
    n_sample = take(EXTRACTION, page_ok, why("extraction check"),
                    pick=lambda it: it.get("text_source") == "page" and not junk_flagged(it), cap=unflagged)
    extraction.update(target=n_flagged + n_sample, unflagged_sample=n_sample)
    if n_sample < unflagged:
        notes.append(f"{EXTRACTION}: unflagged sample {n_sample} of {unflagged}")

    total = len(entries)
    if total > target:
        notes.append(f"total {total} exceeds the ~{target} target: every junk-flagged, pricing and funding story "
                     "is required")
    elif total < target:
        notes.append(f"total {total} is under the ~{target} target; not padded")
    return {"version": stratified.QUEUE_VERSION, "mode": "topup", "run_id": run_id, "require_bad_extraction": True,
            "rules_hash": topup_hash(cfg), "buckets": buckets, "entries": entries,
            "summary": {"target": target, "total": total, "candidates": len(candidates),
                        "stories": len(stories), "excluded_golden_stories": len(done_stories), "notes": notes}}


def topup_hash(cfg: ci_config.CIConfig) -> str:
    parts = [Path(__file__).read_text(encoding="utf-8"), cfg.model_dump_json()]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:12]


def format_summary(queue: dict, titles: dict[str, str]) -> str:
    s = queue["summary"]
    out = [f"top-up queue {queue['run_id']}: {s['total']} items (target ~{s['target']}) from {s['stories']} new "
           f"stories ({s['candidates']} candidates, {s['excluded_golden_stories']} golden-set stories skipped)"]
    out += [f"  {b['name']:<17} {b['target']:>3}" + (f" (flagged {b['flagged']}, sample {b['unflagged_sample']})"
                                                     if b["name"] == EXTRACTION else "") for b in queue["buckets"]]
    out += [f"  note: {n}" for n in s["notes"]]
    out += [f"  [{e['bucket']}] {titles.get(e['id'], '')[:70]}  <- {e['why']}" for e in queue["entries"]]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.labeling.topup", description=__doc__.split("\n")[0])
    ap.add_argument("run_id")
    ap.add_argument("--target", type=int, default=TARGET)
    ap.add_argument("--unflagged", type=int, default=UNFLAGGED_SAMPLE,
                    help=f"unflagged page texts sampled into extraction_check (default {UNFLAGGED_SAMPLE})")
    ap.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    ap.add_argument("--labels", type=Path, default=LABELS_PATH)
    ap.add_argument("--dry-run", action="store_true", help="print the queue, write nothing")
    ap.add_argument("--force", action="store_true", help="replace an existing <run_id>.queue.json")
    args = ap.parse_args(argv)
    cfg = ci_config.load()
    run_path = args.runs_dir / f"{args.run_id}.jsonl"
    if not run_path.exists():
        print(f"no run file {run_path}", file=sys.stderr)
        return 2
    items = [ci_config.canonical_item(r) for r in read_jsonl(run_path)]
    labels = latest_labels(args.labels)
    cache: dict = {}
    labeled = [eval_golden.rebuild_item(lab, args.runs_dir, cache)[0] for lab in labels.values()]
    queue = build_topup(args.run_id, items, labeled, cfg, coverage.load_events(),
                        lambda its: eval_golden.story_keys(its, args.runs_dir, cache_path=eval_golden.EMBED_CACHE_PATH),
                        args.target, args.unflagged)
    print(format_summary(queue, {it["id"]: it.get("title") or "" for it in items}))
    if args.dry_run:
        return 0
    path = stratified.queue_path(args.runs_dir, args.run_id)
    if path.exists() and not args.force:
        print(f"{path} exists; pass --force to replace it", file=sys.stderr)
        return 1
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
