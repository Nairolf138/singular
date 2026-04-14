import pytest

import singular.providers as providers
from singular.providers import FallbackLLMClient, LLMProviderContract, ProviderUnavailableError, load_llm_client


def _dummy_contract(name: str) -> LLMProviderContract:
    return LLMProviderContract(
        name=name,
        generate=lambda prompt, timeout=8.0: f"{name}:{prompt}",
        embed=lambda text, timeout=8.0: [float(len(text)), timeout],
        healthcheck=lambda: {"ok": True, "provider": name},
        cost_estimate=lambda prompt, completion="": 0.0,
    )


def test_load_llm_client_none_without_env_uses_default_fallback_chain(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER_FALLBACK", raising=False)
    monkeypatch.setattr(providers, "DEFAULT_FALLBACK_CHAIN", ("dummy",))
    monkeypatch.setattr(providers, "_load_provider_contract", lambda chain_name: _dummy_contract(chain_name))

    client = load_llm_client(None)
    assert client is not None
    assert client.name == "dummy"
    assert client.generate_reply("hello") == "dummy:hello"


def test_load_llm_client_env_fallback_chain_has_priority_over_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "dummy")
    monkeypatch.setattr(providers, "DEFAULT_FALLBACK_CHAIN", ("local",))
    monkeypatch.setattr(providers, "_load_provider_contract", lambda chain_name: _dummy_contract(chain_name))

    client = load_llm_client(None)
    assert client is not None
    assert client.name == "dummy"
    assert client.generate_reply("bonjour") == "dummy:bonjour"


def test_load_llm_client_explicit_name_has_priority_over_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "dummy")
    monkeypatch.setattr(providers, "_load_provider_contract", lambda chain_name: _dummy_contract(chain_name))

    client = load_llm_client("openai")
    assert client is not None
    assert client.name == "openai"
    assert client.generate_reply("salut") == "openai:salut"


def test_fallback_client_errors_when_chain_empty():
    client = FallbackLLMClient(name="none", generate=lambda prompt, timeout=8.0: prompt, chain=[])
    with pytest.raises(ProviderUnavailableError):
        client.generate_reply("x")
