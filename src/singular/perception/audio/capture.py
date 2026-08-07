"""Microphone capture utilities for audio perception."""

from __future__ import annotations

import audioop
from dataclasses import dataclass
from queue import Empty, Queue
from time import monotonic
from typing import Protocol

try:
    import sounddevice as sd  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    sd = None


class AudioCaptureError(RuntimeError):
    """Raised when microphone capture is unavailable or fails."""


@dataclass(frozen=True)
class AudioBlock:
    """One captured PCM block and lightweight energy metadata."""

    pcm16: bytes
    sample_rate: int
    channels: int
    started_at: float
    duration_s: float
    rms: float
    peak: float


class AudioBlockProvider(Protocol):
    """Provider contract for continuous microphone blocks."""

    def next_block(self, *, timeout: float = 0.05) -> AudioBlock | None:
        """Return the next block or ``None`` when no data is available yet."""

    def close(self) -> None:
        """Release capture resources."""


@dataclass
class MicrophoneCapture:
    """Continuous microphone capture based on ``sounddevice.RawInputStream``."""

    sample_rate: int = 16_000
    channels: int = 1
    block_duration_ms: int = 30
    _stream: object | None = None
    _queue: Queue[tuple[bytes, float]] | None = None

    def _ensure_started(self) -> None:
        if self._stream is not None:
            return
        if sd is None:
            raise AudioCaptureError("sounddevice is not installed")

        block_size = max(1, int(self.sample_rate * self.block_duration_ms / 1000))
        queue: Queue[tuple[bytes, float]] = Queue(maxsize=128)

        def _callback(indata, _frames, _time_info, _status) -> None:
            try:
                queue.put_nowait((bytes(indata), monotonic()))
            except Exception:
                pass

        stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=block_size,
            callback=_callback,
        )
        stream.start()
        self._stream = stream
        self._queue = queue

    def next_block(self, *, timeout: float = 0.05) -> AudioBlock | None:
        self._ensure_started()
        assert self._queue is not None
        try:
            pcm16, captured_at = self._queue.get(timeout=timeout)
        except Empty:
            return None

        sample_width = 2
        frame_count = max(1, len(pcm16) // (sample_width * max(self.channels, 1)))
        duration = frame_count / float(self.sample_rate)
        started_at = captured_at - duration

        rms = float(audioop.rms(pcm16, sample_width)) / 32768.0
        peak = float(audioop.max(pcm16, sample_width)) / 32768.0
        return AudioBlock(
            pcm16=pcm16,
            sample_rate=self.sample_rate,
            channels=self.channels,
            started_at=started_at,
            duration_s=duration,
            rms=max(0.0, min(1.0, rms)),
            peak=max(0.0, min(1.0, peak)),
        )

    def close(self) -> None:
        stream = self._stream
        self._stream = None
        self._queue = None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
