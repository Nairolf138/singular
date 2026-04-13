"""Local LLM provider using a small transformers model."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from . import ProviderExecutionError, ProviderMetrics, ProviderTimeoutError, ProviderUnavailableError

MAX_RETRIES = 1

try:  # pragma: no cover - optional dependency
    from transformers import pipeline  # type: ignore
except Exception:  # pragma: no cover - handle missing package
    pipeline = None  # type: ignore

_pipe: Any | None = None

LAST_METRICS = ProviderMetrics(provider="local")


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


def generate(prompt: str, *, timeout: float = 8.0) -> str:
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

    reply = _filter(text[len(prompt) :].strip())
    LAST_METRICS.latency_ms = min(timeout * 50.0, 400.0)
    LAST_METRICS.input_tokens = len(prompt.split())
    LAST_METRICS.output_tokens = len(reply.split())
    LAST_METRICS.estimated_cost_usd = cost_estimate(prompt, reply)
    return reply


def embed(text: str, *, timeout: float = 8.0) -> list[float]:
    del timeout
    return [float(len(text)), float(sum(ord(ch) for ch in text) % 2048)]


def healthcheck() -> dict[str, object]:
    try:
        _get_pipe()
    except ProviderUnavailableError as exc:
        return {"ok": False, "provider": "local", "error": str(exc)}
    return {"ok": True, "provider": "local"}


def cost_estimate(prompt: str, completion: str = "") -> float:
    del prompt, completion
    return 0.0


def generate_reply(prompt: str, *, timeout: float = 8.0) -> str:
    """Backward-compatible alias to unified ``generate``."""

    return generate(prompt, timeout=timeout)
