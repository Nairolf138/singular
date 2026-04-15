"""Local Whisper transcription with CPU fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .capture import AudioBlock


@dataclass(frozen=True)
class WhisperRuntime:
    """Resolved runtime configuration for Whisper inference."""

    device: str
    model_size: str
    backend: str
    fallback_applied: bool = False


@dataclass
class WhisperTranscriber:
    """Best-effort local Whisper transcriber with GPU->CPU fallback."""

    prefer_gpu: bool = True
    gpu_model_size: str = "small"
    cpu_model_size: str = "tiny"
    _runtime: WhisperRuntime | None = None
    _model: Any = None

    @property
    def runtime(self) -> WhisperRuntime:
        if self._runtime is None:
            self._runtime = self._load_runtime()
            self._model = self._load_model(self._runtime)
        return self._runtime

    def _load_runtime(self) -> WhisperRuntime:
        gpu_available = self._gpu_available() if self.prefer_gpu else False
        device = "cuda" if gpu_available else "cpu"
        model_size = self.gpu_model_size if gpu_available else self.cpu_model_size
        return WhisperRuntime(device=device, model_size=model_size, backend="whisper")

    def _gpu_available(self) -> bool:
        try:  # pragma: no cover - optional dependency
            import torch  # type: ignore

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    def _load_model(self, runtime: WhisperRuntime) -> Any:
        try:  # pragma: no cover - optional dependency
            import whisper  # type: ignore

            return whisper.load_model(runtime.model_size, device=runtime.device)
        except Exception:
            if runtime.device == "cuda":
                cpu_runtime = WhisperRuntime(
                    device="cpu",
                    model_size=self.cpu_model_size,
                    backend="whisper",
                    fallback_applied=True,
                )
                try:  # pragma: no cover - optional dependency
                    import whisper  # type: ignore

                    self._runtime = cpu_runtime
                    return whisper.load_model(cpu_runtime.model_size, device=cpu_runtime.device)
                except Exception:
                    self._runtime = WhisperRuntime(
                        device="cpu",
                        model_size=self.cpu_model_size,
                        backend="unavailable",
                        fallback_applied=True,
                    )
                    return None
            self._runtime = WhisperRuntime(
                device="cpu",
                model_size=self.cpu_model_size,
                backend="unavailable",
                fallback_applied=runtime.fallback_applied,
            )
            return None

    def transcribe(self, blocks: list[AudioBlock]) -> dict[str, Any]:
        runtime = self.runtime
        if not blocks:
            return {"text": "", "segments": [], "confidence": 0.0, "runtime": runtime.__dict__}

        if self._model is None:
            return {
                "text": "",
                "segments": [],
                "confidence": 0.0,
                "status": "unavailable",
                "runtime": runtime.__dict__,
            }

        pcm = b"".join(block.pcm16 for block in blocks)
        sample_rate = blocks[0].sample_rate

        try:  # pragma: no cover - optional dependency
            result = self._model.transcribe(pcm, language="fr", fp16=(runtime.device == "cuda"))
        except Exception:
            return {
                "text": "",
                "segments": [],
                "confidence": 0.0,
                "status": "error",
                "runtime": runtime.__dict__,
            }

        text = str(result.get("text", "")).strip()
        segments = []
        confidences: list[float] = []
        for item in result.get("segments", []):
            conf = float(item.get("avg_logprob", 0.0))
            norm_conf = max(0.0, min(1.0, (conf + 1.5) / 1.5))
            confidences.append(norm_conf)
            segments.append(
                {
                    "start": round(float(item.get("start", 0.0)), 3),
                    "end": round(float(item.get("end", 0.0)), 3),
                    "text": str(item.get("text", "")).strip(),
                    "confidence": round(norm_conf, 4),
                }
            )

        confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        return {
            "text": text,
            "segments": segments,
            "confidence": confidence,
            "sample_rate": sample_rate,
            "runtime": runtime.__dict__,
            "status": "ok",
        }
