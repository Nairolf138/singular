from singular import cli
from singular.providers import llm_ollama


def test_cli_ollama_setup_noninteractive_never_pulls_implicitly(monkeypatch, capsys):
    calls = []

    def fake_setup_status(**kwargs):
        calls.append(kwargs)
        return {
            "ok": False,
            "state": "model_missing",
            "models": [],
            "remediation": "ollama pull llama3.2",
        }

    monkeypatch.setattr(llm_ollama, "setup_status", fake_setup_status)
    assert (
        cli.main(["config", "providers", "setup", "ollama", "--non-interactive"]) == 1
    )
    assert calls == [
        {"model": llm_ollama.DEFAULT_OLLAMA_MODEL, "pull": False, "timeout": 120.0}
    ]
    assert "Remédiation: ollama pull llama3.2" in capsys.readouterr().err


def test_cli_ollama_setup_ci_explicit_pull(monkeypatch):
    calls = []

    def fake_setup_status(**kwargs):
        calls.append(kwargs)
        if kwargs["pull"]:
            return {"ok": True, "state": "ready", "models": ["ci-model"]}
        return {
            "ok": False,
            "state": "model_missing",
            "models": [],
            "remediation": "ollama pull ci-model",
        }

    monkeypatch.setattr(llm_ollama, "setup_status", fake_setup_status)
    assert (
        cli.main(
            [
                "config",
                "providers",
                "setup",
                "ollama",
                "--model",
                "ci-model",
                "--non-interactive",
                "--pull",
            ]
        )
        == 0
    )
    assert [call["pull"] for call in calls] == [False, True]
