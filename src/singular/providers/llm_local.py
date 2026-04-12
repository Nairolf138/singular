"""Local LLM provider using a small transformers model."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from . import ProviderExecutionError, ProviderTimeoutError, ProviderUnavailableError

MAX_RETRIES = 1

try:  # pragma: no cover - optional dependency
    from transformers import pipeline  # type: ignore
except Exception:  # pragma: no cover - handle missing package
    pipeline = None  # type: ignore

_pipe: Any | None = None


def _get_pipe() -> Any:
    """Return a cached text generation pipeline or raise an availability error."""

    global _pipe
    if pipeline is None:
        raise ProviderUnavailableError("transformers is not installed")
    if _pipe is None:
        try:  # pragma: no cover - model download
            _pipe = pipeline("text-generation", model="sshleifer/tiny-gpt2")
        except Exception as exc:
            raise ProviderUnavailableError("Local model is unavailable") from exc
    return _pipe


def _filter(text: str) -> str:
    """Return only printable characters from ``text``."""

    return "".join(ch for ch in text if ch.isprintable())


def _infer(pipe: Any, prompt: str) -> str:
    outputs = pipe(prompt, max_new_tokens=50, num_return_sequences=1)
    text: str = outputs[0]["generated_text"]
    return text


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Generate a reply using a small local transformers model."""

    pipe = _get_pipe()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_infer, pipe, prompt)
            text = future.result(timeout=timeout)
    except FutureTimeoutError as exc:
        raise ProviderTimeoutError("Local model inference timed out") from exc
    except ProviderTimeoutError:
        raise
    except Exception as exc:
        raise ProviderExecutionError("Error running local model") from exc

    reply = text[len(prompt) :].strip()
    return _filter(reply)
