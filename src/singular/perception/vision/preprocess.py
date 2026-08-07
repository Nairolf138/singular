"""Frame preprocessing and sampling utilities for vision perception."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha1
from time import monotonic
from typing import Any

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None


@dataclass(frozen=True)
class RegionOfInterest:
    """Rectangular ROI in pixel coordinates."""

    x: int
    y: int
    width: int
    height: int


@dataclass
class FrameSamplingStrategy:
    """Throttle frame processing to a bounded FPS budget."""

    fps: float = 1.5
    _last_sample_at: float | None = field(default=None, init=False, repr=False)

    def should_sample(self, *, now: float | None = None) -> bool:
        """Return ``True`` only when enough time elapsed since last sample."""

        if self.fps <= 0:
            return False
        current = monotonic() if now is None else now
        if self._last_sample_at is None:
            self._last_sample_at = current
            return True
        min_interval = 1.0 / self.fps
        if (current - self._last_sample_at) >= min_interval:
            self._last_sample_at = current
            return True
        return False


@dataclass
class FramePreprocessor:
    """Apply ROI cropping and resize in-memory before extraction."""

    target_width: int = 640
    target_height: int = 360
    roi: RegionOfInterest | None = None

    def preprocess(self, frame: Any) -> Any:
        """Return processed frame (no persistence)."""

        cropped = self._apply_roi(frame)
        return self._resize(cropped)

    def frame_fingerprint(self, frame: Any) -> str:
        """Compute a compact stable frame fingerprint."""

        payload = frame.tobytes() if hasattr(frame, "tobytes") else bytes(str(frame), "utf-8")
        return sha1(payload).hexdigest()[:16]

    def _apply_roi(self, frame: Any) -> Any:
        if self.roi is None:
            return frame
        x, y, w, h = self.roi.x, self.roi.y, self.roi.width, self.roi.height
        if hasattr(frame, "__getitem__"):
            return frame[y : y + h, x : x + w]
        return frame

    def _resize(self, frame: Any) -> Any:
        if cv2 is None or self.target_width <= 0 or self.target_height <= 0:
            return frame
        return cv2.resize(frame, (self.target_width, self.target_height))
