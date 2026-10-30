"""Labeling page API: serves a run's packets and appends Ofri's labels to the golden set (PRD D11, D14). No LLM."""
import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from ci import config
from ci.labeling import stratified
from ci.packet import NON_COMPETITOR
from config.settings import EVALS_DIR, OUTPUT_DIR

RUNS_DIR = OUTPUT_DIR / "runs"
LABELS_PATH = EVALS_DIR / "golden_set.jsonl"  # append-only; not evals/golden_set.json, which is an older file
PAGE_PATH = Path(__file__).with_name("page.html")

# D11 categories, stored verbatim in the label
CATEGORIES = [
    "Product & Features",
    "Pricing & Packaging",
    "AI & Agents",
    "Security",
    "Funding/M&A/Partnerships",
    "Customers & Market",
    "Leadership & Org",
]
SNAPSHOT_TEXT_CHARS = 2000
log = logging.getLogger(__name__)


class LabelIn(BaseModel):
    id: str
    run_id: str
    competitor: str
    category: str | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    noise: bool = False
    mentions_jfrog: bool = False
    basis: Literal["full", "partial"]  # did Ofri read the full article, or only part of it, before labeling
    note: str = ""

    @model_validator(mode="after")
    def _check(self):
        if self.category is not None and self.category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        # noise means "not relevant at all", so category and score are optional only then
        if not self.noise and (self.category is None or self.score is None):
            raise ValueError("a non-noise label needs a category and a score")
        if self.noise:  # noise carries no category or score, whatever the client sent
            self.category = self.score = None
        return self


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("skipping malformed line %d in %s", n, path)
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def latest_labels(path: Path) -> dict[str, dict]:
    """Item id -> its latest label; later lines win."""
    rows = (r for r in read_jsonl(path) if isinstance(r.get("id"), str) and isinstance(r.get("noise"), bool))
    return {row["id"]: {"basis": None, **row} for row in rows}  # lines from before `basis` read back as None


def read_mentions(path: Path) -> dict[str, dict[str, int]]:
    """Item id -> {competitor: count} from a <run_id>.mentions.json side file, if there is a readable one.
    Accepts {id: {competitor: n}} or {id: {"mentions": {competitor: n}, ...}}."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for item_id, value in data.items() if isinstance(data, dict) else []:
        counts = value.get("mentions", value) if isinstance(value, dict) else None
        if isinstance(counts, dict):
            out[item_id] = {k: v for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)}
    return out


def snapshot(item: dict) -> dict:
    keys = ("title", "url", "source", "origin", "publisher", "published_at")
    snap = {k: item.get(k) for k in keys}
    snap["text"] = (item.get("text") or "")[:SNAPSHOT_TEXT_CHARS]
    snap["competitor"] = item.get("competitor")
    return snap


def create_app(runs_dir: Path = RUNS_DIR, labels_path: Path = LABELS_PATH,
               competitors: list[str] | None = None, default_run: str | None = None,
               cfg: config.CIConfig | None = None) -> FastAPI:
    if cfg is None:  # tests may pass only competitor keys; the queue's name rules then use the keys as names
        cfg = config.load() if competitors is None else config.CIConfig(competitors=[
            config.Competitor(key=k, name=k.replace("_", " ").title()) for k in competitors])
    if competitors is None:
        competitors = [c.key for c in cfg.competitors]
    competitors = [*competitors, NON_COMPETITOR]  # always offered, so an off-target story can be relabeled
    app = FastAPI(title="JFrog CI labeling")
    write_lock = threading.Lock()  # one append at a time (FastAPI runs sync handlers in a thread pool)
    queue_lock = threading.Lock()  # one queue build per run, even when two tabs open it at once

    def run_ids() -> list[str]:
        """Newest first (by file mtime). Only <run_id>.jsonl: skips side files such as <run_id>.dropped.jsonl."""
        files = [p for p in runs_dir.glob("*.jsonl") if "." not in p.stem and not p.name.startswith(".")]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return [p.stem for p in files]

    def run_status(run_id: str) -> str:
        """"failed" when the run's report says so, "empty" when it kept no items, else "ok"."""
        try:
            report = json.loads((runs_dir / f"{run_id}.report.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
        if isinstance(report, dict) and report.get("status") == "failed":
            return "failed"
        with (runs_dir / f"{run_id}.jsonl").open(encoding="utf-8") as f:
            return "ok" if any(line.strip() for line in f) else "empty"

    def load_run(run_id: str) -> list[dict]:
        if run_id not in run_ids():  # also guards against path tricks in run_id
            raise HTTPException(404, f"unknown run {run_id}")
        return read_jsonl(runs_dir / f"{run_id}.jsonl")

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE_PATH.read_text(encoding="utf-8")

    @app.get("/api/meta")
    def meta() -> dict:
        runs = run_ids()
        status = {r: run_status(r) for r in runs}
        usable = [r for r in runs if status[r] == "ok"]  # a failed or empty run is listed but never the default
        if default_run in runs:
            default = default_run  # asked for by name with --run
        else:
            default = usable[0] if usable else (runs[0] if runs else None)
        return {"runs": runs, "run_status": status, "default_run": default, "competitors": competitors,
                "categories": CATEGORIES}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [{"run_id": r, "items": len(read_jsonl(runs_dir / f"{r}.jsonl")), "status": run_status(r)}
                for r in run_ids()]

    @app.get("/api/runs/{run_id}/items")
    def items(run_id: str) -> list[dict]:
        labels = latest_labels(labels_path)
        side = read_mentions(runs_dir / f"{run_id}.mentions.json")
        return [{**item, "mentions": item.get("mentions") or side.get(item.get("id")),
                 "label": labels.get(item.get("id"))} for item in load_run(run_id)]

    def queue_for(run_id: str, rebuild: bool) -> dict:
        run_items = load_run(run_id)
        labels = latest_labels(labels_path)
        with queue_lock:
            q = stratified.load_or_build(runs_dir, run_id, run_items, set(labels), cfg, rebuild=rebuild)
        return stratified.with_progress(q, labels, stratified.rules_hash(cfg))

    @app.get("/api/runs/{run_id}/queue")
    def queue(run_id: str) -> dict:
        """The stratified labeling queue (built once, then reused) with labeled/target per bucket."""
        return queue_for(run_id, rebuild=False)

    @app.post("/api/runs/{run_id}/queue/rebuild")
    def rebuild_queue(run_id: str) -> dict:
        """Replace the stored queue with one built from the current rules (labeled items are kept first)."""
        return queue_for(run_id, rebuild=True)

    @app.get("/api/stats")
    def stats() -> dict:
        """Totals over the whole golden set, across runs."""
        labels = latest_labels(labels_path).values()
        per_cat = {c: 0 for c in CATEGORIES}
        for lab in labels:
            if not lab["noise"] and lab.get("category") in per_cat:
                per_cat[lab["category"]] += 1
        noise = sum(1 for lab in labels if lab["noise"])
        per_basis = {"full": 0, "partial": 0, "unknown": 0}
        for lab in labels:
            per_basis[lab["basis"] if lab["basis"] in per_basis else "unknown"] += 1
        return {"labeled": len(labels), "noise": noise, "relevant": len(labels) - noise, "per_category": per_cat,
                "per_basis": per_basis}

    @app.post("/api/labels")
    def save_label(label: LabelIn) -> dict:
        if label.competitor not in competitors:
            raise HTTPException(422, f"unknown competitor {label.competitor}")
        item = next((it for it in load_run(label.run_id) if it.get("id") == label.id), None)
        if item is None:
            raise HTTPException(404, f"item {label.id} not in run {label.run_id}")
        row = {**label.model_dump(), "labeled_at": datetime.now(UTC).isoformat(), "item": snapshot(item)}
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with write_lock:
            labels_path.parent.mkdir(parents=True, exist_ok=True)
            with labels_path.open("ab+") as f:
                # never glue a line onto an unterminated last line (e.g. after a crash mid-write)
                if f.tell() > 0:
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        line = "\n" + line
                f.write(line.encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
        return row

    return app
