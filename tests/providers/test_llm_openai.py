from types import SimpleNamespace

import pytest

from singular.providers import (
    LLMProviderClient,
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
            assert model == "gpt-3.5-turbo"
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


def test_openai_quota_maps_to_typed_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

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

    with pytest.raises(ProviderQuotaExceededError):
        llm_openai.generate_reply("hi")


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
