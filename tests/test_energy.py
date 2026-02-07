from singular.life.death import DeathMonitor
from singular.psyche import Psyche


def test_energy_persistence(tmp_path):
    path = tmp_path / "psyche.json"
    psyche = Psyche()
    psyche.consume(10)
    psyche.save_state(path)
    loaded = Psyche.load_state(path)
    assert loaded.energy == psyche.energy
    loaded.gain(5)
    assert loaded.energy == psyche.energy + 5


def test_energy_death():
    psyche = Psyche(energy=1.0)
    monitor = DeathMonitor(max_age=99, max_failures=99, min_trait=0.0)
    dead, _ = monitor.check(0, psyche, success=True)
    assert not dead
    psyche.consume(1.0)
    dead, reason = monitor.check(1, psyche, success=True)
    assert dead and reason == "energy depleted"
