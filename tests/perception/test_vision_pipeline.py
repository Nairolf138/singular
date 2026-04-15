from __future__ import annotations

from perception.vision.extractors import UIStateChangeExtractor
from perception.vision.pipeline import VisionPerceptionPipeline
from perception.vision.preprocess import FrameSamplingStrategy


class DummyFrame:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def tobytes(self) -> bytes:
        return self._content

    def __getitem__(self, _item):
        return self


class _TestPipeline(VisionPerceptionPipeline):
    def __init__(self, frame: DummyFrame, **kwargs):
        super().__init__(**kwargs)
        self._frame = frame

    def _capture_frame(self):
        return self._frame


def test_sampling_strategy_throttles_to_configured_fps() -> None:
    sampling = FrameSamplingStrategy(fps=2.0)

    assert sampling.should_sample(now=0.0) is True
    assert sampling.should_sample(now=0.5) is True
    assert sampling.should_sample(now=0.7) is False
    assert sampling.should_sample(now=1.0) is True


def test_pipeline_emits_compact_vision_event_without_raw_image() -> None:
    pipeline = _TestPipeline(
        frame=DummyFrame(b"frame-1"),
        source="window",
    )

    events = pipeline.collect()

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "vision"
    assert "frame_fingerprint" in event.payload
    assert "events" in event.payload
    assert "frame" not in event.payload
    assert "raw_image" not in event.payload


def test_ui_state_change_extractor_flags_changes() -> None:
    extractor = UIStateChangeExtractor(changed_threshold=0.99)

    first = extractor.extract(DummyFrame(b"state-a"))
    second = extractor.extract(DummyFrame(b"state-a"))
    third = extractor.extract(DummyFrame(b"state-b"))

    assert first["changed"] is False
    assert second["changed"] is False
    assert third["changed"] is True
