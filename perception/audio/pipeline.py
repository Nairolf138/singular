"""Audio perception pipeline: continuous capture, VAD, segment buffer and STT."""

from __future__ import annotations

from dataclasses import dataclass, field

from singular.core.agent_runtime import PerceptEvent

from .capture import AudioBlockProvider, MicrophoneCapture
from .transcribe import WhisperTranscriber
from .vad import EnergyVAD, SegmentBuffer


@dataclass
class AudioPerceptionPipeline:
    """Collect audio blocks continuously and emit transcript/audio metadata events."""

    source_name: str = "audio.pipeline"
    capture: AudioBlockProvider = field(default_factory=MicrophoneCapture)
    vad: EnergyVAD = field(default_factory=EnergyVAD)
    transcriber: WhisperTranscriber = field(default_factory=WhisperTranscriber)
    segment_buffer: SegmentBuffer = field(default_factory=SegmentBuffer)
    _noise_floor: float = field(default=0.01, init=False, repr=False)
    _speaking: bool = field(default=False, init=False, repr=False)

    def collect(self) -> list[PerceptEvent]:
        block = self.capture.next_block()
        if block is None:
            return []

        is_speech, speech_started, speech_ended, vad_confidence = self.vad.process(
            block,
            noise_floor=self._noise_floor,
        )

        if not is_speech:
            self._noise_floor = (self._noise_floor * 0.95) + (block.rms * 0.05)

        if speech_started:
            self._speaking = True
            self.segment_buffer.flush()
        if self._speaking:
            self.segment_buffer.add(block)

        events: list[PerceptEvent] = []
        runtime = self.transcriber.runtime
        events.append(
            PerceptEvent(
                event_type="audio_meta",
                source=self.source_name,
                payload={
                    "volume": round(block.rms, 4),
                    "peak": round(block.peak, 4),
                    "noise": round(self._noise_floor, 4),
                    "confidence": vad_confidence,
                    "speech": is_speech,
                    "runtime": runtime.__dict__,
                },
            )
        )

        if speech_ended and self._speaking:
            self._speaking = False
            segment = self.segment_buffer.flush()
            if segment:
                transcript = self.transcriber.transcribe(segment)
                events.append(
                    PerceptEvent(
                        event_type="transcript",
                        source=self.source_name,
                        payload={
                            "text": transcript.get("text", ""),
                            "segments": transcript.get("segments", []),
                            "confidence": transcript.get("confidence", 0.0),
                            "status": transcript.get("status", "ok"),
                            "runtime": transcript.get("runtime", runtime.__dict__),
                            "start": round(segment[0].started_at, 3),
                            "end": round(segment[-1].started_at + segment[-1].duration_s, 3),
                        },
                    )
                )

        return events

    def close(self) -> None:
        self.capture.close()
