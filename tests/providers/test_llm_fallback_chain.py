import pytest

from singular.providers import FallbackLLMClient, ProviderUnavailableError, load_llm_client


def test_load_llm_client_from_env_fallback_chain(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "dummy")
    client = load_llm_client(None)
    assert client is not None
    assert client.name == "dummy"
    assert client.generate_reply("hello") == "Echo: hello"


def test_load_llm_client_comma_chain_uses_order(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = load_llm_client("openai,dummy")
    assert isinstance(client, FallbackLLMClient)
    assert client.generate_reply("bonjour") == "Echo: bonjour"


def test_fallback_client_errors_when_chain_empty():
    client = FallbackLLMClient(name="none", generate=lambda prompt, timeout=8.0: prompt, chain=[])
    with pytest.raises(ProviderUnavailableError):
        client.generate_reply("x")
