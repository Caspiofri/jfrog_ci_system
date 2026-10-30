"""The LLM seam: one method, prompt in, JSON object out. Gemini in production, FakeLLM in tests.

Nothing here touches the network or the environment at import time; the Gemini client is built on the first call,
by the shared factory in modules/llm_clients.py (API key by default, Vertex AI opt-in, 60s request timeout).
"""
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable
from typing import Any, Protocol

log = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"  # build design doc, Oct 30 midday decision; override with GEMINI_MODEL
MAX_ATTEMPTS = 3  # one call plus two retries, on 429 and 5xx only
BACKOFF_S = 2.0  # doubled per retry, plus up to JITTER of itself so parallel callers spread out
JITTER = 0.5
MAX_RETRY_AFTER_S = 60.0  # a server-requested wait longer than this is capped
RETRYABLE = frozenset({408, 429})  # plus every 5xx


class LLMError(RuntimeError):
    """The model could not be reached, or its answer was not a JSON object."""


class JsonLLM(Protocol):
    def complete(self, prompt: str, schema: dict) -> dict:
        """Answer the prompt with a JSON object that follows the JSON schema."""
        ...


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL


def make_gemini_client():
    """The Gemini client from modules.llm_clients (imported here, so importing this module loads no .env)."""
    from modules import llm_clients

    try:
        return llm_clients.gemini_client()
    except llm_clients.MissingCredentials as e:
        raise LLMError(f"{e} (env or .env)") from e


def _retryable(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code in RETRYABLE or code >= 500
    return type(exc).__name__ in {"TimeoutException", "ReadTimeout", "ConnectTimeout", "ConnectError"}


def retry_after(exc: Exception) -> float | None:
    """Seconds the server asked us to wait: the Retry-After header, or Gemini's RetryInfo.retryDelay ("17s")."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = headers.get("retry-after") if headers is not None else None
        if value is not None:
            return min(MAX_RETRY_AFTER_S, max(0.0, float(value)))
    except (TypeError, ValueError, AttributeError):
        pass
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else None
    for d in (error or {}).get("details", []) if isinstance(error, dict) else []:
        delay = d.get("retryDelay") if isinstance(d, dict) else None
        m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(delay or ""))
        if m:
            return min(MAX_RETRY_AFTER_S, float(m.group(1)))
    return None


def parse_json_object(text: str | None) -> dict:
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError as e:
        raise LLMError(f"answer is not JSON: {(text or '')[:200]!r}") from e
    if not isinstance(data, dict):
        raise LLMError(f"answer is not a JSON object: {type(data).__name__}")
    return data


class GeminiLLM:
    """Gemini with structured JSON output. The client is created lazily on the first complete()."""

    def __init__(self, model: str | None = None, client_factory: Callable[[], Any] = make_gemini_client,
                 max_attempts: int = MAX_ATTEMPTS, sleep: Callable[[float], None] = time.sleep,
                 rng: random.Random | None = None):
        self.model = model or model_name()
        self._factory = client_factory
        self._client = None
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._rng = rng or random.Random()

    def _get_client(self):
        if self._client is None:
            self._client = self._factory()
        return self._client

    def complete(self, prompt: str, schema: dict) -> dict:
        client = self._get_client()
        config = {"response_mime_type": "application/json", "response_json_schema": schema, "temperature": 0.0}
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = client.models.generate_content(model=self.model, contents=prompt, config=config)
                return parse_json_object(response.text)
            except LLMError:
                raise
            except Exception as e:
                if attempt == self._max_attempts or not _retryable(e):
                    raise LLMError(f"{self.model} call failed: {e}") from e
                asked = retry_after(e)
                if asked is not None:  # honour the server, no jitter needed on top
                    wait = asked
                else:
                    base = BACKOFF_S * 2 ** (attempt - 1)
                    wait = base + self._rng.uniform(0, JITTER * base)
                log.warning("%s: %s, retry %d in %.1fs", self.model, e, attempt, wait)
                self._sleep(wait)
        raise AssertionError("unreachable")


Answer = dict | Exception | Callable[[str, dict], dict]


class FakeLLM:
    """Scripted answers for tests. Each answer is a dict, an exception to raise, or a function of (prompt, schema).

    With a single callable it answers every call; with a list it answers in order and fails when the script runs out.
    Every call is recorded in .calls as (prompt, schema).
    """

    def __init__(self, answers: list[Answer] | Callable[[str, dict], dict] | None = None):
        self._always = answers if callable(answers) else None
        self._script = [] if callable(answers) or answers is None else list(answers)
        self.calls: list[tuple[str, dict]] = []

    def complete(self, prompt: str, schema: dict) -> dict:
        self.calls.append((prompt, schema))
        if self._always is not None:
            answer = self._always
        elif self._script:
            answer = self._script.pop(0)
        else:
            raise LLMError("FakeLLM: no scripted answer left")
        if isinstance(answer, Exception):
            raise answer
        return answer(prompt, schema) if callable(answer) else answer
