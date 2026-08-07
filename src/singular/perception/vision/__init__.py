"""Vision perception stack producing compact :class:`PerceptEvent` objects.

The package avoids persisting raw image buffers in events. It keeps transient
frames in memory, then emits compact summaries (hashes, counts, labels, text
snippets) under ``event_type='vision'``.
"""

from .capture import CameraCapture, ScreenCapture
from .extractors import (
    KeyObjectExtractor,
    OcrTextExtractor,
    UIStateChangeExtractor,
    VisionEventExtractor,
)
from .pipeline import VisionPerceptionPipeline
from .preprocess import FramePreprocessor, FrameSamplingStrategy, RegionOfInterest

__all__ = [
    "CameraCapture",
    "FramePreprocessor",
    "FrameSamplingStrategy",
    "KeyObjectExtractor",
    "OcrTextExtractor",
    "RegionOfInterest",
    "ScreenCapture",
    "UIStateChangeExtractor",
    "VisionEventExtractor",
    "VisionPerceptionPipeline",
]
