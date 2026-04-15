"""Vision perception pipeline emitting compact ``PerceptEvent(type='vision')``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from singular.core.agent_runtime import PerceptEvent

from .capture import ActiveWindowCapture, CameraCapture, ScreenCapture, VisionCaptureError
from .extractors import KeyObjectExtractor, OcrTextExtractor, UIStateChangeExtractor, VisionEventExtractor
from .preprocess import FramePreprocessor, FrameSamplingStrategy


@dataclass
class VisionPerceptionPipeline:
    """Capture, preprocess, extract and emit compact vision percepts."""

    source: str = "screen"
    source_name: str = "vision.pipeline"
    sampling: FrameSamplingStrategy = field(default_factory=lambda: FrameSamplingStrategy(fps=1.5))
    preprocessor: FramePreprocessor = field(default_factory=FramePreprocessor)
    extractors: list[VisionEventExtractor] = field(
        default_factory=lambda: [OcrTextExtractor(), KeyObjectExtractor(), UIStateChangeExtractor()]
    )

    def collect(self) -> list[PerceptEvent]:
        """Collect at most one sampled frame and return compact vision events."""

        if not self.sampling.should_sample():
            return []

        try:
            frame = self._capture_frame()
            processed = self.preprocessor.preprocess(frame)
        except VisionCaptureError as exc:
            return [
                PerceptEvent(
                    event_type="vision",
                    source=self.source_name,
                    payload={"status": "capture_error", "error": str(exc)},
                )
            ]

        payload: dict[str, Any] = {
            "status": "ok",
            "source": self.source,
            "frame_fingerprint": self.preprocessor.frame_fingerprint(processed),
            "sampling_fps": self.sampling.fps,
            "events": {},
        }
        for extractor in self.extractors:
            payload["events"][extractor.__class__.__name__] = extractor.extract(processed)

        return [
            PerceptEvent(
                event_type="vision",
                source=self.source_name,
                payload=payload,
            )
        ]

    def _capture_frame(self) -> Any:
        if self.source == "camera":
            return CameraCapture().grab_frame()
        if self.source == "window":
            return ActiveWindowCapture().grab_frame()
        return ScreenCapture().grab_frame()
