"""Transient frame capture providers for camera, screen and active window."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import mss  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    mss = None

try:
    import pygetwindow as gw  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    gw = None


class VisionCaptureError(RuntimeError):
    """Raised when a capture source cannot be initialized or read."""


@dataclass
class CameraCapture:
    """OpenCV-based camera frame capture."""

    camera_index: int = 0

    def grab_frame(self) -> Any:
        if cv2 is None:
            raise VisionCaptureError("opencv-python is not installed")

        camera = cv2.VideoCapture(self.camera_index)
        try:
            ok, frame = camera.read()
        finally:
            camera.release()

        if not ok:
            raise VisionCaptureError(f"unable to read camera index={self.camera_index}")
        return frame


@dataclass
class ScreenCapture:
    """Capture display content via ``mss``."""

    monitor_index: int = 1

    def grab_frame(self) -> Any:
        if mss is None:
            raise VisionCaptureError("mss is not installed")

        with mss.mss() as sct:
            monitors = sct.monitors
            if self.monitor_index >= len(monitors):
                raise VisionCaptureError(
                    f"monitor index out of range: {self.monitor_index} (available={len(monitors)-1})"
                )
            shot = sct.grab(monitors[self.monitor_index])
        return shot


@dataclass
class ActiveWindowCapture:
    """Capture only the currently active window when available."""

    fallback_monitor_index: int = 1

    def grab_frame(self) -> Any:
        if mss is None:
            raise VisionCaptureError("mss is not installed")

        region: dict[str, int] | None = None
        if gw is not None:
            window = gw.getActiveWindow()
            if window is not None:
                region = {
                    "left": max(int(window.left), 0),
                    "top": max(int(window.top), 0),
                    "width": max(int(window.width), 1),
                    "height": max(int(window.height), 1),
                }

        with mss.mss() as sct:
            if region is None:
                monitors = sct.monitors
                if self.fallback_monitor_index >= len(monitors):
                    raise VisionCaptureError(
                        "no active window and fallback monitor index is out of range"
                    )
                region = monitors[self.fallback_monitor_index]
            shot = sct.grab(region)
        return shot
