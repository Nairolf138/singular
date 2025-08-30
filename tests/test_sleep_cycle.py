import random

import life.loop as life_loop
from life.loop import run
from singular.psyche import Psyche


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def time(self):
        self.now += 0.2
        return self.now

    def perf_counter(self):
        return self.time()

    def sleep(self, seconds):
        self.now += seconds


def test_sleep_regenerates_energy_without_mutation(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "foo.py").write_text("result = 1", encoding="utf-8")
    checkpoint = tmp_path / "ckpt.json"

    psyche = Psyche(energy=5)
    psyche.save_state = lambda path=None: None
    monkeypatch.setattr(life_loop.Psyche, "load_state", classmethod(lambda cls: psyche))

    calls = {"n": 0}

    def fake_apply(code, operator, rng=None):
        calls["n"] += 1
        return code

    monkeypatch.setattr(life_loop, "apply_mutation", fake_apply)
    monkeypatch.setattr(life_loop, "time", FakeTime())

    run(
        skills_dir,
        checkpoint,
        budget_seconds=0.3,
        rng=random.Random(0),
        operators={"id": lambda tree, rng=None: tree},
    )

    assert psyche.energy > 5
    assert calls["n"] == 0
