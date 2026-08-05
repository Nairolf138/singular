import singular.providers as providers
from singular.providers import LLMProviderContract, doctor_providers, provider_is_real


def test_provider_is_real_excludes_offline_stubs():
    assert provider_is_real("openai") is True
    assert provider_is_real("ollama") is True
    assert provider_is_real("local") is True
    assert provider_is_real("stub") is False
    assert provider_is_real("dummy") is False


def test_doctor_providers_reports_missing_provider_category(monkeypatch):
    monkeypatch.setattr(providers, "_load_provider_contract", lambda _name: None)

    results = doctor_providers(["openai"])

    assert results == [
        {
            "provider": "openai",
            "ok": False,
            "llm_real": True,
            "error_category": "provider_missing",
        }
    ]


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
