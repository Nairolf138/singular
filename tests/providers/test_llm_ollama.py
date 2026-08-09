from __future__ import annotations

import json
import socket
from urllib.error import URLError

import pytest

from singular.providers import (
    ProviderExecutionError,
    ProviderMisconfiguredError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    llm_ollama,
)


class FakeHTTPResponse:
    def __init__(
        self, payload: dict[str, object], url: str = "http://127.0.0.1:11434/api"
    ):
        self.payload = payload
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def geturl(self) -> str:
        return self.url


def test_generate_reply_posts_to_configured_ollama_host(monkeypatch):
    calls = []
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama.test/")
    monkeypatch.setenv("OLLAMA_MODEL", " mistral ")
    monkeypatch.setenv("OLLAMA_NETWORK_POLICY", "unrestricted")

    def fake_urlopen(request, timeout):
        calls.append(
            (request.full_url, json.loads(request.data.decode("utf-8")), timeout)
        )
        return FakeHTTPResponse({"response": "bonjour\x00"})

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    assert llm_ollama.generate_reply("salut", timeout=2.5) == "bonjour"
    assert calls == [
        (
            "http://ollama.test/api/generate",
            {"model": "mistral", "prompt": "salut", "stream": False},
            2.5,
        )
    ]


def test_embed_uses_configured_embedding_model(monkeypatch):
    calls = []
    monkeypatch.setenv("OLLAMA_EMBED_MODEL", " nomic-embed-text ")

    def fake_urlopen(request, timeout):
        calls.append(
            (request.full_url, json.loads(request.data.decode("utf-8")), timeout)
        )
        return FakeHTTPResponse({"embedding": [1, "2.5", 3.0]})

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    assert llm_ollama.embed("texte", timeout=4.0) == [1.0, 2.5, 3.0]
    assert calls[0][1] == {"model": "nomic-embed-text", "prompt": "texte"}
    assert calls[0][2] == 4.0


def test_timeout_maps_to_provider_timeout(monkeypatch):
    def fake_urlopen(_request, timeout):
        raise socket.timeout("too slow")

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    with pytest.raises(ProviderTimeoutError):
        llm_ollama.generate_reply("salut")


def test_network_error_maps_to_provider_unavailable(monkeypatch):
    def fake_urlopen(_request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    with pytest.raises(ProviderUnavailableError):
        llm_ollama.generate_reply("salut")


def test_schema_errors_map_to_provider_execution(monkeypatch):
    def fake_urlopen(_request, timeout):
        return FakeHTTPResponse({"not_response": "missing"})

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    with pytest.raises(ProviderExecutionError, match="missing response text"):
        llm_ollama.generate_reply("salut")


def test_healthcheck_reports_unavailable(monkeypatch):
    def fake_urlopen(_request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)

    result = llm_ollama.healthcheck()
    assert result["ok"] is False
    assert result["provider"] == "ollama"
    assert result["host"] == llm_ollama.DEFAULT_OLLAMA_HOST


def test_cost_estimate_is_zero_for_local_ollama():
    assert llm_ollama.cost_estimate("prompt", "completion") == 0.0


@pytest.mark.parametrize(
    "host", ["http://127.0.0.1:11434", "http://[::1]:11434", "http://localhost:11434"]
)
def test_local_policy_accepts_loopback(monkeypatch, host):
    monkeypatch.setenv("OLLAMA_HOST", host)
    monkeypatch.setenv("OLLAMA_NETWORK_POLICY", "local")
    assert llm_ollama._host() == host


@pytest.mark.parametrize("host", ["http://192.168.1.20:11434", "https://203.0.113.10"])
def test_local_policy_rejects_lan_and_public_hosts(monkeypatch, host):
    monkeypatch.setenv("OLLAMA_HOST", host)
    monkeypatch.setenv("OLLAMA_NETWORK_POLICY", "local")
    with pytest.raises(ProviderMisconfiguredError, match="loopback"):
        llm_ollama._host()


def test_local_policy_rejects_http_redirect_to_public_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_NETWORK_POLICY", "local")

    def fake_urlopen(_request, timeout):
        return FakeHTTPResponse(
            {"response": "unsafe"}, "https://203.0.113.10/api/generate"
        )

    monkeypatch.setattr(llm_ollama, "_urlopen", fake_urlopen)
    with pytest.raises(ProviderMisconfiguredError, match="loopback"):
        llm_ollama.generate("hello")


def test_disabled_policy_refuses_even_loopback(monkeypatch):
    monkeypatch.setenv("OLLAMA_NETWORK_POLICY", "disabled")
    with pytest.raises(ProviderMisconfiguredError, match="disabled"):
        llm_ollama.generate("hello")


def test_setup_reports_stopped_service_with_remediation(monkeypatch):
    monkeypatch.setattr(
        llm_ollama,
        "available_models",
        lambda **_kwargs: (_ for _ in ()).throw(ProviderUnavailableError("offline")),
    )
    result = llm_ollama.setup_status()
    assert (result["state"], result["remediation"]) == (
        "service_stopped",
        "ollama serve",
    )


def test_setup_pulls_missing_model_and_validates_http_generation(monkeypatch):
    responses = iter([[], ["llama3.2:latest"]])
    monkeypatch.setattr(
        llm_ollama, "available_models", lambda **_kwargs: next(responses)
    )
    monkeypatch.setattr(llm_ollama.shutil, "which", lambda _name: "/usr/bin/ollama")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(llm_ollama.subprocess, "run", fake_run)
    monkeypatch.setattr(llm_ollama, "generate", lambda prompt, timeout: "ok")
    result = llm_ollama.setup_status(pull=True)
    assert result["state"] == "ready"
    assert calls[0][0] == ["/usr/bin/ollama", "pull", llm_ollama.DEFAULT_OLLAMA_MODEL]


def test_setup_reports_incomplete_download_process(monkeypatch):
    monkeypatch.setattr(llm_ollama, "available_models", lambda **_kwargs: [])
    monkeypatch.setattr(llm_ollama.shutil, "which", lambda _name: "/bin/ollama")
    monkeypatch.setattr(
        llm_ollama.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Completed", (), {"returncode": 1})(),
    )
    result = llm_ollama.setup_status(model="missing", pull=True)
    assert result["state"] == "download_incomplete"
    assert result["remediation"] == "ollama pull missing"
