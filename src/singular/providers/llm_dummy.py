"""Dummy LLM provider for tests and offline usage."""

from __future__ import annotations


def generate_reply(prompt: str) -> str:
    """Return a simple echoed reply for ``prompt``."""
    return f"Echo: {prompt}"
