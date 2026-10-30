"""LLM and tracing clients, each built on first use.

Importing any module of the project needs no API key or credentials: a client is only created when a call needs it.
Each accessor caches its client; tests reset one with e.g. `gemini_client.cache_clear()`.

Gemini auth (PRD D4, D5):
- default: the Gemini API with GOOGLE_API_KEY
- opt-in: Vertex AI with GOOGLE_GENAI_USE_VERTEXAI=true, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION (default
  us-central1) and application-default credentials (GOOGLE_APPLICATION_CREDENTIALS, a service-account key file)
The model name is settings.GEMINI_MODEL on both routes.
"""
import os
from functools import cache

import config.settings  # noqa: F401  (loads .env before the variables below are read)

DEFAULT_VERTEX_LOCATION = "us-central1"
GEMINI_TIMEOUT_S = 60  # per request, on both routes; a hung call fails instead of stalling a run


class MissingCredentials(RuntimeError):
    """A client was needed but its key or settings are not configured."""


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes")


def use_vertex() -> bool:
    return _env_true("GOOGLE_GENAI_USE_VERTEXAI")


@cache
def gemini_client():
    """The Gemini client the old funnel (shortlist, ranker, summarizer) and ci.llm call."""
    from google import genai
    from google.genai import types

    http_options = types.HttpOptions(timeout=GEMINI_TIMEOUT_S * 1000)  # milliseconds

    if use_vertex():
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project:
            raise MissingCredentials("GOOGLE_GENAI_USE_VERTEXAI is set but GOOGLE_CLOUD_PROJECT is not")
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or DEFAULT_VERTEX_LOCATION
        return genai.Client(vertexai=True, project=project, location=location, http_options=http_options)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise MissingCredentials("GOOGLE_API_KEY is not set (or set GOOGLE_GENAI_USE_VERTEXAI=true for Vertex AI)")
    return genai.Client(vertexai=False, api_key=api_key, http_options=http_options)


@cache
def anthropic_client():
    """The Claude client the judge calls; reads ANTHROPIC_API_KEY when built."""
    import anthropic

    return anthropic.Anthropic()


@cache
def langsmith_client():
    """The LangSmith client feedback is posted with; reads LANGSMITH_API_KEY when built."""
    import langsmith

    return langsmith.Client()
