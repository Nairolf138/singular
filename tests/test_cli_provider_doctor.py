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
            {
                "provider": "ollama",
                "ok": True,
                "llm_real": True,
                "error_category": None,
            },
        ],
    )

    rc = cli.main(["config", "providers", "doctor"])

    out = capsys.readouterr().out
    assert rc == 1
    assert "Diagnostic providers LLM" in out
    assert "openai" in out
    assert "error_category=misconfigured" in out
    assert "ollama" in out


def test_provider_doctor_saves_secret_separately_with_restrictive_permissions(
    monkeypatch, tmp_path
):
    monkeypatch.setattr("singular.providers.doctor_providers", lambda: [])
    config = tmp_path / "providers.env"
    credentials = tmp_path / "credentials.env"

    cli.main(
        [
            "config",
            "providers",
            "doctor",
            "--save",
            str(config),
            "--provider",
            "ollama",
            "--fallback",
            "ollama,openai",
            "--ollama-model",
            "llama3",
            "--api-key",
            "sk-secret-value",
            "--credentials-file",
            str(credentials),
        ]
    )

    assert "sk-secret-value" not in config.read_text()
    assert "OPENAI_API_KEY_FILE" in config.read_text()
    assert credentials.stat().st_mode & 0o077 == 0
