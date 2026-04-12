from singular.resource_manager import ResourceManager
from singular.environment.notifications import auto_post, notify


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
