"""Golden-set eval of the classifier (D11) and ranker (D14), per PRD D17.

    python -m ci.eval_golden [--split train|test|all] [--live]

The default is the train split, which is the one to tune on. The test split runs only when asked for explicitly
(--split test); every such run is logged with the prompts+rules fingerprint (see the Eval protocol).

Reads evals/golden_set.jsonl (latest label per id wins), rebuilds each item from its snapshot, runs the classifier
and the ranker, and reports accuracy against the labels. Without --live the LLM abstains (a fake that answers
nothing), so the numbers are the rules-only baseline and no API key is needed. Writes output/evals/<timestamp>.json
and prints a table. Read-only on the golden set and the runs.
"""
import argparse
import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from ci import classify as classify_mod
from ci import config as ci_config
from ci import extraction_quality
from ci import mentions as side_mentions
from ci import rank as rank_mod
from ci.classify import Classification, Classifier
from ci.dedupe import EMBED_TEXT_CHARS, default_embedding_fn
from ci.labeling.app import LABELS_PATH, RUNS_DIR, latest_labels, read_jsonl
from ci.llm import FakeLLM, GeminiLLM, JsonLLM
from ci.rank import Ranked, Ranker
from config.settings import DATA_DIR, EVALS_DIR, OUTPUT_DIR
from evals.rank_split import TEST_PERCENT  # same 75/25 ratio as the ranking eval (D17)

EVALS_OUT_DIR = OUTPUT_DIR / "evals"
K_VALUES = (10,)  # P@10 is the headline (Ofri, Oct 30)
IMPORTANT_MIN = 4  # a labeled score at or above this counts as a hit for precision@k
SNIPPET_MAX_CHARS = 500  # snapshot text shorter than this is treated as a snippet when the run file is gone
CONFUSIONS_SHOWN = 8
PUBLISHER_SUFFIX_RE = re.compile(r"\s+[-–—|]\s+\S+(?:\s+\S+){0,3}$")  # " - Publisher" of up to 4 words
SPLITS = ("test", "train", "all")
# Story grouping for the split: cosine similarity of the dedupe embedding (title + 300 chars). Chosen on the Oct 30
# run: 0.72 joins the reworded copies (Copilot Fusion, Orbit GA, the Ruby/GitLab RCE reports, Roku, LiteLLM) with
# two false merges (two Copilot Automations posts, two snyk cli releases); 0.75 keeps the same false merge and drops
# true ones, 0.70 adds unrelated Copilot and agent-security posts.
STORY_SIMILARITY = 0.72
EMBED_MODEL_TAG = "chroma-onnx-all-MiniLM-L6-v2"
EMBED_CACHE_PATH = DATA_DIR / "ci" / "eval_story_embeddings.json"
SPLIT_ASSIGNMENTS_PATH = EVALS_DIR / "split_assignments.json"  # item id -> side, fixed the first time it is assigned
RANKED_FIELDS = {"raw_score", "degraded", "score", "why_it_matters", "reason", "adjustments", "needs_review",
                 "review_reasons"}
TEST_LOG_NAME = "test_runs.log"  # every --split test run is appended here, so repeated peeking at test is visible


def assign_split(story_key: str, test_percent: int = TEST_PERCENT) -> str:
    """Deterministic by story key: every copy of a story is on the same side, across runs and machines."""
    bucket = int(hashlib.sha1(story_key.encode("utf-8")).hexdigest()[:8], 16) % 100
    return "test" if bucket < test_percent else "train"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_assignments(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    sides = data.get("sides", {}) if isinstance(data, dict) else {}
    return {k: v for k, v in sides.items() if v in ("train", "test")}


def assign_sides(keys: dict[str, str], path: Path | None) -> tuple[dict[str, str], list[dict]]:
    """Item id -> side, persisted so a labeled item never changes side once assigned.

    A new item takes the side its story group already has; a group with no persisted member is placed by hashing
    its key. When a merge joins groups already persisted on different sides, every member keeps its own side, new
    members follow the majority (ties: the key hash), and the group is reported as a conflict.
    """
    persisted = load_assignments(path)
    groups: dict[str, list[str]] = {}
    for item_id, key in keys.items():
        groups.setdefault(key, []).append(item_id)
    sides, conflicts = {}, []
    for key, members in sorted(groups.items()):
        known = Counter(persisted[m] for m in members if m in persisted)
        if len(known) > 1:
            conflicts.append({"group": key, "ids": sorted(members),
                              "sides": {m: persisted[m] for m in sorted(members) if m in persisted}})
        top = known.most_common()
        if not top or (len(top) > 1 and top[0][1] == top[1][1]):
            default = assign_split(key)
        else:
            default = top[0][0]
        for m in members:
            sides[m] = persisted.get(m, default)
    new = {m: s for m, s in sides.items() if m not in persisted}
    if new and path is not None:
        merged = {**persisted, **new}
        _write_atomic(path, json.dumps({"version": 1, "sides": dict(sorted(merged.items()))}, indent=1) + "\n")
    return sides, conflicts


def normalize_title(title: str, publisher: str = "") -> str:
    """Lowercase, the " - Publisher" suffix dropped, punctuation stripped, whitespace collapsed."""
    t = " ".join((title or "").split())
    if publisher and t.lower().endswith(f" - {publisher.lower()}"):
        t = t[: -len(publisher) - 3]
    else:
        t = PUBLISHER_SUFFIX_RE.sub("", t)
    return " ".join(re.sub(r"[^\w\s]", " ", t.lower()).split())


class _Union:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


EmbedFn = Callable[[list[str]], list]


def story_embed_text(item: dict) -> str:
    """What dedupe embeds (ci.dedupe.embed_text): title plus the first EMBED_TEXT_CHARS of text."""
    return f"{item.get('title') or ''}. {(item.get('text') or '')[:EMBED_TEXT_CHARS]}"


def cached_embeddings(texts: list[str], embed_fn: Callable[[], EmbedFn], cache_path: Path | None) -> np.ndarray:
    """Unit-normalized embeddings, reusing a JSON cache keyed by the text's hash; embed_fn is only built on a miss."""
    cache: dict[str, list[float]] = {}
    if cache_path is not None and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}
    keys = [hashlib.sha1(f"{EMBED_MODEL_TAG}|{t}".encode()).hexdigest() for t in texts]
    missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in cache]
    if missing:
        vectors = embed_fn()([t for _, t in missing])
        cache.update({k: [round(float(x), 6) for x in v] for (k, _), v in zip(missing, vectors, strict=True)})
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
    emb = np.array([cache[k] for k in keys], dtype=float).reshape(len(texts), -1)
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    return emb / np.where(norms == 0, 1, norms)


def story_keys(items: list[dict], runs_dir: Path, embed_fn: Callable[[], EmbedFn] | None = None,
               cache_path: Path | None = None, threshold: float | None = None) -> dict[str, str]:
    """Item id -> story key. Items are one story when they share a normalized title, are linked through any run's
    dedupe drops (dropped item -> duplicate_of), or their embeddings (as dedupe computes them) have cosine
    similarity >= STORY_SIMILARITY. The key is the group's smallest member id, so the split is deterministic."""
    threshold = STORY_SIMILARITY if threshold is None else threshold
    uf = _Union()

    def link(row: dict) -> None:
        if not row.get("id"):
            return
        title = normalize_title(row.get("title") or "", row.get("publisher") or "")
        uf.union(f"id:{row['id']}", f"title:{title or 'untitled ' + row['id']}")  # no title never merges stories
        if row.get("duplicate_of"):
            uf.union(f"id:{row['id']}", f"id:{row['duplicate_of']}")

    for path in sorted(runs_dir.glob("*.jsonl")) if runs_dir.is_dir() else []:
        for row in read_jsonl(path):
            link(row)
    for item in items:
        link(item)
    if len(items) > 1:
        emb = cached_embeddings([story_embed_text(it) for it in items], embed_fn or default_embedding_fn, cache_path)
        sim = emb @ emb.T
        for a, b in zip(*np.nonzero(np.triu(sim >= threshold, k=1)), strict=True):
            uf.union(f"id:{items[a]['id']}", f"id:{items[b]['id']}")
    groups: dict[str, list[str]] = {}
    for node in list(uf.parent):
        if node.startswith("id:"):
            groups.setdefault(uf.find(node), []).append(node[len("id:"):])
    return {it["id"]: min(groups[uf.find(f"id:{it['id']}")]) for it in items}


def _frozen(value):
    if callable(value) and hasattr(value, "__code__"):  # a rule predicate: its source, never its memory address
        try:
            return inspect.getsource(value).strip()
        except (OSError, TypeError):
            return value.__code__.co_code.hex()
    if isinstance(value, re.Pattern):
        return value.pattern
    if isinstance(value, set | frozenset):
        return sorted(value)
    if isinstance(value, dict):
        return {str(k): _frozen(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_frozen(v) for v in value]
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    text = repr(value)
    if " at 0x" in text:
        raise ValueError(f"fingerprint would depend on a memory address: {text}")
    return text


def fingerprint(cfg: ci_config.CIConfig | None = None, side_hashes: dict[str, str] | None = None) -> str:
    """Hash of everything that shapes the numbers: both prompt templates, the full source of ci/classify.py and
    ci/rank.py, every module-level constant there, the whole competitors config, and the eval's own knobs (story
    similarity, embedding text length, test percent, the importance cutoff).
    Test numbers are only meaningful for a fingerprint that was frozen before test was looked at."""
    cfg = cfg or ci_config.load()
    parts = {
        "classify_prompt": classify_mod.Classifier(FakeLLM(), cfg).prompt([]),
        "rank_prompt": rank_mod.Ranker.prompt([]),
        **{f"classify.{k}": _frozen(v) for k, v in sorted(vars(classify_mod).items()) if k.isupper()},
        **{f"rank.{k}": _frozen(v) for k, v in sorted(vars(rank_mod).items()) if k.isupper()},
        "eval.STORY_SIMILARITY": STORY_SIMILARITY,
        "eval.EMBED_MODEL_TAG": EMBED_MODEL_TAG,
        "eval.EMBED_TEXT_CHARS": EMBED_TEXT_CHARS,
        "eval.TEST_PERCENT": TEST_PERCENT,
        "eval.IMPORTANT_MIN": IMPORTANT_MIN,
        "eval.metrics": inspect.getsource(evaluate) + inspect.getsource(detector_vs_flags),
        "classify.source": inspect.getsource(classify_mod),
        "rank.source": inspect.getsource(rank_mod),
        "extraction_quality.source": inspect.getsource(extraction_quality),
        **{f"extraction_quality.{k}": _frozen(v) for k, v in sorted(vars(extraction_quality).items())
           if k.isupper()},
        "config": cfg.model_dump(mode="json"),
        "mention_side_files": dict(sorted((side_hashes or {}).items())),  # run_id -> hash, backfilled counts
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


BASES = ("full", "partial", "unknown")
BAD_EXTRACTION = ("true", "false", "unknown")


def label_bad_extraction(label: dict) -> str:
    flag = label.get("bad_extraction")
    return "unknown" if flag is None else str(bool(flag)).lower()


def detector_vs_flags(labels: list[dict], items: list[dict]) -> dict:
    """ci.extraction_quality run on each labeled item's run-file text, against Ofri's Bad extraction flags
    (positive = junk). Only labels that carry the flag count; works on runs collected before the detector."""
    text_of = {it["id"]: it for it in items}
    tp = fp = fn = tn = 0
    misses = []
    for row in labels:
        if row.get("bad_extraction") is None:
            continue
        it = text_of[row["id"]]
        flagged = not extraction_quality.assess(it.get("title") or "", it.get("text") or "").ok
        actual = bool(row["bad_extraction"])
        tp, fp = tp + (flagged and actual), fp + (flagged and not actual)
        fn, tn = fn + (actual and not flagged), tn + (not flagged and not actual)
        if flagged != actual:
            misses.append({"id": row["id"], "labeled_bad": actual, "detected_junk": flagged})
    return {"n": tp + fp + fn + tn, "tn": tn, **_pr(tp, fp, fn), "misses": misses}


def label_basis(label: dict) -> str:
    """What the labeler read before labeling: "full" or "partial"; older labels have no basis -> "unknown"."""
    basis = label.get("basis")
    return basis if basis in ("full", "partial") else "unknown"


def label_score(label: dict) -> int:
    """The label's importance; noise is 1 on the D14 rubric."""
    return 1 if label["noise"] else int(label["score"])


def rebuild_item(label: dict, runs_dir: Path, run_cache: dict[str, dict[str, dict]]) -> tuple[dict, bool]:
    """The item exactly as production saw it, from its run file; the label's snapshot (text cut to 2000 chars)
    only when the run file or the item is gone. Returns (item, used_snapshot)."""
    run_id = label.get("run_id") or ""
    if run_id not in run_cache:
        path = runs_dir / f"{run_id}.jsonl"
        safe = run_id and "/" not in run_id and "\\" not in run_id
        run_cache[run_id] = {r.get("id"): r for r in read_jsonl(path)} if safe else {}
    original = run_cache[run_id].get(label["id"])
    if original is not None:  # legacy competitor keys (aws_codeartifact) map to the current one on read
        return {**ci_config.canonical_item(original), "id": label["id"]}, False
    item = {**ci_config.canonical_item(label.get("item") or {}), "id": label["id"], "run_id": run_id}
    item["text_status"] = "snippet" if len(item.get("text") or "") < SNIPPET_MAX_CHARS else "full"
    return item, True


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def _confusions(pairs: list[tuple[str, str]]) -> list[dict]:
    off = Counter((a, b) for a, b in pairs if a != b)
    return [{"label": a, "pred": b, "n": n} for (a, b), n in off.most_common(CONFUSIONS_SHOWN)]


def evaluate(labels: list[dict], classifications: list[Classification], ranked: list[Ranked]) -> dict:
    """Metrics of predictions against labels (pure; ranked is in the ranker's order)."""
    cls = {c.id: c for c in classifications}
    final = {r.id: r for r in ranked}

    # competitor is scored on relevant items; on noise the tag hardly matters, so it is reported apart
    comp_pairs = [(row["competitor"], cls[row["id"]].competitor) for row in labels if not row["noise"]]
    noise_comp = [row["competitor"] == cls[row["id"]].competitor for row in labels if row["noise"]]
    per_comp = {}
    for key in sorted({a for a, _ in comp_pairs}):
        hits = [a == b for a, b in comp_pairs if a == key]
        per_comp[key] = {"n": len(hits), "correct": sum(hits), "accuracy": _ratio(sum(hits), len(hits))}

    cat_rows = [row for row in labels if not row["noise"] and row.get("category")]
    cat_pairs = [(row["category"], cls[row["id"]].category or "(none)") for row in cat_rows]
    cat_correct = sum(a == b for a, b in cat_pairs)

    tp = sum(row["noise"] and cls[row["id"]].noise for row in labels)
    fp = sum(not row["noise"] and cls[row["id"]].noise for row in labels)
    fn = sum(row["noise"] and not cls[row["id"]].noise for row in labels)
    tn = len(labels) - tp - fp - fn
    j_tp = sum(bool(row.get("mentions_jfrog")) and cls[row["id"]].mentions_jfrog for row in labels)
    j_fp = sum(not row.get("mentions_jfrog") and cls[row["id"]].mentions_jfrog for row in labels)
    j_fn = sum(bool(row.get("mentions_jfrog")) and not cls[row["id"]].mentions_jfrog for row in labels)

    # degraded items (no score: the ranker failed) are missing, counted apart, never scored as anything
    scored = [row for row in labels if final[row["id"]].score is not None]
    diffs = [abs(final[row["id"]].score - label_score(row)) for row in scored]
    # "important": predicted final score >= IMPORTANT_MIN vs labeled score >= IMPORTANT_MIN (noise counts as 1),
    # over the scored items; this replaces P@k, which needs a full daily run to mean anything
    i_tp = sum(final[row["id"]].score >= IMPORTANT_MIN and label_score(row) >= IMPORTANT_MIN for row in scored)
    i_fp = sum(final[row["id"]].score >= IMPORTANT_MIN and label_score(row) < IMPORTANT_MIN for row in scored)
    i_fn = sum(final[row["id"]].score < IMPORTANT_MIN and label_score(row) >= IMPORTANT_MIN for row in scored)

    # accuracy split by who settled the item: competitor and category on non-noise labels, noise on all
    by_method = {}
    for method in ("rules", "llm", "fallback"):
        rows = [row for row in labels if cls[row["id"]].method == method]
        relevant = [row for row in rows if not row["noise"]]
        comp_ok = sum(row["competitor"] == cls[row["id"]].competitor for row in relevant)
        cat_m = [row for row in relevant if row.get("category")]
        cat_ok = sum(row["category"] == cls[row["id"]].category for row in cat_m)
        noise_ok = sum(row["noise"] == cls[row["id"]].noise for row in rows)
        by_method[method] = {
            "n": len(rows),
            "competitor": {"n": len(relevant), "correct": comp_ok, "accuracy": _ratio(comp_ok, len(relevant))},
            "category": {"n": len(cat_m), "correct": cat_ok, "accuracy": _ratio(cat_ok, len(cat_m))},
            "noise": {"n": len(rows), "correct": noise_ok, "accuracy": _ratio(noise_ok, len(rows))},
        }

    def errors_for(rows: list[dict]) -> dict:
        relevant = [row for row in rows if not row["noise"]]
        cat_rows = [row for row in relevant if row.get("category")]
        rows_scored = [r for r in rows if final[r["id"]].score is not None]
        def err(n: int, errors: int) -> dict:
            return {"n": n, "errors": errors, "error_rate": _ratio(errors, n)}

        off2 = sum(abs(final[row["id"]].score - label_score(row)) > 1 for row in rows_scored)
        return {
            "n": len(rows),
            "competitor": err(len(relevant), sum(row["competitor"] != cls[row["id"]].competitor for row in relevant)),
            "category": err(len(cat_rows), sum(row["category"] != cls[row["id"]].category for row in cat_rows)),
            "noise": err(len(rows), sum(row["noise"] != cls[row["id"]].noise for row in rows)),
            "score": {**err(len(rows_scored), sum(final[row["id"]].score != label_score(row) for row in rows_scored)),
                      "off_by_2_plus": off2, "off_by_2_plus_rate": _ratio(off2, len(rows_scored)),
                      "missing": len(rows) - len(rows_scored)},
        }

    # errors by what the labeler read before labeling (labels without basis predate the field)
    by_basis = {b: errors_for([row for row in labels if label_basis(row) == b]) for b in BASES}
    # errors by whether the labeler saw junk instead of the article (labels without the flag predate it)
    by_bad = {b: errors_for([row for row in labels if label_bad_extraction(row) == b]) for b in BAD_EXTRACTION}

    return {
        "n": len(labels),
        "by_basis": by_basis,
        "by_bad_extraction": by_bad,
        "competitor": {"correct": sum(a == b for a, b in comp_pairs), "n": len(comp_pairs),
                       "accuracy": _ratio(sum(a == b for a, b in comp_pairs), len(comp_pairs)),
                       "per_competitor": per_comp,
                       "on_noise": {"n": len(noise_comp), "correct": sum(noise_comp),
                                    "accuracy": _ratio(sum(noise_comp), len(noise_comp))}},
        "category": {"correct": cat_correct, "n": len(cat_pairs), "accuracy": _ratio(cat_correct, len(cat_pairs))},
        "noise": _pr(tp, fp, fn) | {"tn": tn},
        "mentions_jfrog": _pr(j_tp, j_fp, j_fn),
        "score": {"n": len(diffs), "exact": _ratio(sum(d == 0 for d in diffs), len(diffs)),
                  "within_1": _ratio(sum(d <= 1 for d in diffs), len(diffs)), "missing": len(labels) - len(scored)},
        "important": {"min": IMPORTANT_MIN, "n": len(scored), "missing": len(labels) - len(scored),
                      **_pr(i_tp, i_fp, i_fn)},
        "by_method": by_method,
        "confusion": {"competitor": _confusions(comp_pairs), "category": _confusions(cat_pairs),
                      "noise": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}},
    }


def _pr(tp: int, fp: int, fn: int) -> dict:
    """Precision and recall, each with the n it is computed over."""
    return {"tp": tp, "fp": fp, "fn": fn, "precision": _ratio(tp, tp + fp), "precision_n": tp + fp,
            "recall": _ratio(tp, tp + fn), "recall_n": tp + fn}


def precision_at_k(labels: list[dict], ranked: list[Ranked], k_values=K_VALUES) -> dict:
    """Share of labeled-important items in the ranker's top k. Kept for full daily-run reports; the golden-set eval
    does not show it (its items are a sample, not a day's ranking)."""
    lab = {row["id"]: row for row in labels}
    out = {}
    for k in k_values:
        top = [r.id for r in ranked if r.id in lab and r.score is not None][:k]
        hits = sum(label_score(lab[i]) >= IMPORTANT_MIN for i in top)
        out[str(k)] = {"k": len(top), "hits": hits, "precision": _ratio(hits, len(top)), "n": len(top)}
    return out


def abstaining_llm() -> JsonLLM:
    """The offline stand-in: answers every call with no items, so classifier and ranker fall back (rules baseline)."""
    return FakeLLM(lambda prompt, schema: {"items": []})


_DEFAULT = Path("<default>")  # sentinel: resolve the module-level path at call time (so tests can patch it)


def run(split: str = "train", live: bool = False, labels_path: Path | None = None, runs_dir: Path | None = None,
        out_dir: Path | None = _DEFAULT, llm: JsonLLM | None = None, cfg: ci_config.CIConfig | None = None,
        allow_fallback: bool = False, embed_fn: Callable[[], EmbedFn] | None = None,
        embed_cache: Path | None = _DEFAULT, split_path: Path | None = _DEFAULT) -> dict:
    """Run the eval and return the report; write it under out_dir unless out_dir is None or nothing was labeled.

    A live run in which any classifier or ranker batch fell back is aborted (report["aborted"], nothing written):
    its numbers would silently mix the rules baseline into the LLM's. allow_fallback overrides, for debugging.
    """
    labels_path = labels_path or LABELS_PATH
    runs_dir = runs_dir or RUNS_DIR
    out_dir = EVALS_OUT_DIR if out_dir is _DEFAULT else out_dir
    embed_cache = EMBED_CACHE_PATH if embed_cache is _DEFAULT else embed_cache
    split_path = SPLIT_ASSIGNMENTS_PATH if split_path is _DEFAULT else split_path
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    all_labels = list(latest_labels(labels_path).values())
    side_hashes = {r: h for r in sorted({row.get("run_id") or "" for row in all_labels})
                   if (h := side_mentions.side_hash(runs_dir, r))}
    run_cache: dict[str, dict[str, dict]] = {}
    rebuilt = {row["id"]: rebuild_item(row, runs_dir, run_cache) for row in all_labels}
    keys = story_keys([item for item, _ in rebuilt.values()], runs_dir, embed_fn=embed_fn, cache_path=embed_cache)
    side, conflicts = assign_sides(keys, split_path)
    labels = [row for row in all_labels if split == "all" or side[row["id"]] == split]
    items = side_mentions.attach([rebuilt[row["id"]][0] for row in labels], runs_dir)
    if llm is None:
        llm = GeminiLLM() if live else abstaining_llm()
    report = {"created_at": datetime.now(UTC).isoformat(), "split": split, "live": live,
              "fingerprint": fingerprint(cfg, side_hashes), "mention_side_files": side_hashes,
              "model": getattr(llm, "model", "fake (abstains)"), "labels_total": len(all_labels),
              "split_counts": dict(Counter(side.values())), "split_conflicts": conflicts,
              "stories": len(set(keys.values())), "n": len(labels),
              "full_page_mentions": sum(bool(it.get("mentions")) for it in items),
              "snapshot_text_used": sum(rebuilt[row["id"]][1] for row in labels),
              "metrics": None, "items": [], "path": None,
              "fallbacks": {"classify": 0, "rank": 0}, "aborted": False}
    if not labels:
        return report
    started = time.monotonic()
    classifications = Classifier(llm, cfg, runs_dir=runs_dir).classify(items)
    ranked = Ranker(llm).rank(items, classifications)
    report["seconds"] = round(time.monotonic() - started, 1)
    report["fallbacks"] = {"classify": sum(c.method == "fallback" for c in classifications),
                           "rank": sum(r.degraded for r in ranked)}
    if live and any(report["fallbacks"].values()) and not allow_fallback:
        report["aborted"] = True
        _log_test_run(report, out_dir)
        return report
    report["metrics"] = evaluate(labels, classifications, ranked)
    report["metrics"]["extraction_detector"] = detector_vs_flags(labels, items)
    cls, fin = {c.id: c for c in classifications}, {r.id: r for r in ranked}
    for row, item in zip(labels, items, strict=True):
        report["items"].append({
            "id": row["id"], "story": keys[row["id"]], "title": item.get("title"),
            "text_status": item.get("text_status"), "snapshot_text": rebuilt[row["id"]][1],
            "label": {k: row.get(k) for k in ("competitor", "category", "noise", "score", "mentions_jfrog")},
            "pred": {**cls[row["id"]].model_dump(exclude={"id"}),
                     **fin[row["id"]].model_dump(include=RANKED_FIELDS)}})
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        report["path"] = str(path)
    _log_test_run(report, out_dir)
    return report


def _log_test_run(report: dict, out_dir: Path | None) -> None:
    """Append a --split test run to the test log (timestamp, fingerprint, headline metrics)."""
    if report["split"] != "test" or out_dir is None:
        return
    m = report["metrics"] or {}
    pick = {"competitor": ("competitor", "accuracy"), "category": ("category", "accuracy"),
            "noise_precision": ("noise", "precision"), "noise_recall": ("noise", "recall"),
            "score_exact": ("score", "exact"), "score_within_1": ("score", "within_1")}
    entry = {"at": report["created_at"], "fingerprint": report["fingerprint"], "live": report["live"],
             "model": report["model"], "n": report["n"], "aborted": report["aborted"],
             "metrics": {name: (m.get(a) or {}).get(b) for name, (a, b) in pick.items()}}
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / TEST_LOG_NAME).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    report["test_log"] = str(out_dir / TEST_LOG_NAME)


def _rate(value: float | None, n: int) -> str:
    """A rate with the n it is computed over: "0.67 (n=12)", or "n/a (n=0)" when there is nothing to divide."""
    return f"n/a (n={n})" if value is None or not n else f"{value:.2f} (n={n})"


def fallback_warning(report: dict) -> str | None:
    fb = report["fallbacks"]
    if not report["live"] or not any(fb.values()):
        return None
    what = "ABORTED, nothing written" if report["aborted"] else "scored anyway (--allow-fallback)"
    return (f"!!! WARNING: the LLM answer was unusable for {fb['classify']} classifier and {fb['rank']} ranker items;"
            f" they fell back to rules / the midpoint score. {what}. !!!")


def format_report(report: dict) -> str:
    head = (f"Golden-set eval · split={report['split']} · {'LIVE ' + report['model'] if report['live'] else 'offline'}"
            f" · prompts+rules {report['fingerprint']}"
            f" · {report['n']} items (labels total {report['labels_total']} in {report.get('stories', 0)} stories,"
            f" {report['split_counts']})")
    warning = fallback_warning(report)
    if report["aborted"]:
        return f"{head}\n{warning}"
    if warning:
        head = f"{warning}\n{head}"
    m = report["metrics"]
    if m is None:
        return head + "\nNo labeled items in this split yet; nothing to score."
    lines = [head]
    if report.get("split_conflicts"):
        ids = sorted({i for c in report["split_conflicts"] for i in c["ids"]})
        lines.append(f"  SPLIT CONFLICT: {len(report['split_conflicts'])} story groups span both sides after a merge"
                     f" (sides kept as persisted): {', '.join(ids)}")
    if report.get("full_page_mentions") is not None:
        lines.append(f"  full-page mention counts on {report['full_page_mentions']}/{report['n']} items")
    if report.get("snapshot_text_used"):
        lines.append(f"  note: {report['snapshot_text_used']} items had no run file; classified on the 2000-char"
                     " label snapshot, not production text")
    lines.append("")
    row = "  {:<28} {:>14}  {}"
    comp, cat, nz, jf, sc, imp = (m[k] for k in ("competitor", "category", "noise", "mentions_jfrog", "score",
                                                 "important"))
    lines.append(row.format("Competitor accuracy", _rate(comp["accuracy"], comp["n"]), "non-noise"))
    for key, v in comp["per_competitor"].items():
        lines.append(row.format(f"  {key}", _rate(v["accuracy"], v["n"]), ""))
    on_noise = comp["on_noise"]
    lines.append(row.format("  (on noise items)", _rate(on_noise["accuracy"], on_noise["n"]), ""))
    lines.append(row.format("Category accuracy", _rate(cat["accuracy"], cat["n"]), "non-noise"))
    for name, pr in (("Noise", nz), ("Mentions JFrog", jf), (f"Important (score >= {imp['min']})", imp)):
        lines.append(row.format(f"{name} precision", _rate(pr["precision"], pr["precision_n"]), "predicted"))
        lines.append(row.format(f"{name} recall", _rate(pr["recall"], pr["recall_n"]), "labeled"))
    lines.append(row.format("Score exact", _rate(sc["exact"], sc["n"]), f"{sc['missing']} unscored (degraded)"))
    lines.append(row.format("Score within ±1", _rate(sc["within_1"], sc["n"]), ""))
    lines.append("\n  Settled by        items       competitor          category             noise")
    for method, v in m["by_method"].items():
        cells = [f"{_rate(v[k]['accuracy'], v[k]['n']):>16}" for k in ("competitor", "category", "noise")]
        lines.append(f"  {method:<16} {v['n']:>6}  " + "  ".join(cells))
    for title, key in (("label basis", "by_basis"), ("bad extraction", "by_bad_extraction")):
        lines.append(f"\n  Error rate by {title:<14} items       competitor          category             noise"
                     "             score    off by 2+")
        for group, v in m[key].items():
            if not v["n"]:
                continue
            cells = [f"{_rate(v[k]['error_rate'], v[k]['n']):>16}" for k in ("competitor", "category", "noise",
                                                                              "score")]
            cells.append(f"{_rate(v['score']['off_by_2_plus_rate'], v['score']['n']):>16}")
            lines.append(f"  {group:<27} {v['n']:>6}  " + "  ".join(cells))
    det = m.get("extraction_detector")
    if det and det["n"]:
        lines.append("\n  Junk detector vs Bad extraction flags: "
                     f"precision {_rate(det['precision'], det['precision_n'])}, "
                     f"recall {_rate(det['recall'], det['recall_n'])} (flagged labels n={det['n']})")
    for name in ("competitor", "category"):
        conf = m["confusion"][name]
        if conf:
            lines.append(f"\n  {name} confusions (label -> predicted):")
            lines.extend(f"    {c['n']:>3}  {c['label']} -> {c['pred']}" for c in conf)
    if report.get("path"):
        lines.append(f"\nWrote {report['path']}")
    if report.get("test_log"):
        lines.append(f"Logged this test run (fingerprint {report['fingerprint']}) to {report['test_log']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=SPLITS, default="train",
                        help="train (default, for tuning), test (held out: run only on a frozen fingerprint, "
                             "every run is logged), or all")
    parser.add_argument("--live", action="store_true", help="call Gemini (needs GOOGLE_API_KEY)")
    parser.add_argument("--allow-fallback", action="store_true",
                        help="score a live run even if some LLM batches failed (debugging only)")
    args = parser.parse_args(argv)
    report = run(split=args.split, live=args.live, allow_fallback=args.allow_fallback)
    print(format_report(report))
    return 2 if report["aborted"] else 0


if __name__ == "__main__":
    sys.exit(main())
