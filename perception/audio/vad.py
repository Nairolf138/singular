"""Energy-based voice activity detection and speech segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .capture import AudioBlock


@dataclass
class EnergyVAD:
    """Simple VAD using block RMS with speech start/stop hysteresis."""

    start_threshold: float = 0.03
    stop_threshold: float = 0.015
    noise_boost: float = 2.8
    min_speech_blocks: int = 2
    silence_blocks_to_stop: int = 6
    _speech_blocks: int = field(default=0, init=False, repr=False)
    _silence_blocks: int = field(default=0, init=False, repr=False)
    _speaking: bool = field(default=False, init=False, repr=False)

    def process(self, block: AudioBlock, *, noise_floor: float) -> tuple[bool, bool, bool, float]:
        """Return ``(is_speech, speech_started, speech_ended, confidence)``."""

        adaptive_start = max(self.start_threshold, noise_floor * self.noise_boost)
        adaptive_stop = max(self.stop_threshold, adaptive_start * 0.5)
        energy = block.rms
        is_speech = energy >= (adaptive_stop if self._speaking else adaptive_start)

        speech_started = False
        speech_ended = False
        if is_speech:
            self._speech_blocks += 1
            self._silence_blocks = 0
            if not self._speaking and self._speech_blocks >= self.min_speech_blocks:
                self._speaking = True
                speech_started = True
        else:
            self._silence_blocks += 1
            self._speech_blocks = 0
            if self._speaking and self._silence_blocks >= self.silence_blocks_to_stop:
                self._speaking = False
                speech_ended = True

        confidence = 0.0
        if adaptive_start > 0:
            confidence = max(0.0, min(1.0, (energy - noise_floor) / adaptive_start))
        return is_speech, speech_started, speech_ended, round(confidence, 4)


@dataclass
class SegmentBuffer:
    """Accumulate blocks while speech is active and flush completed segments."""

    _active: list[AudioBlock] = field(default_factory=list, init=False, repr=False)

    def add(self, block: AudioBlock) -> None:
        self._active.append(block)

    def flush(self) -> list[AudioBlock]:
        segment = self._active
        self._active = []
        return segment
