from types import SimpleNamespace

import pytest

from singular.providers import (
    LLMProviderClient,
    ProviderExecutionError,
    ProviderMisconfiguredError,
    ProviderQuotaExceededError,
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
)
from singular.providers import llm_openai


def test_generate_reply_without_key(monkeypatch):
    """No API key should raise an explicit misconfiguration error."""

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderMisconfiguredError):
        llm_openai.generate_reply("hi")


def test_generate_reply_success(monkeypatch):
    """Mock the OpenAI client to test successful replies and filtering."""

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, *, model, messages, max_tokens, timeout):
            assert model == llm_openai.DEFAULT_OPENAI_MODEL
            assert messages == [{"role": "user", "content": "hi"}]
            assert max_tokens == 100
            assert timeout == 3.0
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="hello\x00"))]
            )

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)
    assert llm_openai.generate_reply("hi", timeout=3.0) == "hello"


def test_generate_reply_uses_openai_model_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", " gpt-4.1-mini ")

    class FakeCompletions:
        def create(self, *, model, messages, max_tokens, timeout):
            assert model == "gpt-4.1-mini"
            assert messages == [{"role": "user", "content": "hi"}]
            assert max_tokens == 100
            assert timeout == 2.0
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))]
            )

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)
    assert llm_openai.generate_reply("hi", timeout=2.0) == "hello"


def test_openai_quota_maps_to_typed_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    timer_values = iter([1.0, 1.25])

    class FakeRateLimitError(Exception):
        pass

    class FakeCompletions:
        def create(self, **_kwargs):
            raise FakeRateLimitError("quota")

    class FakeClient:
        def __init__(self, api_key):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)
    monkeypatch.setattr(llm_openai, "RateLimitError", FakeRateLimitError)
    monkeypatch.setattr(llm_openai.time, "perf_counter", lambda: next(timer_values))

    with pytest.raises(ProviderQuotaExceededError):
        llm_openai.generate_reply("hi")
    assert llm_openai.LAST_METRICS.latency_ms == 250.0


def test_generate_reply_latency_uses_elapsed_time(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, *, model, messages, max_tokens, timeout):
            del model, messages, max_tokens, timeout
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
            )

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    timer_values = iter([10.0, 10.1234])
    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)
    monkeypatch.setattr(llm_openai.time, "perf_counter", lambda: next(timer_values))

    assert llm_openai.generate_reply("hi", timeout=3.0) == "ok"
    assert llm_openai.LAST_METRICS.latency_ms == 123.4


def test_retry_strategy_is_bounded():
    attempts = {"count": 0}

    def always_timeout(_prompt: str, *, timeout: float = 8.0) -> str:
        attempts["count"] += 1
        raise ProviderTimeoutError(f"timeout={timeout}")

    client = LLMProviderClient(name="openai", generate=always_timeout, max_retries=2)

    with pytest.raises(ProviderRetryExhaustedError):
        client.generate_reply("hello", timeout=1.0)

    assert attempts["count"] == 3


def test_openai_version():
    """If ``openai`` is installed ensure it is the modern client (>=1.0)."""

    try:
        import openai
    except Exception:  # pragma: no cover - optional dependency missing
        pytest.skip("openai not installed")
    from packaging import version

    assert version.parse(openai.__version__) >= version.parse("1.0.0")


def test_healthcheck_exposes_active_model_default(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_openai, "OpenAI", object())

    result = llm_openai.healthcheck()
    assert result["model"] == llm_openai.DEFAULT_OPENAI_MODEL


def test_healthcheck_exposes_active_model_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", " gpt-4.1 ")
    monkeypatch.setattr(llm_openai, "OpenAI", object())

    result = llm_openai.healthcheck()
    assert result["model"] == "gpt-4.1"


def test_generate_reply_schema_error_empty_choices(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(choices=[])

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)

    with pytest.raises(ProviderExecutionError, match="empty choices"):
        llm_openai.generate_reply("hi")


def test_generate_reply_schema_error_missing_message_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace())])

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)

    with pytest.raises(ProviderExecutionError, match="missing message content"):
        llm_openai.generate_reply("hi")


def test_generate_reply_schema_error_non_string_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=["not", "text"]))]
            )

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)

    with pytest.raises(ProviderExecutionError, match="not a string"):
        llm_openai.generate_reply("hi")
