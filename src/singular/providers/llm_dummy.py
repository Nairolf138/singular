"""Dummy LLM provider for tests and offline usage."""

from __future__ import annotations

from . import ProviderMetrics


LAST_METRICS = ProviderMetrics(provider="dummy")


def generate(prompt: str, *, timeout: float = 8.0) -> str:
    """Return a simple echoed reply for ``prompt``."""

    LAST_METRICS.latency_ms = min(timeout * 5.0, 10.0)
    LAST_METRICS.input_tokens = len(prompt.split())
    reply = f"Echo: {prompt}"
    LAST_METRICS.output_tokens = len(reply.split())
    LAST_METRICS.estimated_cost_usd = 0.0
    return reply


def embed(text: str, *, timeout: float = 8.0) -> list[float]:
    del timeout
    return [float(len(text)), float(sum(ord(ch) for ch in text) % 997)]


def healthcheck() -> dict[str, object]:
    return {"ok": True, "provider": "dummy", "offline": True}


def cost_estimate(prompt: str, completion: str = "") -> float:
    del prompt, completion
    return 0.0


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Backward-compatible alias to unified ``generate``."""

    return generate(prompt, timeout=timeout)
