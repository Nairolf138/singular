import logging
from graine.evolver.dsl import Patch
from graine.evolver.select import Candidate, select


def build_patch(**overrides):
    data = {
        "type": "Patch",
        "target": {"file": "dummy.py", "function": "foo"},
        "ops": [{"op": "CONST_TUNE", "delta": 0.0, "bounds": [-0.1, 0.1]}],
        "theta_diff": 1,
        "purity": True,
        "cyclomatic": 1,
    }
    data.update(overrides)
    return Patch.from_dict(data)


def test_select_accepts_only_best_candidate(caplog):
    caplog.set_level(logging.INFO)
    thresholds = {"tests": True, "perf": True, "quality": True, "stability": True}
    c1 = Candidate(build_patch(), {"err": 1, "time": 1}, thresholds, name="A")
    c2 = Candidate(build_patch(), {"err": 2, "time": 2}, thresholds, name="B")

    chosen = select([c1, c2])
    assert chosen is c1
    accepted = [r for r in caplog.records if "Accepted patch" in r.message]
    rejected = [r for r in caplog.records if "Rejected patch" in r.message]
    assert len(accepted) == 1
    assert any("A" in r.message for r in accepted)
    assert any("B" in r.message and "dominated" in r.message for r in rejected)


def test_select_retains_prev_best(caplog):
    caplog.set_level(logging.INFO)
    thresholds = {"tests": True, "perf": True, "quality": True, "stability": True}
    prev = Candidate(build_patch(), {"err": 1, "time": 1}, thresholds, name="Prev")
    new = Candidate(build_patch(), {"err": 2, "time": 2}, thresholds, name="New")

    chosen = select([new], prev_best=prev)
    assert chosen is prev
    assert any("Accepted patch Prev" in r.message for r in caplog.records)
    assert any("Rejected patch New" in r.message for r in caplog.records)


def test_select_replaces_dominated_prev_best(caplog):
    caplog.set_level(logging.INFO)
    thresholds = {"tests": True, "perf": True, "quality": True, "stability": True}
    prev = Candidate(build_patch(), {"err": 2, "time": 2}, thresholds, name="Prev")
    new = Candidate(build_patch(), {"err": 1, "time": 1}, thresholds, name="New")

    chosen = select([new], prev_best=prev)
    assert chosen is new
    assert any("Accepted patch New" in r.message for r in caplog.records)
    assert any("Rejected patch Prev" in r.message for r in caplog.records)


def test_select_filters_on_thresholds(caplog):
    caplog.set_level(logging.INFO)
    good = Candidate(
        build_patch(),
        {"err": 1, "time": 1},
        {"tests": True, "perf": True, "quality": True, "stability": True},
        name="Good",
    )
    bad = Candidate(
        build_patch(),
        {"err": 0.5, "time": 0.5},
        {"tests": True, "perf": False, "quality": True, "stability": True},
        name="Bad",
    )

    chosen = select([good, bad])
    assert chosen is good
    assert any("Rejected patch Bad: failed thresholds" in r.message for r in caplog.records)
