from singular import cli


def test_config_providers_doctor_prints_provider_status(monkeypatch, capsys):
    monkeypatch.setattr(
        "singular.providers.doctor_providers",
        lambda: [
            {
                "provider": "openai",
                "ok": False,
                "llm_real": True,
                "error_category": "misconfigured",
                "error": "OPENAI_API_KEY not configured",
            },
            {"provider": "ollama", "ok": True, "llm_real": True, "error_category": None},
        ],
    )

    rc = cli.main(["config", "providers", "doctor"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "Diagnostic providers LLM" in out
    assert "openai" in out
    assert "error_category=misconfigured" in out
    assert "ollama" in out
