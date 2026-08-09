import singular.providers as providers
from singular.providers import (
    LLMProviderContract,
    doctor_providers,
    provider_diagnostics,
    provider_is_real,
)


def test_provider_is_real_excludes_offline_stubs():
    assert provider_is_real("openai") is True
    assert provider_is_real("ollama") is True
    assert provider_is_real("local") is True
    assert provider_is_real("stub") is False
    assert provider_is_real("dummy") is False


def test_doctor_providers_reports_missing_provider_category(monkeypatch):
    monkeypatch.setattr(providers, "_load_provider_contract", lambda _name: None)

    results = doctor_providers(["openai"])

    assert results[0]["provider"] == "openai"
    assert results[0]["state"] == "unavailable"
    assert results[0]["error_category"] == "provider_missing"
    assert results[0]["configuration_command"] == "singular config openai"


def test_doctor_providers_normalizes_healthcheck_failures(monkeypatch):
    contract = LLMProviderContract(
        name="ollama",
        generate=lambda prompt, timeout=8.0: prompt,
        embed=lambda text, timeout=8.0: [1.0],
        healthcheck=lambda: {"ok": False, "provider": "ollama", "error": "offline"},
        cost_estimate=lambda prompt, completion="": 0.0,
    )
    monkeypatch.setattr(providers, "_load_provider_contract", lambda _name: contract)

    result = doctor_providers(["ollama"])[0]

    assert result["provider"] == "ollama"
    assert result["ok"] is False
    assert result["llm_real"] is True
    assert result["error_category"] == "unavailable"
    assert result["state"] == "unavailable"
    assert result["cause"] == "offline"


def test_diagnostics_distinguish_dummy_and_real_provider_restoration(monkeypatch):
    contracts = {
        "dummy": LLMProviderContract(
            name="dummy",
            generate=lambda prompt: prompt,
            embed=lambda text: [1.0],
            healthcheck=lambda: {"ok": True, "provider": "dummy"},
            cost_estimate=lambda prompt, completion="": 0.0,
        ),
        "openai": LLMProviderContract(
            name="openai",
            generate=lambda prompt: prompt,
            embed=lambda text: [1.0],
            healthcheck=lambda: {"ok": True, "provider": "openai"},
            cost_estimate=lambda prompt, completion="": 0.0,
        ),
    }
    monkeypatch.setattr(
        providers, "_load_provider_contract", lambda name: contracts.get(name)
    )

    assert provider_diagnostics(["dummy"])["state"] == "degraded_dummy"
    restored = provider_diagnostics(["dummy", "openai"])
    assert restored["state"] == "ready"
    assert restored["llm_real"] is True


def test_doctor_reports_missing_openai_key_and_ollama_timeout(monkeypatch):
    contracts = {
        "openai": LLMProviderContract(
            name="openai",
            generate=lambda prompt: prompt,
            embed=lambda text: [1.0],
            healthcheck=lambda: {
                "ok": False,
                "provider": "openai",
                "error": "missing OPENAI_API_KEY",
            },
            cost_estimate=lambda prompt, completion="": 0.0,
        ),
        "ollama": LLMProviderContract(
            name="ollama",
            generate=lambda prompt: prompt,
            embed=lambda text: [1.0],
            healthcheck=lambda: {
                "ok": False,
                "provider": "ollama",
                "error": "Ollama request timed out",
            },
            cost_estimate=lambda prompt, completion="": 0.0,
        ),
    }
    monkeypatch.setattr(providers, "_load_provider_contract", contracts.get)
    openai, ollama = doctor_providers(["openai", "ollama"])
    assert (openai["state"], openai["error_category"]) == (
        "unavailable",
        "misconfigured",
    )
    assert (ollama["state"], ollama["cause"]) == (
        "unavailable",
        "Ollama request timed out",
    )


def test_doctor_distinguishes_missing_ollama_model(monkeypatch):
    contract = LLMProviderContract(
        name="ollama",
        generate=lambda prompt: prompt,
        embed=lambda text: [],
        healthcheck=lambda: {"ok": False, "error": "model llama3 not found"},
        cost_estimate=lambda prompt, completion="": 0.0,
    )
    monkeypatch.setattr(providers, "_load_provider_contract", lambda _name: contract)

    result = doctor_providers(["ollama"])[0]

    assert result["installed"] is True
    assert result["configured"] is False
    assert result["reachable"] is False


def test_provider_diagnostics_exposes_all_three_dashboard_states(monkeypatch):
    monkeypatch.setattr(
        providers,
        "doctor_providers",
        lambda _names=None: [{"state": "unavailable"}],
    )
    assert provider_diagnostics()["state"] == "unavailable"
    monkeypatch.setattr(
        providers,
        "doctor_providers",
        lambda _names=None: [{"state": "degraded_dummy"}],
    )
    assert provider_diagnostics()["state"] == "degraded_dummy"
    monkeypatch.setattr(
        providers, "doctor_providers", lambda _names=None: [{"state": "ready"}]
    )
    assert provider_diagnostics()["state"] == "ready"
