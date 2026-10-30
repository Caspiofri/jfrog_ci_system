import asyncio
import json
import os
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path

import requests
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from config import settings  # also loads .env
from modules import article_store, nodes, tracing
from modules.graph import graph

GRAPH_TIMEOUT = 600
HEALTHCHECK_PING_URL = os.getenv("HEALTHCHECK_PING_URL")


def _ping_healthcheck(ok: bool, message: str = ""):
    if not HEALTHCHECK_PING_URL:
        return
    url = HEALTHCHECK_PING_URL if ok else f"{HEALTHCHECK_PING_URL}/fail"
    try:
        requests.post(url, data=message.encode("utf-8")[:10000], timeout=10)
    except requests.RequestException as e:
        print(f"[warn] Failed to ping healthcheck: {e}")


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else list(default)


def initial_state() -> dict:
    return {
        **settings.reader_profile(),
        "digest_name": settings.STORE_PROFILE,
        "top_k": int(os.getenv("TOP_K") or settings.DEFAULT_TOP_K),
        "hn_queries": _env_list("HN_QUERIES", settings.DEFAULT_HN_QUERIES),
        "articles": [],
        "candidates": [],
        "extra_articles": [],
        "top_articles": [],
        "run_stats": {},
        "dedupe_drops": [],
        "rank_scores": [],
        "source_errors": [],
        "newsletter_data": None,
        "email_status": "",
    }


def new_thread_id() -> str:
    """A fresh id per run, so runs never share LangGraph checkpointer state and each can be found again."""
    return str(uuid.uuid4())


def save_run(thread_id: str, started_at: str, result: dict, output_dir: Path | None = None) -> Path:
    """Write the run's ranked items, stats and source failures to output/run_<thread_id>.json."""
    out = (output_dir or settings.OUTPUT_DIR) / f"run_{thread_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "thread_id": thread_id,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": result.get("email_status", ""),
        "run_stats": result.get("run_stats", {}),
        "source_errors": result.get("source_errors", []),
        "picked": [{"title": a.name, "url": a.url, "origin": a.origin} for a in result.get("top_articles", [])],
        "ranked": result.get("rank_scores", []),
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


@traceable(name="digest_run")
async def run(thread_id: str | None = None) -> str:
    thread_id = thread_id or new_thread_id()
    started_at = datetime.now(UTC).isoformat(timespec="seconds")
    print(f"Run {thread_id} started at {started_at}")
    state = initial_state()
    rt = get_current_run_tree()  # None when LANGSMITH_TRACING is off
    if rt is not None:
        try:
            rt.add_tags(["digest_run"])
            rt.add_metadata({"thread_id": thread_id})
        except Exception as e:
            print(f"[warn] Failed to tag LangSmith run: {e}")
    purged = article_store.purge_old(settings.STORE_PROFILE)
    if purged:
        print(f"Purged {purged} article(s) older than {article_store.RETENTION_DAYS} days.")

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}}),
            timeout=GRAPH_TIMEOUT,
        )
    except TimeoutError:
        print(f"\nRun {thread_id}: graph timed out after {GRAPH_TIMEOUT}s.")
        return "timeout"

    if nodes.every_source_failed(result):
        result = {**result, "email_status": "failed"}
    print(f"\nRun {thread_id} status: {result['email_status']}")
    print(f"Articles after dedupe: {len(result['articles'])}")
    print(f"Top articles: {[a.name for a in result['top_articles']]}")
    for err in result.get("source_errors", []):
        print(f"Source failed ({err['stage']}): {err['source']}: {err['error']}")
    print(f"Run {thread_id} saved to {save_run(thread_id, started_at, result)}")

    tracing.judge_and_post(result, settings.STORE_PROFILE, rt)
    return result["email_status"]


async def main():
    try:
        status = await run()
    except Exception:
        print(f"\nRun crashed:\n{traceback.format_exc()}")
        _ping_healthcheck(ok=False, message=f"crashed:\n{traceback.format_exc()}")
        return
    if status in ("failed", "timeout"):
        _ping_healthcheck(ok=False, message=f"status={status}")
    else:
        _ping_healthcheck(ok=True)


if __name__ == "__main__":
    asyncio.run(main())
