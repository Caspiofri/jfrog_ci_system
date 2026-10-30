"""Stratified labeling queue: 60 items per run, balanced across competitors, industry and likely noise.

The golden set needs every competitor, the industry channel and enough noise, so the queue takes up to 6 items per
tracked competitor, 8 industry items and fills the rest of the 60 with likely-noise items (16 with six competitors).
The noise signal comes from ci.classify's offline rules (no LLM, no network) and wins over the prefilled competitor,
so each item lands in exactly one bucket. Short buckets are filled from the remaining noise candidates, then from the
rest of the run. Order is shuffled with a seed derived from the run id, and the queue is stored as
<run_id>.queue.json so it survives reloads and restarts. A stored queue is never rebuilt unless asked.
"""
import hashlib
import json
import os
import random
from pathlib import Path

from ci import classify as classify_mod
from ci import config as ci_config
from ci.classify import MARKETING_HINT_RE, NOISE_HINT_RE, Classifier
from ci.packet import INDUSTRY

PER_COMPETITOR = 6  # nominal; scaled down when the competitors would not fit in TARGET
INDUSTRY_QUOTA = 8
TARGET = 60  # noise takes whatever the competitors and industry leave (16 with six competitors)
NOISE = "noise"
REST = "rest"  # gap filler when noise runs dry: whatever is left in the run
QUEUE_VERSION = 1


def queue_path(runs_dir: Path, run_id: str) -> Path:
    return runs_dir / f"{run_id}.queue.json"


def quotas_for(tracked: list[str]) -> tuple[dict[str, int], int]:
    """(per-bucket quotas for competitors and industry, the noise quota), summing to TARGET."""
    per = min(PER_COMPETITOR, (TARGET - INDUSTRY_QUOTA) // len(tracked)) if tracked else 0
    quotas = {**dict.fromkeys(tracked, per), INDUSTRY: INDUSTRY_QUOTA}
    return quotas, TARGET - sum(quotas.values())


def rules_hash(cfg: ci_config.CIConfig) -> str:
    """Fingerprint of what decides the buckets: the classifier rules, the competitors config, the quotas."""
    parts = [Path(classify_mod.__file__).read_text(encoding="utf-8"), cfg.model_dump_json(),
             json.dumps([PER_COMPETITOR, INDUSTRY_QUOTA, TARGET, QUEUE_VERSION])]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:12]


def noise_signal(item: dict, clf: Classifier) -> str | None:
    """Why the item is likely noise, from the offline rules only; None when it looks like a real story."""
    title, prefilled = item.get("title") or "", item.get("competitor") or ""
    if NOISE_HINT_RE.search(title):
        return "title looks like market chatter"
    if prefilled not in clf.alias_res:  # industry and anything untracked: only the chatter signal applies
        return None
    settled, _ = clf.apply_rules(item)
    if settled is not None:  # rules are confident: a real competitor story
        return None
    weights = clf._mention_weights(item)
    own, name = weights[prefilled], clf.names[prefilled]
    if own == 0 and not clf.is_first_party(item):
        return f"{name} never named: ambiguous name or generic match"
    rival = max((k for k in weights if k != prefilled), key=lambda k: weights[k])
    if weights[rival] > own:
        return f"mostly about {clf.names[rival]}, not {name}"
    if own <= 1 and MARKETING_HINT_RE.search(title):
        return f"listicle or marketing with a passing {name} mention"
    return None


def bucket_of(item: dict, clf: Classifier) -> tuple[str, str]:
    """(bucket, why). A noise signal wins over the prefilled competitor; untracked competitors go to REST."""
    why = noise_signal(item, clf)
    if why:
        return NOISE, why
    comp = item.get("competitor") or ""
    if comp in clf.alias_res or comp == INDUSTRY:
        return comp, f"prefilled {comp}"
    return REST, f"prefilled {comp or 'nothing'}"


def _pool(ids: list[str], seed: str, labeled: set[str]) -> list[str]:
    """Seeded shuffle with already-labeled items first, so earlier work counts toward the bucket."""
    out = sorted(ids)  # independent of run file order
    random.Random(seed).shuffle(out)
    return sorted(out, key=lambda i: i not in labeled)  # stable: keeps the shuffled order within each group


def build_queue(run_id: str, items: list[dict], labeled: set[str], cfg: ci_config.CIConfig) -> dict:
    clf = Classifier(None, cfg)  # rules only; the LLM is never called
    tracked = [c.key for c in cfg.competitors if c.key != INDUSTRY]
    quotas, noise_quota = quotas_for(tracked)
    ids_by_bucket: dict[str, list[str]] = {}
    why: dict[str, str] = {}
    for item in items:
        b, reason = bucket_of(item, clf)
        if item["id"] in why:
            continue  # a duplicate id in the run file
        ids_by_bucket.setdefault(b, []).append(item["id"])
        why[item["id"]] = reason

    seed = f"labeling-queue:{run_id}"
    pools = {b: _pool(ids, f"{seed}:{b}", labeled) for b, ids in ids_by_bucket.items()}
    picks = {b: pools.get(b, [])[:q] for b, q in quotas.items()}
    gap = sum(q - len(picks[b]) for b, q in quotas.items())
    picks[NOISE] = pools.get(NOISE, [])[:noise_quota + gap]
    gap = noise_quota + gap - len(picks[NOISE])
    # the rest: competitor and industry items beyond their quota, plus untracked items
    leftover = [i for b, q in quotas.items() for i in pools.get(b, [])[q:]] + ids_by_bucket.get(REST, [])
    picks[REST] = _pool(leftover, f"{seed}:{REST}", labeled)[:gap]

    order = [*tracked, INDUSTRY, NOISE, REST]
    buckets = []
    for b in order:
        chosen = set(picks[b])
        # within a bucket, show the seeded order (labeled-first only decided who got in)
        ids = _pool(list(chosen), f"{seed}:{b}:order", set())
        if b == REST:
            for i in ids:
                why[i] = f"gap filler ({why[i]})"
        nominal = quotas.get(b, noise_quota if b == NOISE else 0)
        buckets.append({"name": b, "nominal": nominal, "target": len(ids), "ids": ids})
    entries = [{"id": i, "bucket": b["name"], "why": why[i]} for b in buckets for i in b["ids"]]
    return {"version": QUEUE_VERSION, "run_id": run_id, "seed": seed, "target": TARGET,
            "rules_hash": rules_hash(cfg),
            "buckets": [{k: v for k, v in b.items() if k != "ids"} for b in buckets], "entries": entries}


def load_or_build(runs_dir: Path, run_id: str, items: list[dict], labeled: set[str],
                  cfg: ci_config.CIConfig, rebuild: bool = False) -> dict:
    """The stored queue if there is a valid one, else a new one written atomically next to the run.

    A stored queue is never rebuilt on its own, even when the rules changed (someone may be labeling from it);
    only rebuild=True replaces it. Already-labeled items are picked first, so a rebuild keeps finished work."""
    path = queue_path(runs_dir, run_id)
    stored = _read_queue(path, run_id)
    if stored is not None and stored.get("mode") == "topup":
        return canonical_queue(stored)  # a top-up queue is never replaced by a stratified rebuild
    if path.exists() and not rebuild:
        try:
            queue = json.loads(path.read_text(encoding="utf-8"))
            if queue.get("version") == QUEUE_VERSION and queue.get("run_id") == run_id:
                return canonical_queue(queue)
        except (json.JSONDecodeError, OSError, AttributeError):
            pass  # rebuild below
    queue = build_queue(run_id, items, labeled, cfg)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return queue


def _read_queue(path: Path, run_id: str) -> dict | None:
    try:
        queue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return queue if isinstance(queue, dict) and queue.get("run_id") == run_id else None


def requires_bad_extraction(runs_dir: Path, run_id: str) -> set[str]:
    """Ids whose label must answer bad_extraction explicitly: the entries of a queue marked so (the top-up)."""
    queue = _read_queue(queue_path(runs_dir, run_id), run_id)
    if not queue or not queue.get("require_bad_extraction"):
        return set()
    return {e.get("id") for e in queue.get("entries", [])}


def canonical_queue(queue: dict) -> dict:
    """A stored queue with legacy competitor keys in its bucket names mapped (the file is not rewritten)."""
    key = ci_config.canonical_key
    return {**queue, "buckets": [{**b, "name": key(b.get("name"))} for b in queue.get("buckets", [])],
            "entries": [{**e, "bucket": key(e.get("bucket"))} for e in queue.get("entries", [])]}


def with_progress(queue: dict, labels: dict[str, dict], current_hash: str | None = None) -> dict:
    """The queue plus labeled counts per bucket and overall, and whether it was built with other rules."""
    done = {e["id"] for e in queue["entries"] if e["id"] in labels}
    per = {}
    for e in queue["entries"]:
        per[e["bucket"]] = per.get(e["bucket"], 0) + (e["id"] in done)
    buckets = [{**b, "labeled": per.get(b["name"], 0)} for b in queue["buckets"]]
    # no hash: built before hashing; a top-up queue has its own selection, never the stratified rules
    stale = current_hash is not None and queue.get("mode") != "topup" and queue.get("rules_hash") != current_hash
    return {**queue, "buckets": buckets, "labeled": len(done), "total": len(queue["entries"]), "stale": stale}
