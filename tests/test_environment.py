import time

from singular.resource_manager import ResourceManager
from singular.environment.notifications import auto_post, notify
from singular.perception import PerceptionNoiseFilter


def test_update_from_environment_increases_warmth(tmp_path):
    path = tmp_path / "resources.json"
    rm = ResourceManager(warmth=50.0, path=path)
    rm.update_from_environment(30.0)
    assert rm.warmth > 50.0


def test_update_from_environment_decreases_warmth(tmp_path):
    path = tmp_path / "resources.json"
    rm = ResourceManager(warmth=50.0, path=path)
    rm.update_from_environment(10.0)
    assert rm.warmth < 50.0


def test_notify_supports_levels_and_actions() -> None:
    messages: list[str] = []
    notify(
        "hausse des échecs sandbox",
        channel=messages.append,
        level="critical",
        action="changer opérateurs",
    )
    assert messages == [
        "[CRITICAL] hausse des échecs sandbox — action recommandée: changer opérateurs"
    ]


def test_auto_post_defaults_action_for_warning() -> None:
    messages: list[str] = []
    auto_post(messages.append, "baisse continue du health score", level="warning")
    assert messages == [
        "[WARNING] baisse continue du health score — action recommandée: réduire exploration"
    ]


def test_perception_noise_filter_threshold_dedup_and_cooldown() -> None:
    noise_filter = PerceptionNoiseFilter(confidence_threshold=0.5, cooldown_seconds=0.1)
    weak = {
        "type": "artifact.logs.new",
        "source": "sandbox",
        "confidence": 0.1,
        "data": {"count": 1},
    }
    strong = {
        "type": "artifact.logs.new",
        "source": "sandbox",
        "confidence": 0.9,
        "data": {"count": 1},
    }

    assert noise_filter.allow(weak) is False
    assert noise_filter.allow(strong) is True
    # Dedup: same payload is filtered while still in seen cache.
    assert noise_filter.allow(strong) is False

    time.sleep(0.11)
    # New payload after cooldown can pass.
    new_payload = {
        "type": "artifact.logs.new",
        "source": "sandbox",
        "confidence": 0.9,
        "data": {"count": 2},
    }
    assert noise_filter.allow(new_payload) is True
