"""OpenAI LLM provider using the Chat Completions API."""

from __future__ import annotations

import os
from typing import Any

from . import (
    ProviderExecutionError,
    ProviderMetrics,
    ProviderMisconfiguredError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

MAX_RETRIES = 2

LAST_METRICS = ProviderMetrics(provider="openai")

try:  # pragma: no cover - optional dependency
    from openai import (  # type: ignore
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except Exception:  # pragma: no cover - handle missing package
    APIConnectionError = ()  # type: ignore[assignment]
    APITimeoutError = ()  # type: ignore[assignment]
    AuthenticationError = ()  # type: ignore[assignment]
    RateLimitError = ()  # type: ignore[assignment]
    OpenAI = None  # type: ignore[assignment]


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""
    return "".join(ch for ch in text if ch.isprintable())


def generate(prompt: str, *, timeout: float = 8.0) -> str:
    """Generate a reply via OpenAI using typed errors for failures."""

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ProviderMisconfiguredError("OPENAI_API_KEY not configured")
    if OpenAI is None:
        raise ProviderUnavailableError("openai dependency is not installed")

    try:  # pragma: no cover - network call
        client = OpenAI(api_key=api_key)
        response: Any = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            timeout=timeout,
        )
        text: str = response.choices[0].message.content
    except APITimeoutError as exc:
        raise ProviderTimeoutError("OpenAI request timed out") from exc
    except TimeoutError as exc:
        raise ProviderTimeoutError("OpenAI request timed out") from exc
    except RateLimitError as exc:
        raise ProviderQuotaExceededError("OpenAI quota exceeded or rate limited") from exc
    except AuthenticationError as exc:
        raise ProviderMisconfiguredError("OpenAI credentials are invalid") from exc
    except APIConnectionError as exc:
        raise ProviderUnavailableError("Unable to connect to OpenAI") from exc
    except Exception as exc:
        raise ProviderExecutionError("Unexpected OpenAI provider failure") from exc

    filtered = _filter(text)
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    LAST_METRICS.input_tokens = input_tokens or len(prompt.split())
    LAST_METRICS.output_tokens = output_tokens or len(filtered.split())
    LAST_METRICS.estimated_cost_usd = cost_estimate(prompt, filtered, input_tokens=input_tokens, output_tokens=output_tokens)
    LAST_METRICS.latency_ms = min(timeout * 100.0, 800.0)
    return filtered


def embed(text: str, *, timeout: float = 8.0) -> list[float]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ProviderMisconfiguredError("OPENAI_API_KEY not configured")
    if OpenAI is None:
        raise ProviderUnavailableError("openai dependency is not installed")

    try:  # pragma: no cover - network call
        client = OpenAI(api_key=api_key)
        response: Any = client.embeddings.create(model="text-embedding-3-small", input=text, timeout=timeout)
        values = response.data[0].embedding
    except APITimeoutError as exc:
        raise ProviderTimeoutError("OpenAI embedding timed out") from exc
    except TimeoutError as exc:
        raise ProviderTimeoutError("OpenAI embedding timed out") from exc
    except RateLimitError as exc:
        raise ProviderQuotaExceededError("OpenAI quota exceeded or rate limited") from exc
    except AuthenticationError as exc:
        raise ProviderMisconfiguredError("OpenAI credentials are invalid") from exc
    except APIConnectionError as exc:
        raise ProviderUnavailableError("Unable to connect to OpenAI") from exc
    except Exception as exc:
        raise ProviderExecutionError("Unexpected OpenAI embedding failure") from exc

    return [float(v) for v in values]


def healthcheck() -> dict[str, object]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "provider": "openai", "error": "missing OPENAI_API_KEY"}
    return {"ok": OpenAI is not None, "provider": "openai"}


def cost_estimate(
    prompt: str,
    completion: str = "",
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> float:
    in_tokens = input_tokens if input_tokens is not None and input_tokens > 0 else max(1, len(prompt.split()))
    out_tokens = output_tokens if output_tokens is not None and output_tokens > 0 else len(completion.split())
    # Heuristic for gpt-3.5-turbo style pricing approximation.
    return round((in_tokens * 0.0000005) + (out_tokens * 0.0000015), 8)


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Backward-compatible alias to unified ``generate``."""

    return generate(prompt, timeout=timeout)
