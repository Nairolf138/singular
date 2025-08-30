from singular.resource_manager import ResourceManager


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
