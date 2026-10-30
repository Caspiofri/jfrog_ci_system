"""The LLM seam, offline: lazy client, retry policy, JSON parsing, and the FakeLLM script."""
import random
import subprocess
import sys

import pytest

from ci.llm import DEFAULT_MODEL, FakeLLM, GeminiLLM, LLMError, model_name


class _Resp:
    def __init__(self, text):
        self.text = text


class _ApiError(Exception):
    def __init__(self, code, headers=None, details=None):
        super().__init__(f"HTTP {code}")
        self.code = code
        self.response = type("R", (), {"headers": headers})() if headers is not None else None
        self.details = details


class _Client:
    """Stands in for genai.Client: answers or raises from a script, records the calls."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Resp(nxt)


def _gemini(script, **kw):
    client = _Client(script)
    built = []

    def factory():
        built.append(1)
        return client

    return GeminiLLM(model="m", client_factory=factory, sleep=lambda s: None, **kw), client, built


def test_client_is_built_on_first_call_only():
    llm, client, built = _gemini(['{"a": 1}', '{"b": 2}'])
    assert built == []
    assert llm.complete("p", {"type": "object"}) == {"a": 1}
    assert llm.complete("p", {"type": "object"}) == {"b": 2}
    assert built == [1]
    model, contents, config = client.calls[0]
    assert (model, contents) == ("m", "p")
    assert config["response_mime_type"] == "application/json"
    assert config["response_json_schema"] == {"type": "object"}


def test_retries_on_429_and_5xx_then_succeeds():
    llm, client, _ = _gemini([_ApiError(429), _ApiError(503), '{"ok": true}'])
    assert llm.complete("p", {}) == {"ok": True}
    assert len(client.calls) == 3


def test_gives_up_after_max_attempts():
    llm, client, _ = _gemini([_ApiError(500)] * 3)
    with pytest.raises(LLMError):
        llm.complete("p", {})
    assert len(client.calls) == 3


def test_does_not_retry_a_client_error():
    llm, client, _ = _gemini([_ApiError(400)])
    with pytest.raises(LLMError):
        llm.complete("p", {})
    assert len(client.calls) == 1


@pytest.mark.parametrize("text", ["not json", "[1, 2]", "", None])
def test_non_object_answer_is_an_llm_error(text):
    llm, _, _ = _gemini([text])
    with pytest.raises(LLMError):
        llm.complete("p", {})


def test_missing_key_is_reported_on_call_not_on_construction(monkeypatch):

    from modules import llm_clients

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # a developer's .env must not supply the key
    for name in ("GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI"):
        monkeypatch.delenv(name, raising=False)
    llm_clients.gemini_client.cache_clear()
    llm = GeminiLLM()  # no error yet
    with pytest.raises(LLMError, match="GOOGLE_API_KEY"):
        llm.complete("p", {})


def test_gemini_client_comes_from_the_shared_factory(monkeypatch):
    """Vertex opt-in and the request timeout apply to the ci path too."""
    from modules import llm_clients

    sentinel = object()
    monkeypatch.setattr(llm_clients, "gemini_client", lambda: sentinel)
    assert GeminiLLM()._get_client() is sentinel


def test_model_from_env(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert model_name() == DEFAULT_MODEL == "gemini-3.6-flash"
    monkeypatch.setenv("GEMINI_MODEL", "other")
    assert GeminiLLM(client_factory=lambda: None).model == "other"


def test_import_has_no_side_effects():
    code = "import sys, ci.llm; assert 'google.genai' not in sys.modules; assert 'dotenv' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True)


def test_fake_llm_script_and_recording():
    fake = FakeLLM([{"a": 1}, ValueError("boom"), lambda p, s: {"echo": p}])
    assert fake.complete("one", {"s": 1}) == {"a": 1}
    with pytest.raises(ValueError):
        fake.complete("two", {})
    assert fake.complete("three", {}) == {"echo": "three"}
    with pytest.raises(LLMError):
        fake.complete("four", {})
    assert [c[0] for c in fake.calls] == ["one", "two", "three", "four"]


def test_fake_llm_single_responder_answers_every_call():
    fake = FakeLLM(lambda p, s: {"n": len(p)})
    assert fake.complete("ab", {}) == {"n": 2}
    assert fake.complete("abc", {}) == {"n": 3}


def _sleeps(script):
    waits = []
    client = _Client(script)
    llm = GeminiLLM(model="m", client_factory=lambda: client, sleep=waits.append, rng=random.Random(0))
    return llm, waits


def test_retry_after_header_is_honoured():
    llm, waits = _sleeps([_ApiError(429, headers={"retry-after": "7"}), '{"ok": 1}'])
    assert llm.complete("p", {}) == {"ok": 1}
    assert waits == [7.0]


def test_gemini_retry_info_is_honoured_and_capped():
    info = {"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}}
    huge = {"error": {"details": [{"retryDelay": "900s"}]}}
    llm, waits = _sleeps([_ApiError(429, details=info), _ApiError(429, details=huge), '{"ok": 1}'])
    llm.complete("p", {})
    assert waits == [17.0, 60.0]


def test_backoff_has_jitter_within_bounds():
    llm, waits = _sleeps([_ApiError(503), _ApiError(503), '{"ok": 1}'])
    llm.complete("p", {})
    assert 2.0 <= waits[0] <= 3.0 and 4.0 <= waits[1] <= 6.0
    assert waits[0] != 2.0  # jitter applied (seeded)
