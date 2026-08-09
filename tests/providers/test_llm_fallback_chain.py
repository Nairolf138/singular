import pytest

import singular.providers as providers
from singular.organisms.talk import ContextBudget
from singular.providers import (
    FallbackLLMClient,
    LLMProviderContract,
    ProviderUnavailableError,
    load_llm_client,
)


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
    monkeypatch.setattr(
        providers,
        "_load_provider_contract",
        lambda chain_name: _dummy_contract(chain_name),
    )

    client = load_llm_client(None)
    assert client is not None
    assert client.name == "dummy"
    assert client.generate_reply("hello") == "dummy:hello"


def test_load_llm_client_env_fallback_chain_has_priority_over_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "dummy")
    monkeypatch.setattr(providers, "DEFAULT_FALLBACK_CHAIN", ("local",))
    monkeypatch.setattr(
        providers,
        "_load_provider_contract",
        lambda chain_name: _dummy_contract(chain_name),
    )

    client = load_llm_client(None)
    assert client is not None
    assert client.name == "dummy"
    assert client.generate_reply("bonjour") == "dummy:bonjour"


def test_load_llm_client_explicit_name_has_priority_over_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "dummy")
    monkeypatch.setattr(
        providers,
        "_load_provider_contract",
        lambda chain_name: _dummy_contract(chain_name),
    )

    client = load_llm_client("openai")
    assert client is not None
    assert client.name == "openai"
    assert client.generate_reply("salut") == "openai:salut"


def test_fallback_client_errors_when_chain_empty():
    client = FallbackLLMClient(
        name="none", generate=lambda prompt, timeout=8.0: prompt, chain=[]
    )
    with pytest.raises(ProviderUnavailableError):
        client.generate_reply("x")


def test_fallback_client_records_the_provider_that_succeeds():
    def fail(_prompt: str, *, timeout: float = 8.0) -> str:
        raise ProviderUnavailableError("offline")

    client = FallbackLLMClient(
        name="automatic",
        generate=lambda prompt, timeout=8.0: prompt,
        chain=[
            providers.LLMProviderClient(name="first", generate=fail, max_retries=0),
            providers.LLMProviderClient(
                name="second", generate=lambda prompt, timeout=8.0: f"second:{prompt}"
            ),
        ],
    )

    assert client.generate_reply("hello") == "second:hello"
    assert client.last_active_provider == "second"
    assert client.last_fallback_used is True
    assert client.last_errors == [
        {"provider": "first", "category": "unavailable", "error": "offline"}
    ]


def test_automatic_selection_excludes_unhealthy_ollama_and_uses_real_fallback(
    monkeypatch,
):
    contracts = {
        "ollama": LLMProviderContract(
            name="ollama",
            generate=lambda prompt: prompt,
            embed=lambda text: [],
            healthcheck=lambda: {"ok": False, "error": "Unable to connect to Ollama"},
            cost_estimate=lambda prompt, completion="": 0.0,
        ),
        "openai": _dummy_contract("openai"),
    }
    monkeypatch.setenv("LLM_PROVIDER_FALLBACK", "ollama,openai")
    monkeypatch.setattr(providers, "_load_provider_contract", contracts.get)

    client = load_llm_client(None)

    assert client is not None
    assert client.selected_provider == "openai"
    assert client.candidates[0]["installed"] is True
    assert client.candidates[0]["reachable"] is False
    assert client.candidates[0]["exclusion_cause"] == "Unable to connect to Ollama"


def test_context_budget_is_provider_aware_stable_and_safely_capped(monkeypatch):
    monkeypatch.delenv("SINGULAR_TALK_CONTEXT_CHARS", raising=False)
    openai = providers.LLMProviderClient(name="openai", generate=lambda prompt: prompt)
    ollama = providers.LLMProviderClient(name="ollama", generate=lambda prompt: prompt)
    assert ContextBudget.for_client(openai) == ContextBudget.for_client(openai)
    assert (
        ContextBudget.for_client(ollama).total > ContextBudget.for_client(openai).total
    )

    monkeypatch.setenv("SINGULAR_TALK_CONTEXT_CHARS", "999999")
    assert ContextBudget.for_client(ollama).total == 2000
