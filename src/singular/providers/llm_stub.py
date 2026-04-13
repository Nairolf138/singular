"""Rule-based stub LLM provider for offline usage."""

from __future__ import annotations

import re

from . import ProviderMetrics


LAST_METRICS = ProviderMetrics(provider="stub")


def generate(prompt: str, *, timeout: float = 8.0) -> str:
    """Generate a deterministic reply without network access."""

    LAST_METRICS.latency_ms = min(timeout * 5.0, 10.0)
    LAST_METRICS.input_tokens = len(prompt.split())
    text = prompt.strip().lower()
    if re.search(r"\b(hi|hello|salut|bonjour)\b", text):
        reply = "Hello!"
    elif text.endswith("?"):
        reply = "I'm not sure about that."
    else:
        reply = f"You said: {prompt}"
    LAST_METRICS.output_tokens = len(reply.split())
    LAST_METRICS.estimated_cost_usd = 0.0
    return reply


def embed(text: str, *, timeout: float = 8.0) -> list[float]:
    del timeout
    vowels = sum(1 for ch in text.lower() if ch in "aeiouy")
    return [float(len(text)), float(vowels)]


def healthcheck() -> dict[str, object]:
    return {"ok": True, "provider": "stub", "offline": True}


def cost_estimate(prompt: str, completion: str = "") -> float:
    del prompt, completion
    return 0.0


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Backward-compatible alias to unified ``generate``."""

    return generate(prompt, timeout=timeout)
