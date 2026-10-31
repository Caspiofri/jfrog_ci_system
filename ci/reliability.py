"""Reliability check of a daily run (PRD D41): every held item plus a fixed-seed sample of auto-published items, for
Ofri to mark competitor, category and score right or wrong. The answers live in the review file (output/reviews/),
never in the golden set.

    python -m ci.reliability make [--run RUN_ID] [--sample 20] [--seed 20261101]   (default: today's daily run)
    python -m ci.reliability score output/reviews/reliability_<run_id>.yaml

make never overwrites a review file that already exists (answers may be in it). score counts right / wrong per field
and group with n and writes <file>.results.json next to it.
"""
import argparse
import json
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

from ci import config as ci_config
from ci.api import service as svc
from ci.store import STORE_PATH, Store
from config.settings import OUTPUT_DIR

REVIEW_DIR = OUTPUT_DIR / "reviews"
SAMPLE, SEED = 20, 20261101
FIELDS = ("competitor", "category", "score")
ANSWERS = ("right", "wrong")
HEADER = """# Reliability check of daily run {run_id} (D41). For every item, set each of competitor / category /
#   score to right or wrong (leave null if you can't judge it), and add `note:` if useful. Nothing else needs editing.
# held: every item held for review at level {level} ({held} items). auto: {sample} of the {auto} auto-published items,
#   drawn with seed {seed} (fixed, so the sample can be redrawn exactly). Answers stay in this file, not in the golden
#   set. Count them with: python -m ci.reliability score {path}
"""


def pick_run(s: svc.Snapshot, run_id: str | None, today: str) -> dict:
    runs = sorted((r for r in s.runs if r["kind"] == "daily"), key=lambda r: r["started_at"])
    if run_id:
        found = next((r for r in s.runs if r["run_id"] == run_id), None)
        if found is None:
            raise SystemExit(f"no run {run_id} in the store")
        return found
    todays = [r for r in runs if svc.israel_date(svc.parse_ts(r["started_at"])) == today]
    if not todays:
        raise SystemExit(f"no daily run on {today} in the store (did the 06:00 run fail? see output/logs/ci_daily.log)")
    return todays[0]


def entry(s: svc.Snapshot, item_id: str, group: str) -> dict:
    it = s.item(item_id)
    row = {"id": item_id, "group": group, "title": it["title"], "url": it["url"], "source": it["source"],
           "publisher": it["publisher"],
           "shown": {"competitor": it["competitor"], "category": it["category"], "score": it["score"]},
           "answer": dict.fromkeys(FIELDS)}
    if group == "held":
        row["held_for"] = [h["code"] for h in it["hold_reasons"] if s.level in h["held_at"]]
    return row


def make(run_id: str | None = None, sample: int = SAMPLE, seed: int = SEED, store_path: Path = STORE_PATH,
         out_dir: Path = REVIEW_DIR, now: datetime | None = None) -> Path:
    today = svc.israel_date(now or datetime.now(UTC))
    with Store(store_path) as store:
        s = svc.Snapshot.read(store, ci_config.load())
        run = pick_run(s, run_id, today)
        mine = sorted(i for i, o in s.outputs.items() if o["run_id"] == run["run_id"])
        held = [i for i in mine if s.status(i) == "awaiting_review"]
        auto = [i for i in mine if s.status(i) == "auto_published"]
        drawn = sorted(random.Random(seed).sample(auto, min(sample, len(auto))))
        items = [entry(s, i, "held") for i in held] + [entry(s, i, "auto") for i in drawn]
    path = out_dir / f"reliability_{run['run_id']}.yaml"
    if path.exists():
        raise SystemExit(f"{path} exists; not overwritten (it may hold answers)")
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {"run_id": run["run_id"], "level": s.level, "seed": seed, "auto_published_total": len(auto),
            "items": items}
    path.write_text(HEADER.format(run_id=run["run_id"], level=s.level, held=len(held), sample=len(drawn),
                                  auto=len(auto), seed=seed, path=path) +
                    yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return path


def score(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = {"run_id": data["run_id"], "level": data["level"], "seed": data["seed"], "groups": {}}
    for group in ("held", "auto", "all"):
        rows = [x for x in data["items"] if group == "all" or x["group"] == group]
        g = {"items": len(rows)}
        for f in FIELDS:
            c = Counter((x.get("answer") or {}).get(f) for x in rows)
            bad = sorted(set(c) - set(ANSWERS) - {None})
            if bad:
                raise SystemExit(f"{path}: {f} answers must be right, wrong or null, found {bad}")
            judged = c["right"] + c["wrong"]
            g[f] = {"right": c["right"], "wrong": c["wrong"], "n": judged, "unanswered": c[None],
                    "accuracy": round(c["right"] / judged, 3) if judged else None}
        out["groups"][group] = g
    out["wrong_items"] = [{"id": x["id"], "group": x["group"], "title": x["title"],
                           "wrong": [f for f in FIELDS if (x.get("answer") or {}).get(f) == "wrong"],
                           "note": x.get("note")} for x in data["items"]
                          if any((x.get("answer") or {}).get(f) == "wrong" for f in FIELDS)]
    path.with_suffix(".results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.reliability", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--run")
    m.add_argument("--sample", type=int, default=SAMPLE)
    m.add_argument("--seed", type=int, default=SEED)
    sc = sub.add_parser("score")
    sc.add_argument("path", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "make":
        print(f"wrote {make(args.run, args.sample, args.seed)}")
    else:
        res = score(args.path)
        for group, g in res["groups"].items():
            print(f"{group:4} items {g['items']:>3}: " + "; ".join(
                f"{f} {g[f]['right']} of {g[f]['n']} right" + (f" ({g[f]['unanswered']} unanswered)"
                                                                if g[f]["unanswered"] else "") for f in FIELDS))
        print(f"wrote {args.path.with_suffix('.results.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
