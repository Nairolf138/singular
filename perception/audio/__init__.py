"""Audio perception stack with VAD, segmentation and local Whisper STT."""

from .capture import AudioBlock, AudioBlockProvider, AudioCaptureError, MicrophoneCapture
from .pipeline import AudioPerceptionPipeline
from .transcribe import WhisperRuntime, WhisperTranscriber
from .vad import EnergyVAD, SegmentBuffer

__all__ = [
    "AudioBlock",
    "AudioBlockProvider",
    "AudioCaptureError",
    "AudioPerceptionPipeline",
    "EnergyVAD",
    "MicrophoneCapture",
    "SegmentBuffer",
    "WhisperRuntime",
    "WhisperTranscriber",
]
