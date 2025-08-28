"""OpenAI LLM provider using the ChatCompletion API."""

from __future__ import annotations

import os
from typing import Any

try:  # pragma: no cover - optional dependency
    import openai  # type: ignore
except Exception:  # pragma: no cover - handle missing package
    openai = None  # type: ignore


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""
    return "".join(ch for ch in text if ch.isprintable())


def generate_reply(prompt: str) -> str:
    """Generate a reply via OpenAI if an API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or openai is None:
        return "OpenAI API key not configured."

    openai.api_key = api_key
    try:  # pragma: no cover - network call
        response: Any = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
        )
        text: str = response["choices"][0]["message"]["content"]
    except Exception:
        return "Error communicating with OpenAI."

    return _filter(text)
