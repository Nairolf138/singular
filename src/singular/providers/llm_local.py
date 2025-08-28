"""Local LLM provider using a small transformers model."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    from transformers import pipeline  # type: ignore
except Exception:  # pragma: no cover - handle missing package
    pipeline = None  # type: ignore

_pipe: Any | None = None


def _get_pipe() -> Any | None:
    """Return a cached text generation pipeline or ``None`` if unavailable."""
    global _pipe
    if pipeline is None:
        return None
    if _pipe is None:
        try:  # pragma: no cover - model download
            _pipe = pipeline("text-generation", model="sshleifer/tiny-gpt2")
        except Exception:
            _pipe = None
    return _pipe


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""
    return "".join(ch for ch in text if ch.isprintable())


def generate_reply(prompt: str) -> str:
    """Generate a reply using a small local transformers model."""
    pipe = _get_pipe()
    if pipe is None:
        return "Local model not available."
    try:  # pragma: no cover - model inference
        outputs = pipe(prompt, max_new_tokens=50, num_return_sequences=1)
        text: str = outputs[0]["generated_text"]
    except Exception:
        return "Error running local model."
    # ``text`` includes the original prompt at the beginning
    reply = text[len(prompt) :].strip()
    return _filter(reply)
