from __future__ import annotations

from dataclasses import dataclass

from perception.audio.capture import AudioBlock, AudioBlockProvider
from perception.audio.pipeline import AudioPerceptionPipeline
from perception.audio.transcribe import WhisperRuntime


@dataclass
class StaticAudioProvider(AudioBlockProvider):
    blocks: list[AudioBlock]

    def next_block(self, *, timeout: float = 0.05) -> AudioBlock | None:
        if not self.blocks:
            return None
        return self.blocks.pop(0)

    def close(self) -> None:
        return None


class DummyTranscriber:
    runtime = WhisperRuntime(device="cpu", model_size="tiny", backend="whisper", fallback_applied=True)

    def transcribe(self, blocks):
        start = blocks[0].started_at
        end = blocks[-1].started_at + blocks[-1].duration_s
        return {
            "text": "bonjour le monde",
            "segments": [{"start": 0.0, "end": round(end - start, 3), "text": "bonjour le monde", "confidence": 0.86}],
            "confidence": 0.86,
            "status": "ok",
            "runtime": self.runtime.__dict__,
        }


def _block(rms: float, t: float) -> AudioBlock:
    amp = int(max(0.0, min(1.0, rms)) * 32767)
    sample = amp.to_bytes(2, byteorder="little", signed=True)
    pcm = sample * 480
    return AudioBlock(
        pcm16=pcm,
        sample_rate=16_000,
        channels=1,
        started_at=t,
        duration_s=0.03,
        rms=rms,
        peak=rms,
    )


def test_audio_pipeline_emits_meta_and_transcript_events() -> None:
    blocks = [
        _block(0.005, 0.00),
        _block(0.004, 0.03),
        _block(0.09, 0.06),
        _block(0.10, 0.09),
        _block(0.11, 0.12),
        _block(0.004, 0.15),
        _block(0.004, 0.18),
        _block(0.004, 0.21),
        _block(0.004, 0.24),
        _block(0.004, 0.27),
        _block(0.004, 0.30),
    ]

    pipeline = AudioPerceptionPipeline(
        capture=StaticAudioProvider(blocks=blocks),
        transcriber=DummyTranscriber(),
    )

    produced = []
    while True:
        events = pipeline.collect()
        if not events and not pipeline.capture.blocks:
            break
        produced.extend(events)

    assert any(evt.event_type == "audio_meta" for evt in produced)
    transcripts = [evt for evt in produced if evt.event_type == "transcript"]
    assert len(transcripts) == 1
    assert transcripts[0].payload["text"] == "bonjour le monde"
    assert transcripts[0].payload["segments"][0]["start"] == 0.0


def test_audio_meta_exposes_runtime_fallback_flags() -> None:
    pipeline = AudioPerceptionPipeline(
        capture=StaticAudioProvider(blocks=[_block(0.02, 1.0)]),
        transcriber=DummyTranscriber(),
    )

    events = pipeline.collect()
    assert len(events) == 1
    assert events[0].event_type == "audio_meta"
    assert events[0].payload["runtime"]["fallback_applied"] is True
