"""OpenAI LLM provider using the Chat Completions API.

This module targets the ``openai`` package version 1.x which exposes the
``OpenAI`` client.  Older versions using ``openai.ChatCompletion`` are not
supported.
"""

from __future__ import annotations

import os
from typing import Any

try:  # pragma: no cover - optional dependency
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - handle missing package
    OpenAI = None  # type: ignore


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""
    return "".join(ch for ch in text if ch.isprintable())


def generate_reply(prompt: str) -> str:
    """Generate a reply via OpenAI if an API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        return "OpenAI API key not configured."

    try:  # pragma: no cover - network call
        client = OpenAI(api_key=api_key)
        response: Any = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
        )
        text: str = response.choices[0].message.content
    except Exception:
        return "Error communicating with OpenAI."

    return _filter(text)
