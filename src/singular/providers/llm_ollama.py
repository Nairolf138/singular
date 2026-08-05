"""Ollama LLM provider using the local HTTP API."""

from __future__ import annotations

import json
import os
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import ProviderExecutionError, ProviderMetrics, ProviderTimeoutError, ProviderUnavailableError

MAX_RETRIES = 1
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OLLAMA_EMBED_MODEL = "nomic-embed-text"

LAST_METRICS = ProviderMetrics(provider="ollama")


def _host() -> str:
    return (os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).strip().rstrip("/")


def _model() -> str:
    return (os.getenv("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL).strip()


def _embed_model() -> str:
    return (os.getenv("OLLAMA_EMBED_MODEL") or "").strip() or _model() or DEFAULT_OLLAMA_EMBED_MODEL


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""

    return "".join(ch for ch in text if ch.isprintable())


def _post_json(path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    url = f"{_host()}{path}"
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured local provider URL
            raw = response.read().decode("utf-8")
    except TimeoutError as exc:
        raise ProviderTimeoutError("Ollama request timed out") from exc
    except socket.timeout as exc:
        raise ProviderTimeoutError("Ollama request timed out") from exc
    except HTTPError as exc:
        message = exc.reason or exc.read().decode("utf-8", errors="replace")
        raise ProviderExecutionError(f"Ollama HTTP error {exc.code}: {message}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError | socket.timeout):
            raise ProviderTimeoutError("Ollama request timed out") from exc
        raise ProviderUnavailableError("Unable to connect to Ollama") from exc
    except OSError as exc:
        raise ProviderUnavailableError("Unable to connect to Ollama") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderExecutionError("Ollama response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderExecutionError("Ollama response schema error: expected object")
    return parsed


def generate(prompt: str, *, timeout: float = 8.0) -> str:
    """Generate a reply with Ollama's local ``/api/generate`` endpoint."""

    start = time.perf_counter()
    response = _post_json(
        "/api/generate",
        {"model": _model(), "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    LAST_METRICS.latency_ms = round(elapsed_ms, 2)

    text = response.get("response")
    if not isinstance(text, str):
        raise ProviderExecutionError("Ollama response schema error: missing response text")

    filtered = _filter(text)
    LAST_METRICS.input_tokens = len(prompt.split())
    LAST_METRICS.output_tokens = len(filtered.split())
    LAST_METRICS.estimated_cost_usd = cost_estimate(prompt, filtered)
    return filtered


def embed(text: str, *, timeout: float = 8.0) -> list[float]:
    """Return embeddings from Ollama's local embedding endpoint."""

    response = _post_json(
        "/api/embeddings",
        {"model": _embed_model(), "prompt": text},
        timeout=timeout,
    )
    values = response.get("embedding")
    if not isinstance(values, list):
        raise ProviderExecutionError("Ollama response schema error: missing embedding")
    try:
        return [float(value) for value in values]
    except (TypeError, ValueError) as exc:
        raise ProviderExecutionError("Ollama response schema error: invalid embedding values") from exc


def healthcheck() -> dict[str, object]:
    """Return provider configuration and whether the local Ollama API responds."""

    try:
        _post_json("/api/generate", {"model": _model(), "prompt": "", "stream": False}, timeout=1.0)
    except Exception as exc:  # healthchecks report instead of raising
        return {"ok": False, "provider": "ollama", "host": _host(), "model": _model(), "error": str(exc)}
    return {"ok": True, "provider": "ollama", "host": _host(), "model": _model()}


def cost_estimate(prompt: str, completion: str = "", **_kwargs: object) -> float:
    """Ollama runs locally, so direct provider cost is zero."""

    del prompt, completion
    return 0.0


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Backward-compatible alias to unified ``generate``."""

    return generate(prompt, timeout=timeout)
