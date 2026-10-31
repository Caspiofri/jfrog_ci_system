"""Reliability check of a daily run (PRD D41): every held item plus a fixed-seed sample of auto-published items, for
Ofri to mark competitor, category and score right or wrong. The answers live in the review file (output/reviews/),
never in the golden set.

    python -m ci.reliability make [--run RUN_ID] [--sample 20] [--seed 20261101]   (default: today's daily run)
    python -m ci.reliability score output/reviews/reliability_<run_id>.yaml

The file also lists every item of the run that the noise pre-filter (shadow mode, D25) would have dropped, with
its reason and what the classifier decided, for a `noise: yes | no` answer: the pre-filter's precision on unseen data.

It also lists the Brief's generated insights for that day, one row per claim with its cited sources, for a
`supported: yes | no` answer (is the claim supported by its cited sources?).

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
# prefilter: every item of this run the noise pre-filter (shadow mode, D25: it changes nothing) would have dropped
#   without an LLM call ({flags} items). Set noise: yes (it is noise) or no (it is relevant).
# insights: the Brief's generated insights ({insights_status}), one row per claim ({claims} claims). Open the cited
#   sources and set supported: yes (the cited sources support the claim) or no.
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


def insight_claims(s: svc.Snapshot, stored: dict) -> list[dict]:
    """One row per claim of the stored insights, with every cited source's title and URL."""
    rows = []
    for ins in stored.get("insights", []):
        for n, c in enumerate(ins["claims"], 1):
            rows.append({"insight_id": ins["insight_id"], "claim_no": n, "pattern": ins["pattern"],
                         "insight_title": ins["title"], "claim": c["text"],
                         "cited": [{"id": i, "title": s.items[i]["title"] if i in s.items else "?",
                                    "url": s.items[i]["url"] if i in s.items else None} for i in c["item_ids"]],
                         "quote": c["quote"], "quote_item_id": c["quote_item_id"],
                         "jfrog_quote": c.get("jfrog_quote") or None, "supported": None})
    return rows


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
        flagged = [{"id": i, "title": s.items[i]["title"], "url": s.items[i]["url"],
                    "would_drop_because": s.outputs[i]["classification"]["shadow_prefilter"],
                    "classifier_noise": bool(s.outputs[i]["classification"]["noise"]), "status": s.status(i),
                    "noise": None} for i in mine if s.outputs[i]["classification"].get("shadow_prefilter")]
        brief_date = svc.israel_date(svc.parse_ts(run["started_at"]))
        stored = store.latest_insights(brief_date)
        claims = insight_claims(s, stored) if stored else []
    path = out_dir / f"reliability_{run['run_id']}.yaml"
    if path.exists():
        raise SystemExit(f"{path} exists; not overwritten (it may hold answers)")
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {"run_id": run["run_id"], "level": s.level, "seed": seed, "auto_published_total": len(auto),
            "items": items, "prefilter": flagged,
            "insights_meta": {"brief_date": brief_date, "status": stored["status"] if stored else "none stored",
                              "generated_at": stored.get("generated_at") if stored else None,
                              "trigger": stored.get("trigger") if stored else None,
                              "fingerprint": stored.get("fingerprint") if stored else None},
            "insights": claims}
    path.write_text(HEADER.format(run_id=run["run_id"], level=s.level, held=len(held), sample=len(drawn),
                                  auto=len(auto), seed=seed, path=path, flags=len(flagged),
                                  insights_status=body["insights_meta"]["status"], claims=len(claims)) +
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
    flags = data.get("prefilter") or []
    answers = Counter(x.get("noise") for x in flags)
    bad = sorted(set(answers) - {"yes", "no", None})
    if bad:
        raise SystemExit(f"{path}: prefilter noise answers must be yes, no or null, found {bad}")
    judged = answers["yes"] + answers["no"]
    out["prefilter"] = {"flagged": len(flags), "noise_yes": answers["yes"], "noise_no": answers["no"], "n": judged,
                        "unanswered": answers[None],
                        "precision": round(answers["yes"] / judged, 3) if judged else None,
                        "relevant_flagged": [{"id": x["id"], "title": x["title"]} for x in flags
                                             if x.get("noise") == "no"]}
    rows = data.get("insights") or []
    sup = Counter(x.get("supported") for x in rows)
    bad = sorted(set(sup) - {"yes", "no", None})
    if bad:
        raise SystemExit(f"{path}: insights supported answers must be yes, no or null, found {bad}")
    out["insights"] = {"claims": len(rows), "supported": sup["yes"], "unsupported": sup["no"],
                       "n": sup["yes"] + sup["no"], "unanswered": sup[None],
                       "insights": len({x["insight_id"] for x in rows}),
                       "unsupported_claims": [{"insight_id": x["insight_id"], "claim_no": x["claim_no"],
                                               "claim": x["claim"], "note": x.get("note")}
                                              for x in rows if x.get("supported") == "no"]}
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
        path = make(args.run, args.sample, args.seed)
        flags = len(yaml.safe_load(path.read_text(encoding="utf-8")).get("prefilter") or [])
        claims = len(yaml.safe_load(path.read_text(encoding="utf-8")).get("insights") or [])
        print(f"wrote {path} (pre-filter shadow flags in this run: {flags}; insight claims: {claims})")
    else:
        res = score(args.path)
        for group, g in res["groups"].items():
            print(f"{group:4} items {g['items']:>3}: " + "; ".join(
                f"{f} {g[f]['right']} of {g[f]['n']} right" + (f" ({g[f]['unanswered']} unanswered)"
                                                                if g[f]["unanswered"] else "") for f in FIELDS))
        p = res["prefilter"]
        print(f"prefilter (shadow): flagged {p['flagged']}; noise {p['noise_yes']} of {p['n']} judged"
              + (f", relevant flagged: {[x['id'] for x in p['relevant_flagged']]}" if p["relevant_flagged"] else ""))
        i = res["insights"]
        print(f"insights: {i['supported']} of {i['n']} claims supported ({i['insights']} insights, "
              f"{i['claims']} claims, {i['unanswered']} unanswered)")
        print(f"wrote {args.path.with_suffix('.results.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
