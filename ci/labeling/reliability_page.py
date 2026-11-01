"""The reliability review page (D41) on the labeling server: every field of a review file's items, marked right or
wrong with a note. Each mark is saved on the server when it is clicked (output/reviews/reliability_<run>.marks.json);
competitor, category and score marks also go to the review file's answers, so `python -m ci.reliability score` counts
them. The page shows what the system stored and never suggests an answer."""
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ci import reliability
from ci.store import STORE_PATH

PAGE_PATH = Path(__file__).with_name("reliability_page.html")


class MarkIn(BaseModel):
    item_id: str
    field: str
    mark: str | None = None  # right | wrong | None (not marked)
    note: str = Field(default="", max_length=reliability.NOTE_MAX_CHARS)


def add_routes(app: FastAPI, reviews_dir: Path = reliability.REVIEW_DIR, store_path: Path = STORE_PATH) -> None:
    lock = threading.Lock()  # one write at a time: the marks file and the review file are rewritten whole

    def path_of(run_id: str) -> Path:
        if run_id not in reliability.review_runs(reviews_dir):  # also guards against path tricks in run_id
            raise HTTPException(404, f"no review file for run {run_id}")
        return reliability.review_path(run_id, reviews_dir)

    @app.get("/reliability", response_class=HTMLResponse)
    def reliability_page() -> str:
        return PAGE_PATH.read_text(encoding="utf-8")

    @app.get("/api/reliability")
    def reliability_runs() -> dict:
        return {"runs": reliability.review_runs(reviews_dir), "marks": list(reliability.MARKS)}

    @app.get("/api/reliability/{run_id}")
    def reliability_sheet(run_id: str) -> dict:
        path = path_of(run_id)
        return {**reliability.sheet(run_id, reviews_dir, store_path), "marks": reliability.load_marks(path)}

    @app.put("/api/reliability/{run_id}/marks")
    def reliability_mark(run_id: str, m: MarkIn) -> dict:
        path = path_of(run_id)
        with lock:
            try:
                return reliability.save_mark(path, m.item_id, m.field, m.mark, m.note)
            except ValueError as e:
                raise HTTPException(422, str(e)) from e

    @app.get("/api/reliability/{run_id}/export")
    def reliability_export(run_id: str) -> dict:
        path = path_of(run_id)
        marks = reliability.load_marks(path)
        rows = [{"item_id": x["id"], "group": x["group"], "field": f,
                 **{k: (marks.get(x["id"], {}).get(f) or {}).get(k) for k in ("mark", "note", "at")}}
                for x in reliability.sheet(run_id, reviews_dir, store_path)["items"] for f in reliability.FIELD_KEYS]
        return {"run_id": run_id, "marks": rows}
