"""The served app (python -m ci.api) can refresh insights: it is built with a model and an embedding function."""
from ci.api import __main__ as api_main


def test_the_served_app_gets_an_insights_model_and_embeddings(monkeypatch):
    seen = {}
    monkeypatch.setattr(api_main, "create_app", lambda **kw: seen.update(kw) or "app")
    monkeypatch.setattr("ci.dedupe.default_embedding_fn", lambda: "embed")
    assert api_main.build_app() == "app"
    assert seen["insights_llm"] is not None and seen["embed_fn"] == "embed"


def test_the_api_listens_on_loopback_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(api_main, "build_app", lambda: "app")
    monkeypatch.setattr(api_main.uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr(api_main, "log_config", lambda: "cfg")
    api_main.main(["--port", "8011"])
    assert seen == {"host": "127.0.0.1", "port": 8011, "log_config": "cfg"}
    try:
        api_main.main(["--host", "0.0.0.0"])
    except SystemExit:
        pass  # there is no --host option
    else:
        raise AssertionError("--host must not be accepted")


def test_the_api_log_is_appended_to_a_file(tmp_path):
    """D48: the API log was lost on reboot; it now also goes to output/logs/ci_api.log."""
    import logging
    import logging.config

    path = tmp_path / "logs" / "ci_api.log"
    cfg = api_main.log_config(path)
    assert api_main.LOG_PATH.name == "ci_api.log" and api_main.LOG_PATH.parent.name == "logs"
    try:
        logging.config.dictConfig(cfg)
        logging.getLogger("ci.api.app").warning("hello from the app")
        logging.getLogger("uvicorn.error").info("hello from uvicorn")
    finally:
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers.clear()
        for name in ("uvicorn", "uvicorn.access"):
            for h in logging.getLogger(name).handlers:
                h.close()
            logging.getLogger(name).handlers.clear()
    text = path.read_text()
    assert "hello from the app" in text and "hello from uvicorn" in text
