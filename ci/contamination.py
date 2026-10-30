"""Contamination check: items whose text contains another item's title from the same run.

A page extractor that pulls in neighbouring content ("Other logs" carousels, related posts) leaves other stories'
titles inside an item's text. The run report counts such items per source and lists the worst offenders.

    python -m ci.contamination <run_id> [--runs-dir DIR]     (read-only over an existing run)
"""
import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from config.settings import OUTPUT_DIR

MIN_TITLE_WORDS = 4  # shorter titles ("cli v1.30.1", "Changelog") occur in ordinary text and give false hits
WORST_SHOWN = 5
RUNS_DIR = OUTPUT_DIR / "runs"


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", (text or "").lower()).split())


KEY_WORDS = 3  # probes are indexed by their first three normalized words; each text is scanned once


def _chains(rows: Iterable[dict]) -> dict[str, str]:
    """id -> root of its dedupe chain (duplicate_of links, followed transitively)."""
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for row in rows:
        if row.get("id") and row.get("duplicate_of"):
            a, b = root(row["id"]), root(row["duplicate_of"])
            if a != b:
                parent[max(a, b)] = min(a, b)
    return {x: root(x) for x in list(parent)}


def find(items: Iterable[dict], extra_titles: Iterable[dict] = ()) -> dict[str, list[str]]:
    """Item id -> ids of the other items whose normalized title (4+ words as written) appears in its text.

    extra_titles (e.g. the run's dropped items) are probes only, and never replace a kept item with the same id.
    Not counted: items sharing a normalized title, and probes in the item's own dedupe chain (a dropped duplicate
    of this very story). Probes are indexed by their first words, so each text is scanned once: linear in the
    total text, not in items x titles.
    """
    items = [it for it in items if it.get("id")]
    extra = [r for r in extra_titles if r.get("id")]
    titles = {it["id"]: normalize(it.get("title") or "") for it in items}
    chain = _chains([*items, *extra])
    probes: dict[str, list[str]] = {}
    for row in [*items, *extra]:  # kept items first: a dropped row never overwrites one
        words = normalize(row.get("title") or "").split()
        if row["id"] in probes or len((row.get("title") or "").split()) < MIN_TITLE_WORDS or len(words) < KEY_WORDS:
            continue
        probes[row["id"]] = words
    index: dict[tuple[str, ...], list[str]] = {}
    for pid, words in probes.items():
        index.setdefault(tuple(words[:KEY_WORDS]), []).append(pid)
    out: dict[str, list[str]] = {}
    for it in items:
        own, own_chain = titles[it["id"]], chain.get(it["id"], it["id"])
        words = normalize(it.get("text") or "").split()
        hits: list[str] = []
        for i in range(len(words) - KEY_WORDS + 1):
            for pid in index.get(tuple(words[i:i + KEY_WORDS]), ()):
                probe = probes[pid]
                if (pid == it["id"] or pid in hits or " ".join(probe) == own
                        or chain.get(pid, pid) == own_chain or words[i:i + len(probe)] != probe):
                    continue
                hits.append(pid)
        if hits:
            out[it["id"]] = hits
    return out


def by_source(items: list[dict], extra_titles: Iterable[dict] = ()) -> dict[str, dict]:
    """Per source: how many items are contaminated, and the worst offenders (most foreign titles first)."""
    hits = find(items, extra_titles)
    source_of = {it["id"]: it.get("source") or "" for it in items if it.get("id")}
    out: dict[str, dict] = {}
    for item_id, others in hits.items():
        row = out.setdefault(source_of[item_id], {"contaminated": 0, "worst": []})
        row["contaminated"] += 1
        row["worst"].append((item_id, len(others)))
    for row in out.values():
        row["worst"] = [i for i, _ in sorted(row["worst"], key=lambda x: (-x[1], x[0]))[:WORST_SHOWN]]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run_id")
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    args = parser.parse_args(argv)
    path = args.runs_dir / f"{args.run_id}.jsonl"
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dropped_path = args.runs_dir / f"{args.run_id}.dropped.jsonl"
    dropped = ([json.loads(line) for line in dropped_path.read_text(encoding="utf-8").splitlines() if line.strip()]
               if dropped_path.exists() else [])
    hits = find(items, dropped)
    titles = {it["id"]: it.get("title") for it in [*dropped, *items]}
    print(f"{args.run_id}: {len(hits)} of {len(items)} items contain another item's title")
    for source, row in sorted(by_source(items, dropped).items()):
        print(f"  {source}: {row['contaminated']}")
    for item_id, others in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print(f"  {item_id} {titles[item_id]!r} contains: " + "; ".join(repr(titles[o]) for o in others))
    return 0


if __name__ == "__main__":
    sys.exit(main())
