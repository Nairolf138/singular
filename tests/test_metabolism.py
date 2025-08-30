from singular.resource_manager import ResourceManager


def test_metabolize(tmp_path):
    rm = ResourceManager(energy=50.0, food=30.0, path=tmp_path / "resources.json")
    rm.metabolize(rate=5.0)
    assert rm.energy == 60.0
    assert rm.food == 25.0
