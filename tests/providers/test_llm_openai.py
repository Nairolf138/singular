import types
from types import SimpleNamespace

import pytest

from singular.providers import llm_openai


def test_generate_reply_without_key(monkeypatch):
    """If no API key is set the provider should return an explicit message."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_openai.generate_reply("hi") == "OpenAI API key not configured."


def test_generate_reply_success(monkeypatch):
    """Mock the OpenAI client to test successful replies and filtering."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class FakeCompletions:
        def create(self, *, model, messages, max_tokens):
            assert model == "gpt-3.5-turbo"
            assert messages == [{"role": "user", "content": "hi"}]
            assert max_tokens == 100
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="hello\x00"))]
            )

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(llm_openai, "OpenAI", FakeClient)
    assert llm_openai.generate_reply("hi") == "hello"


def test_openai_version():
    """If ``openai`` is installed ensure it is the modern client (>=1.0)."""
    try:
        import openai
    except Exception:  # pragma: no cover - optional dependency missing
        pytest.skip("openai not installed")
    from packaging import version

    assert version.parse(openai.__version__) >= version.parse("1.0.0")
