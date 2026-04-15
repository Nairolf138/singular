"""Extract compact vision events from transient frames."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from hashlib import sha1
from typing import Any, Protocol

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pytesseract = None


class VisionEventExtractor(Protocol):
    """Extractor contract returning compact metadata for one frame."""

    def extract(self, frame: Any) -> dict[str, Any]:
        """Return compact extracted features."""


@dataclass
class OcrTextExtractor:
    """OCR extractor returning a short text snippet and confidence proxies."""

    max_chars: int = 240

    def extract(self, frame: Any) -> dict[str, Any]:
        if pytesseract is None:
            return {"available": False, "text": ""}
        text = pytesseract.image_to_string(frame).strip()
        snippet = " ".join(text.split())[: self.max_chars]
        return {
            "available": True,
            "text": snippet,
            "length": len(snippet),
            "has_text": bool(snippet),
        }


@dataclass
class KeyObjectExtractor:
    """Lightweight object cue extractor based on contour count and motion edges."""

    min_area: int = 900

    def extract(self, frame: Any) -> dict[str, Any]:
        if cv2 is None:
            return {"available": False, "key_objects": []}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 80, 160)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes: list[dict[str, int]] = []
        for contour in contours:
            area = int(cv2.contourArea(contour))
            if area < self.min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h), "area": area})

        boxes = sorted(boxes, key=lambda item: item["area"], reverse=True)[:5]
        return {
            "available": True,
            "count": len(boxes),
            "key_objects": boxes,
        }


@dataclass
class UIStateChangeExtractor:
    """Detect meaningful UI state changes via frame fingerprint diffing."""

    changed_threshold: float = 0.94
    _previous_hash: str | None = field(default=None, init=False, repr=False)

    def extract(self, frame: Any) -> dict[str, Any]:
        payload = frame.tobytes() if hasattr(frame, "tobytes") else bytes(str(frame), "utf-8")
        fingerprint = sha1(payload).hexdigest()[:16]

        if self._previous_hash is None:
            self._previous_hash = fingerprint
            return {"changed": False, "change_ratio": 0.0, "ui_state": fingerprint}

        similarity = SequenceMatcher(None, self._previous_hash, fingerprint).ratio()
        changed = similarity < self.changed_threshold
        self._previous_hash = fingerprint
        return {
            "changed": changed,
            "change_ratio": round(1.0 - similarity, 4),
            "ui_state": fingerprint,
        }
