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
    api_main.main(["--port", "8011"])
    assert seen == {"host": "127.0.0.1", "port": 8011}
    try:
        api_main.main(["--host", "0.0.0.0"])
    except SystemExit:
        pass  # there is no --host option
    else:
        raise AssertionError("--host must not be accepted")
