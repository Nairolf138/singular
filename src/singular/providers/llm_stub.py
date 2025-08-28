"""Rule-based stub LLM provider for offline usage."""

from __future__ import annotations

import re


def generate_reply(prompt: str) -> str:
    """Generate a deterministic reply without network access."""
    text = prompt.strip().lower()
    if re.search(r"\b(hi|hello|salut|bonjour)\b", text):
        return "Hello!"
    if text.endswith("?"):
        return "I'm not sure about that."
    return f"You said: {prompt}"
