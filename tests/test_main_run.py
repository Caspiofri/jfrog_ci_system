"""Each run of the old funnel gets its own UUID thread_id, is logged with it, and is saved as run_<thread_id>.json."""
import asyncio
import json
import uuid
from datetime import date
from unittest.mock import patch

import main
from modules.models import Article


def _result():
    art = Article(subject="s", name="Picked", published_at=date(2026, 10, 30), content="c",
                  url="https://x.example/1", origin="hackernews")
    return {"email_status": "success", "articles": [art], "top_articles": [art],
            "run_stats": {"merged": 1, "picked": 1}, "rank_scores": [{"title": "Picked", "score": 8}],
            "source_errors": [{"source": "vendor", "stage": "collect", "error": "RuntimeError: x"}]}


def _run_twice(tmp_path):
    seen = []

    async def fake_ainvoke(state, config):
        seen.append(config["configurable"]["thread_id"])
        return _result()

    with patch.object(main.graph, "ainvoke", side_effect=fake_ainvoke), \
            patch.object(main.article_store, "purge_old", return_value=0), \
            patch.object(main.tracing, "judge_and_post"), \
            patch.object(main.settings, "OUTPUT_DIR", tmp_path):
        statuses = [asyncio.run(main.run()), asyncio.run(main.run())]
    return statuses, seen


def test_every_run_gets_its_own_uuid_thread_id(tmp_path, capsys):
    statuses, seen = _run_twice(tmp_path)
    assert statuses == ["success", "success"]
    assert len(set(seen)) == 2
    assert all(str(uuid.UUID(t)) == t for t in seen)
    out = capsys.readouterr().out
    assert all(f"Run {t} started" in out for t in seen)


def test_the_run_is_saved_under_its_thread_id(tmp_path):
    _, seen = _run_twice(tmp_path)
    for thread_id in seen:
        record = json.loads((tmp_path / f"run_{thread_id}.json").read_text(encoding="utf-8"))
        assert record["thread_id"] == thread_id
        assert record["status"] == "success"
        assert record["run_stats"] == {"merged": 1, "picked": 1}
        assert record["picked"] == [{"title": "Picked", "url": "https://x.example/1", "origin": "hackernews"}]
        assert record["ranked"] == [{"title": "Picked", "score": 8}]
        assert record["source_errors"][0]["source"] == "vendor"


def _main_with(result, tmp_path):
    """Run main.main() once with the graph returning `result`; returns (saved record, healthcheck pings)."""
    pings = []

    async def fake_ainvoke(state, config):
        return result

    with patch.object(main.graph, "ainvoke", side_effect=fake_ainvoke), \
            patch.object(main.article_store, "purge_old", return_value=0), \
            patch.object(main.tracing, "judge_and_post"), \
            patch.object(main.settings, "OUTPUT_DIR", tmp_path), \
            patch.object(main, "_ping_healthcheck", side_effect=lambda ok, message="": pings.append(ok)):
        asyncio.run(main.main())
    record = json.loads(next(tmp_path.glob("run_*.json")).read_text(encoding="utf-8"))
    return record, pings


def test_a_run_where_every_collector_failed_is_failed_not_healthy(tmp_path):
    errors = [{"source": "hackernews", "stage": "collect", "error": "RuntimeError: down"}]
    result = {"email_status": "no_content", "articles": [], "top_articles": [], "run_stats": {},
              "rank_scores": [], "source_errors": errors}
    record, pings = _main_with(result, tmp_path)
    assert record["status"] == "failed" and pings == [False]


def test_a_run_where_every_source_failed_the_shortlist_is_failed(tmp_path):
    art = _result()["articles"][0]
    errors = [{"source": "hackernews", "stage": "shortlist", "error": "RuntimeError: 503"}]
    result = {"email_status": "no_content", "articles": [art], "top_articles": [], "run_stats": {},
              "rank_scores": [], "source_errors": errors}
    record, pings = _main_with(result, tmp_path)
    assert record["status"] == "failed" and pings == [False]


def test_a_run_with_a_working_source_stays_healthy(tmp_path):
    record, pings = _main_with(_result(), tmp_path)  # one collector failed, hackernews delivered
    assert record["status"] == "success" and pings == [True]


def test_missing_credentials_crash_the_run_and_ping_failure(tmp_path):
    pings = []

    async def no_key(state, config):
        raise main.nodes.llm_clients.MissingCredentials("GOOGLE_API_KEY is not set")

    with patch.object(main.graph, "ainvoke", side_effect=no_key), \
            patch.object(main.article_store, "purge_old", return_value=0), \
            patch.object(main, "_ping_healthcheck", side_effect=lambda ok, message="": pings.append(ok)):
        asyncio.run(main.main())
    assert pings == [False]
