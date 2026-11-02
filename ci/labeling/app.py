"""Labeling page API: serves a run's packets and writes Ofri's labels to the golden set (PRD D11, D14). No LLM."""
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from ci import config, reliability
from ci import rank as rank_mod
from ci.csrf import CSRFMiddleware, TrustedHostMiddleware, trusted_hosts
from ci.labeling import audit, relabel, reliability_page, stratified
from ci.packet import NON_COMPETITOR
from ci.store import STORE_PATH
from config.settings import EVALS_DIR, OUTPUT_DIR
from modules.reader import FULL_TEXT_MIN_CHARS

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
# the previous label's values kept on a relabel (with revision_reason saying why it changed)
REVISED_FIELDS = ("competitor", "category", "score", "noise", "mentions_jfrog", "bad_extraction", "basis", "labeled_at")
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
    # the shown text was not the article (boilerplate, nav, another page); category/score/competitor still describe
    # the real article. Old labels without it read back as None.
    bad_extraction: bool | None = None  # None = not answered: stored as False, except where the queue requires it
    note: str = ""
    # why a relabel changed the label (optional); a relabel also stores the previous values under revised_from
    revision_reason: str = Field(default="", max_length=300)

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


def _is_label(row) -> bool:
    return isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("noise"), bool)


def upsert_label(path: Path, row: dict) -> None:
    """Write the label so the file holds one line per id: an existing label for the id is replaced in place (else
    the line is appended), and any older duplicate ids are dropped, keeping the latest. Lines that are not labels
    (malformed JSON, anything else) are kept verbatim. The file is replaced atomically: a temp file in the same
    directory, fsync, os.replace, so a crash leaves either the old file or the new one, never a torn one."""
    # split on "\n" only: splitlines() also breaks on U+2028/U+2029/NEL, which scraped text carries unescaped
    lines = path.read_text(encoding="utf-8").split("\n") if path.exists() else []
    parsed = []
    for line in lines:
        try:
            parsed.append(json.loads(line) if line.strip() else None)
        except json.JSONDecodeError:
            parsed.append(None)
    last = {}  # id -> index of its latest line
    for i, obj in enumerate(parsed):
        if _is_label(obj):
            last[obj["id"]] = i
    new_line = json.dumps(row, ensure_ascii=False)
    out = []
    for i, (line, obj) in enumerate(zip(lines, parsed, strict=True)):
        if _is_label(obj):
            if last[obj["id"]] != i:
                continue  # an older duplicate
            out.append(new_line if obj["id"] == row["id"] else line)
        elif line.strip():
            out.append(line)  # malformed or not a label: preserved as it was
    if row["id"] not in last:
        out.append(new_line)
    _replace_atomically(path, "".join(f"{line}\n" for line in out))


def _replace_atomically(path: Path, text: str) -> None:
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
    try:  # make the rename itself durable
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def rubric_meanings(path: Path | None = None) -> dict[str, str]:
    """{"5".."1", "noise": one line} from the score table of config/rubric_v2.md (the ranker's own rubric), so the
    labeling page's tooltips can never drift from what the model is told. Industry meanings are appended."""
    text = (path or rank_mod.RUBRIC_PATH).read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() not in {"5", "4", "3", "2", "1", "noise"}:
            continue
        meaning = cells[1]
        if cells[2] and cells[2] not in ("—", "-", "same"):
            meaning += f" · Industry: {cells[2]}"
        out[cells[0].lower()] = meaning
    return out


def blind(item: dict) -> dict:
    """The item without the automatic extraction verdict: a "junk" status shows as full/partial by length, and the
    detector's reasons are dropped. Ofri's Bad extraction flags measure that detector, so they must not see it."""
    item = {k: v for k, v in item.items() if k != "extraction_reasons"}
    if item.get("text_status") == "junk":
        item["text_status"] = "full" if len(item.get("text") or "") >= FULL_TEXT_MIN_CHARS else "partial"
    return item


def latest_labels(path: Path) -> dict[str, dict]:
    """Item id -> its latest label; later lines win."""
    rows = (r for r in read_jsonl(path) if isinstance(r.get("id"), str) and isinstance(r.get("noise"), bool))
    # lines from before `basis` / `bad_extraction` existed read back as None
    # legacy competitor keys (aws_codeartifact) read back as the current key; the file itself is never rewritten
    return {row["id"]: {"basis": None, "bad_extraction": None, **config.canonical_item(row)} for row in rows}


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
            out[item_id] = config.canonical_counts(
                {k: v for k, v in counts.items() if isinstance(v, int) and not isinstance(v, bool)})
    return out


def snapshot(item: dict) -> dict:
    keys = ("title", "url", "source", "origin", "publisher", "published_at")
    snap = {k: item.get(k) for k in keys}
    snap["text"] = (item.get("text") or "")[:SNAPSHOT_TEXT_CHARS]
    snap["competitor"] = item.get("competitor")
    return snap


def create_app(runs_dir: Path = RUNS_DIR, labels_path: Path = LABELS_PATH,
               competitors: list[str] | None = None, default_run: str | None = None,
               cfg: config.CIConfig | None = None, relabel_dir: Path = relabel.RELABEL_DIR,
               changes_db: Path = relabel.CHANGES_DB, reviews_dir: Path | None = None,
               store_path: Path | None = None, hosts: list[str] | None = None) -> FastAPI:
    if cfg is None:  # tests may pass only competitor keys; the queue's name rules then use the keys as names
        cfg = config.load() if competitors is None else config.CIConfig(competitors=[
            config.Competitor(key=k, name=k.replace("_", " ").title()) for k in competitors])
    if competitors is None:
        competitors = [c.key for c in cfg.competitors]
    competitors = [*competitors, NON_COMPETITOR]  # always offered, so an off-target story can be relabeled
    app = FastAPI(title="JFrog CI labeling")
    app.add_middleware(CSRFMiddleware)  # labels are written without a login; refuse cross-site writes
    app.add_middleware(TrustedHostMiddleware, hosts=trusted_hosts(hosts or []))  # the addresses it listens on
    reliability_page.add_routes(app, reviews_dir or reliability.REVIEW_DIR, store_path or STORE_PATH)
    write_lock = threading.Lock()  # one write at a time (FastAPI runs sync handlers in a thread pool)
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
        return [config.canonical_item(r) for r in read_jsonl(runs_dir / f"{run_id}.jsonl")]

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
        return {"rubric": rubric_meanings(),
                "runs": runs, "run_status": status, "default_run": default, "competitors": competitors,
                "categories": CATEGORIES, "relabel_queues": relabel.list_queues(relabel_dir),
                "issue_names": audit.ISSUES}

    @app.get("/api/runs")
    def list_runs() -> list[dict]:
        return [{"run_id": r, "items": len(read_jsonl(runs_dir / f"{r}.jsonl")), "status": run_status(r)}
                for r in run_ids()]

    @app.get("/api/runs/{run_id}/items")
    def items(run_id: str) -> list[dict]:
        labels = latest_labels(labels_path)
        side = read_mentions(runs_dir / f"{run_id}.mentions.json")
        ctx = audit_ctx()
        return [{**blind(item), "mentions": item.get("mentions") or side.get(item.get("id")),
                 "label": labels.get(item.get("id")), "issues": ctx.issues(labels.get(item.get("id")))}
                for item in load_run(run_id)]

    def audit_ctx() -> audit.Context:
        return audit.Context(runs_dir, relabel_dir)

    @app.get("/api/audit")
    def audit_totals(run_id: str | None = None, relabel_queue: str | None = None) -> dict:
        """Issue counts under the current standard: the whole golden set, or the labels of one run or queue."""
        labels = latest_labels(labels_path)
        if run_id is not None:
            ids = {it.get("id") for it in load_run(run_id)}
        elif relabel_queue is not None:
            q = relabel.load(relabel_dir, relabel_queue)
            if q is None:
                raise HTTPException(404, f"unknown relabel queue {relabel_queue}")
            ids = {e["id"] for e in q["entries"]}
        else:
            ids = set(labels)
        return audit.audit_labels([labels[i] for i in sorted(ids) if i in labels], audit_ctx())

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

    @app.get("/api/relabel/{queue_id}")
    def relabel_queue(queue_id: str) -> dict:
        """A relabel queue's cards in order: each item from its own run (source fields only, no predictions),
        prefilled with the current label, plus JFrog's baseline cell on score-3/4 cards."""
        q = relabel.load(relabel_dir, queue_id)
        if q is None:
            raise HTTPException(404, f"unknown relabel queue {queue_id}")
        labels = latest_labels(labels_path)
        cells = relabel.jfrog_cells(changes_db)
        ctx = audit_ctx()
        runs: dict[str, dict[str, dict]] = {}
        cards = []
        for e in q["entries"]:
            if e["run_id"] not in runs:
                runs[e["run_id"]] = {it.get("id"): it for it in load_run(e["run_id"])}
            item = runs[e["run_id"]].get(e["id"])
            if item is None:
                continue  # the run file lost it; nothing to show
            label = labels.get(e["id"])
            cards.append({**relabel.card_item(blind(item)), "run_id": e["run_id"], "label": label,
                          "done": relabel.is_done(label, q), "jfrog": relabel.jfrog_baseline(label, cells),
                          "issues": ctx.issues(label)})
        return {"queue_id": queue_id, "built_at": q["built_at"], "cutoff": q["cutoff"], "total": len(cards),
                "done": sum(c["done"] for c in cards), "items": cards,
                "audit": audit.summarize([c["issues"] for c in cards if c["label"]])}

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
                "per_basis": per_basis, "bad_extraction": sum(lab.get("bad_extraction") is True for lab in labels)}

    @app.post("/api/labels")
    def save_label(label: LabelIn) -> dict:
        if label.competitor not in competitors:
            raise HTTPException(422, f"unknown competitor {label.competitor}")
        item = next((it for it in load_run(label.run_id) if it.get("id") == label.id), None)
        if item is None:
            raise HTTPException(404, f"item {label.id} not in run {label.run_id}")
        in_relabel = bool(relabel.queues_holding(relabel_dir, label.id))
        topup_required = label.id in stratified.requires_bad_extraction(runs_dir, label.run_id)
        # the relabel and top-up queues both save to the current standard: every field answered, stamped rubric-v2
        strict = in_relabel or topup_required
        if strict:
            missing = [f for f, ok in (("basis", label.basis in ("full", "partial")),
                                       ("bad_extraction", label.bad_extraction is not None),
                                       ("note", bool(label.note.strip()))) if not ok]
            if missing:
                raise HTTPException(422, f"this queue requires {', '.join(missing)}")
        if label.bad_extraction is None:
            if topup_required:
                raise HTTPException(422, "this queue requires an explicit bad_extraction answer (true or false)")
            label.bad_extraction = False
        now = datetime.now(UTC).isoformat()
        row = {**label.model_dump(), "labeled_at": now, "item": snapshot(item)}
        if in_relabel or topup_required:
            row["bad_extraction_explicit"] = True  # a required Yes/No, not the page default
        ctx = audit_ctx()
        with write_lock:  # relabeling replaces the id's line; the file stays one line per id
            previous = latest_labels(labels_path).get(label.id)
            queues = relabel.queues_holding(relabel_dir, label.id) if previous is not None else []
            if queues:  # a relabel-queue item: a change needs a reason, an unchanged save is a confirmation
                unset = {"bad_extraction"} if "bad_extraction_unanswered" in ctx.issues(previous) else set()
                changed = relabel.changed_fields(previous, row, unset)
                if changed and not label.revision_reason.strip():
                    raise HTTPException(422, f"changed {', '.join(changed)}: say why in revision_reason")
                row["relabel"] = {"queue_id": queues[0]["queue_id"], "changed": changed}
            if strict:  # reviewed under the current standard (a confirmation included)
                row["standard"] = audit.STANDARD
                row["reviewed_at"] = now
            if previous is not None:  # a relabel: keep what it was, so the reason has context
                row["revised_from"] = {k: previous.get(k) for k in REVISED_FIELDS}
            upsert_label(labels_path, row)
        return {**row, "issues": ctx.issues(row)}

    return app
