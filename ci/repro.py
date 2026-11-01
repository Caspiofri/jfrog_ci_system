"""Reproducibility pack (D59): recompute every reported number from files in the repo, with no LLM call.

    python -m ci.repro build --out repro      build the pack from the golden set, the split and the saved reports
    python -m ci.repro check repro            no keys, no article text, no train/test leakage
    python -m ci.repro recompute repro        every reported metric with its n, recomputed and compared

Two different things, kept apart:
- **recompute** (this module): deterministic. It reads the predictions and labels a saved eval report holds and
  runs the eval's own metric code (ci.eval_golden.evaluate) on them, and recounts the coverage report's events. No
  model is called, so the output is the same every time and equals the reported numbers.
- **rerun the evaluation** (python -m ci.eval_run --live): calls Gemini on the labeled articles. It needs the
  article text, which the pack never holds, and the model's output may vary between runs.

The pack: labels.jsonl (each label's values with the item's URL, title and the sha256 of the text it was labeled
on; no article text, no notes), split_assignments.json (as frozen), reports/evals/*.json (the train eval reports) and
reports/coverage/*.json (without the local paths they were run with), plus manifest.json with each file's sha256.
Label values are copied, never changed.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from ci import eval_golden
from ci.classify import Classification
from ci.coverage import COVERAGE_DIR
from ci.rank import Ranked

LABEL_FIELDS = ("competitor", "category", "score", "noise", "mentions_jfrog", "basis", "bad_extraction", "standard",
                "labeled_at")
ITEM_FIELDS = ("url", "title", "publisher", "source", "published_at")
REPORT_NAME = re.compile(r"\d{8}T\d{6}Z\.json")
SECRET_RE = re.compile(r"AIza[0-9A-Za-z_\-]{30,}|(?<![\w-])sk-(?:proj-|ant-)?[A-Za-z0-9_]{20,}|lsv2_[A-Za-z0-9_]{20,}|"
                       r"(?:API_KEY|SECRET|TOKEN)\s*[=:]\s*\S{8,}")
MAX_STRING_CHARS = 600  # longer than any title, reason or quote; an article body is far longer
LOCAL_PATH_KEYS = ("events_file", "runs_dir")  # where the report was run on this machine: dropped from the pack
LOCAL_PATH_RE = re.compile(r"(?:^|[\s\"'=:(])(?:/home/|/Users/|/tmp/|/root/|[A-Za-z]:\\)")
HEADLINE = (("competitor_accuracy", "competitor", "accuracy", "n"), ("category_accuracy", "category", "accuracy", "n"),
            ("noise_precision", "noise", "precision", "precision_n"), ("noise_recall", "noise", "recall", "recall_n"),
            ("important_precision", "important", "precision", "precision_n"),
            ("important_recall", "important", "recall", "recall_n"),
            ("score_exact", "score", "exact", "n"), ("score_within_1", "score", "within_1", "n"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack_label(label: dict, side: str | None) -> dict:
    item = label.get("item") or {}
    return {"id": label["id"], "run_id": label.get("run_id"), "split": side,
            **{k: item.get(k) for k in ITEM_FIELDS},
            "text_sha256": _sha((item.get("text") or "").encode("utf-8")),
            "label": {k: label.get(k) for k in LABEL_FIELDS}}


def build(out: Path, labels_path: Path = eval_golden.LABELS_PATH,
          split_path: Path = eval_golden.SPLIT_ASSIGNMENTS_PATH, evals_dir: Path = eval_golden.EVALS_OUT_DIR,
          coverage_dir: Path = COVERAGE_DIR, reports: list[str] | None = None) -> dict:
    """Write the pack; reports: eval report names to include (default: every live train report)."""
    sides = eval_golden.load_assignments(split_path)
    labels = eval_golden.latest_labels(labels_path)
    (out / "reports" / "evals").mkdir(parents=True, exist_ok=True)
    (out / "reports" / "coverage").mkdir(parents=True, exist_ok=True)
    with (out / "labels.jsonl").open("w", encoding="utf-8") as f:
        for i in sorted(labels):
            f.write(json.dumps(pack_label(labels[i], sides.get(i)), ensure_ascii=False) + "\n")
    shutil.copyfile(split_path, out / "split_assignments.json")
    chosen = []
    for p in sorted(evals_dir.glob("*.json")):
        if not REPORT_NAME.fullmatch(p.name):
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if (reports is None and r.get("live") and r.get("split") == "train" and r.get("metrics")) or \
                (reports is not None and p.name in reports):
            shutil.copyfile(p, out / "reports" / "evals" / p.name)
            chosen.append(p.name)
    for p in sorted(coverage_dir.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        for k in LOCAL_PATH_KEYS:
            r.pop(k, None)
        (out / "reports" / "coverage" / p.name).write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n",
                                                          encoding="utf-8")
    files = sorted(x for x in out.rglob("*") if x.is_file() and x.name != "manifest.json")
    manifest = {"labels": len(labels), "split_counts": dict(Counter(sides.values())), "eval_reports": chosen,
                "coverage_reports": sorted(p.name for p in (out / "reports" / "coverage").glob("*.json")),
                "files": {x.relative_to(out).as_posix(): _sha(x.read_bytes()) for x in files}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _strings(value, path=""):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for n, v in enumerate(value):
            yield from _strings(v, f"{path}[{n}]")


def check(pack: Path) -> list[str]:
    """Problems found (an empty list = clean): secrets, long text, local file paths, labels in a report on the wrong
    split side."""
    problems = []
    sides = json.loads((pack / "split_assignments.json").read_text(encoding="utf-8"))["sides"]
    docs = [(p, [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()])
            for p in [pack / "labels.jsonl"]]
    docs += [(p, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((pack / "reports").rglob("*.json"))]
    for path, doc in docs:
        rel = path.relative_to(pack).as_posix()
        for where, s in _strings(doc):
            if SECRET_RE.search(s):
                problems.append(f"{rel}{where}: looks like a key")
            if len(s) > MAX_STRING_CHARS:
                problems.append(f"{rel}{where}: {len(s)} characters (article text?)")
            if LOCAL_PATH_RE.search(s):
                problems.append(f"{rel}{where}: a local file path")
            if where.endswith((".text", ".snapshot")) and len(s) > 0:
                problems.append(f"{rel}{where}: an item text field")
    for p in sorted((pack / "reports" / "evals").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        wrong = [it["id"] for it in r.get("items", []) if r.get("split") in ("train", "test")
                 and sides.get(it["id"]) != r["split"]]
        if wrong:
            problems.append(f"reports/evals/{p.name}: {len(wrong)} items not on its split side ({r.get('split')})")
    for row in docs[0][1]:
        if row.get("split") != sides.get(row["id"]):
            problems.append(f"labels.jsonl {row['id']}: split {row.get('split')} != the split file")
    return problems


def recompute_eval(report: dict) -> dict:
    """The eval's own metrics on the labels and predictions the report holds."""
    labels, cls, ranked = [], [], []
    for it in report["items"]:
        lab, pred = it["label"], it["pred"]
        labels.append({"id": it["id"], **lab})
        cls.append(Classification(id=it["id"], **{k: pred[k] for k in Classification.model_fields if k in pred
                                                  and k != "id"}))
        ranked.append(Ranked(id=it["id"], **{k: pred[k] for k in Ranked.model_fields if k in pred and k != "id"}))
    return eval_golden.evaluate(labels, cls, ranked)


def headline(metrics: dict) -> dict:
    return {name: {"value": (metrics.get(sec) or {}).get(key), "n": (metrics.get(sec) or {}).get(nk)}
            for name, sec, key, nk in HEADLINE}


def recompute_coverage(report: dict) -> dict:
    events = [e for e in report["events"] if e.get("in_window", True)]

    def count(rows):
        return {"captured": sum(bool(e["captured"]) for e in rows), "n": len(rows)}

    high = report.get("high_importance", {}).get("min", 4)
    return {"overall": count(events),
            "high_importance": count([e for e in events if (e.get("expected_importance") or 0) >= high]),
            **{f"competitor.{c}": count([e for e in events if e["competitor"] == c])
               for c in sorted({e["competitor"] for e in events})},
            **{f"source_kind.{k}": count([e for e in events if e.get("source_kind") == k])
               for k in sorted({e["source_kind"] for e in events if "source_kind" in e})}}


def reported_coverage(report: dict) -> dict:
    out = {"overall": {"captured": report["overall"]["captured"], "n": report["overall"]["events"]},
           "high_importance": {"captured": report["high_importance"]["captured"],
                               "n": report["high_importance"]["events"]}}
    out |= {f"competitor.{c}": {"captured": v["captured"], "n": v["events"]}
            for c, v in report.get("by_competitor", {}).items()}
    out |= {f"source_kind.{k}": {"captured": v["captured"], "n": v["events"]}
            for k, v in report.get("by_source_kind", {}).items()}
    return out


def recompute(pack: Path) -> dict:
    """{report: {metric: {value, n, reported, reported_n, same}}} for every eval and coverage report in the pack."""
    out = {}
    for p in sorted((pack / "reports" / "evals").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        got, rep = headline(recompute_eval(r)), headline(r["metrics"])
        out[f"evals/{p.name}"] = {"split": r["split"], "fingerprint": r["fingerprint"], "n": r["n"], "metrics": {
            k: {**got[k], "reported": rep[k]["value"], "reported_n": rep[k]["n"], "same": got[k] == rep[k]}
            for k in got}}
    for p in sorted((pack / "reports" / "coverage").glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        got, rep = recompute_coverage(r), reported_coverage(r)
        out[f"coverage/{p.name}"] = {"run_id": r.get("run_id"), "metrics": {
            k: {**got[k], "reported": rep.get(k, {}).get("captured"), "reported_n": rep.get(k, {}).get("n"),
                "same": got[k] == rep.get(k)} for k in got}}
    return out


def _fmt(v) -> str:
    return "-" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ci.repro", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, required=True)
    for name in ("check", "recompute"):
        sub.add_parser(name).add_argument("pack", type=Path)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        m = build(args.out)
        problems = check(args.out)
        print(f"wrote {args.out}: {m['labels']} labels, eval reports {m['eval_reports']}, coverage "
              f"{m['coverage_reports']}; check: {'clean' if not problems else problems}")
        return 1 if problems else 0
    if args.cmd == "check":
        problems = check(args.pack)
        print("clean" if not problems else "\n".join(problems))
        return 1 if problems else 0
    res = recompute(args.pack)
    differ = 0
    for name, r in res.items():
        print(f"\n{name}" + (f"  split={r['split']} n={r['n']} fingerprint={r['fingerprint']}" if "split" in r else ""))
        for k, v in r["metrics"].items():
            val = v.get("value", v.get("captured"))
            differ += not v["same"]
            print(f"  {k:<28} {_fmt(val):>6}  n={_fmt(v['n']):<4} reported {_fmt(v['reported']):>6} "
                  f"n={_fmt(v['reported_n']):<4} {'same' if v['same'] else 'DIFFERENT'}")
    print(f"\n{sum(len(r['metrics']) for r in res.values())} numbers recomputed, {differ} different")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
