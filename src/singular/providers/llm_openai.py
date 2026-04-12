"""OpenAI LLM provider using the Chat Completions API."""

from __future__ import annotations

import os
from typing import Any

from . import (
    ProviderExecutionError,
    ProviderMisconfiguredError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

MAX_RETRIES = 2

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


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
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

    return _filter(text)
