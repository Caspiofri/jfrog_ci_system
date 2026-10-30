"""Gemini client factory (API key by default, Vertex AI opt-in) and the model names read from env."""
import importlib
from unittest.mock import patch

import pytest
from google import genai

from config import settings
from modules import llm_clients

AUTH_VARS = ("GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
MODEL_VARS = ("GEMINI_MODEL", "JUDGE_MODEL_DAILY", "JUDGE_MODEL_EVAL")


@pytest.fixture
def clean_env(monkeypatch):
    for name in AUTH_VARS:
        monkeypatch.delenv(name, raising=False)
    llm_clients.gemini_client.cache_clear()
    yield monkeypatch
    llm_clients.gemini_client.cache_clear()


def _built_with():
    """kwargs genai.Client was called with under the current env, minus http_options (checked on its own)."""
    with patch.object(genai, "Client") as client:
        llm_clients.gemini_client()
    client.assert_called_once()
    kwargs = dict(client.call_args.kwargs)
    assert kwargs.pop("http_options").timeout == 60_000  # ms, on every route
    return kwargs


def test_default_route_is_the_api_key(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "k-123")
    assert _built_with() == {"vertexai": False, "api_key": "k-123"}


def test_api_key_route_without_a_key_fails_clearly(clean_env):
    with pytest.raises(llm_clients.MissingCredentials, match="GOOGLE_API_KEY"):
        llm_clients.gemini_client()


def test_vertex_is_opt_in(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "k-123")  # ignored once Vertex is chosen
    clean_env.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    assert _built_with() == {"vertexai": True, "project": "proj-1", "location": "us-central1"}


def test_vertex_location_from_env(clean_env):
    clean_env.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "proj-1")
    clean_env.setenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
    assert _built_with()["location"] == "europe-west4"


def test_vertex_without_project_fails_clearly(clean_env):
    clean_env.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    with pytest.raises(llm_clients.MissingCredentials, match="GOOGLE_CLOUD_PROJECT"):
        llm_clients.gemini_client()


def test_vertex_flag_false_keeps_the_api_key_route(clean_env):
    clean_env.setenv("GOOGLE_GENAI_USE_VERTEXAI", "false")
    clean_env.setenv("GOOGLE_API_KEY", "k-123")
    assert _built_with()["vertexai"] is False


def test_client_is_built_once(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "k-123")
    with patch.object(genai, "Client") as client:
        assert llm_clients.gemini_client() is llm_clients.gemini_client()
    client.assert_called_once()


def test_real_api_key_client_builds_offline(clean_env):
    clean_env.setenv("GOOGLE_API_KEY", "dummy-key-for-offline-test")
    assert hasattr(llm_clients.gemini_client(), "models")


@pytest.fixture
def reload_settings(monkeypatch):
    """Re-read config.settings with .env loading off, then restore it as the rest of the suite saw it."""
    yield monkeypatch
    monkeypatch.undo()
    importlib.reload(settings)


def _reload():
    with patch("dotenv.load_dotenv", return_value=False):
        return importlib.reload(settings)


def test_model_defaults(reload_settings):
    for name in MODEL_VARS:
        reload_settings.delenv(name, raising=False)
    s = _reload()
    assert (s.GEMINI_MODEL, s.JUDGE_MODEL_DAILY, s.JUDGE_MODEL_EVAL) == (
        "gemini-3.6-flash", "claude-haiku-4-5", "claude-sonnet-5-5")


def test_models_from_env(reload_settings):
    reload_settings.setenv("GEMINI_MODEL", "gemini-x")
    reload_settings.setenv("JUDGE_MODEL_DAILY", "judge-d")
    reload_settings.setenv("JUDGE_MODEL_EVAL", "judge-e")
    s = _reload()
    assert (s.GEMINI_MODEL, s.JUDGE_MODEL_DAILY, s.JUDGE_MODEL_EVAL) == ("gemini-x", "judge-d", "judge-e")
