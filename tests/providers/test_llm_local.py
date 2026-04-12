import pytest

from singular.providers import (
    ProviderRetryExhaustedError,
    ProviderTimeoutError,
    load_llm_client,
    load_llm_provider,
)
from singular.providers import llm_local


def test_load_llm_provider_local():
    """Ensure the 'local' provider can be loaded."""

    func = load_llm_provider("local")
    assert callable(func)


def test_load_llm_client_local():
    client = load_llm_client("local")
    assert client is not None
    assert client.name == "local"


def test_local_provider_timeout(monkeypatch):
    monkeypatch.setattr(llm_local, "_get_pipe", lambda: object())

    def fake_infer(_pipe, _prompt):
        raise ProviderTimeoutError("timed out")

    monkeypatch.setattr(llm_local, "_infer", fake_infer)

    with pytest.raises(ProviderTimeoutError):
        llm_local.generate_reply("hello")


def test_local_retry_bounded(monkeypatch):
    attempts = {"count": 0}

    def timeout_then_count(prompt: str, *, timeout: float = 8.0) -> str:
        del prompt, timeout
        attempts["count"] += 1
        raise ProviderTimeoutError("slow")

    client = load_llm_client("local")
    assert client is not None
    monkeypatch.setattr(client, "generate", timeout_then_count)
    client.max_retries = 1

    with pytest.raises(ProviderRetryExhaustedError):
        client.generate_reply("yo", timeout=0.1)

    assert attempts["count"] == 2
