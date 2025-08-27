import json
import pytest
import random
from pathlib import Path

from graine.meta.dsl import MetaSpec, MetaValidationError, MAX_POPULATION_CAP
from graine.meta.evolve import propose_mutation
from graine.meta.phantom import replay_snapshots
from graine.kernel.verifier import DIFF_LIMIT


def build_spec(**overrides):
    data = {
        "weights": {"perf": 0.5, "robust": 0.5},
        "operator_mix": {"CONST_TUNE": 0.5, "EQ_REWRITE": 0.5},
        "population_cap": 10,
        "selection_strategy": "elitism",
    }
    data.update(overrides)
    return MetaSpec.from_dict(data)


def test_meta_rejects_bad_weights():
    spec = build_spec(weights={"perf": 0.7, "robust": 0.2})
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_unknown_operator():
    spec = build_spec(operator_mix={"CONST_TUNE": 0.5, "BAD_OP": 0.5})
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_excess_population():
    spec = build_spec(population_cap=MAX_POPULATION_CAP + 1)
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_bad_selection_strategy():
    spec = build_spec(selection_strategy="bad")
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_diff_max_relaxation():
    spec = build_spec(diff_max=DIFF_LIMIT + 1)
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_forbidden_relaxation():
    spec = build_spec(forbidden=["net"]) 
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_phantom_rejects_invalid_snapshot(tmp_path: Path):
    bad_meta = {
        "weights": {"perf": 1.0},
        "operator_mix": {"CONST_TUNE": 1.0},
        "population_cap": MAX_POPULATION_CAP + 1,
    }
    snap = tmp_path / "bad.json"
    snap.write_text(json.dumps({"meta": bad_meta, "history": [{"err": 0.5, "cost": 0.5}]}))
    with pytest.raises(MetaValidationError):
        replay_snapshots(1, directory=tmp_path)


def test_replay_snapshots_returns_metrics(tmp_path: Path):
    meta = build_spec().__dict__
    hist1 = [{"err": 0.5, "cost": 0.4}, {"err": 0.3, "cost": 0.2}]
    hist2 = [{"err": 0.4, "cost": 0.3}, {"err": 0.2, "cost": 0.1}]
    (tmp_path / "r1.json").write_text(json.dumps({"meta": meta, "history": hist1}))
    (tmp_path / "r2.json").write_text(json.dumps({"meta": meta, "history": hist2}))
    metrics = replay_snapshots(2, directory=tmp_path)
    assert metrics["robustness"] == pytest.approx((0.3 + 0.2) / 2)
    assert metrics["safety"] == pytest.approx((0.2 + 0.1) / 2)


def test_replay_snapshots_detects_regression(tmp_path: Path):
    meta = build_spec().__dict__
    hist = [{"err": 0.1, "cost": 0.1}, {"err": 0.2, "cost": 0.1}]
    (tmp_path / "r.json").write_text(json.dumps({"meta": meta, "history": hist}))
    with pytest.raises(RuntimeError):
        replay_snapshots(1, directory=tmp_path)


def test_propose_mutation_produces_valid_spec():
    spec = build_spec()
    mutated = propose_mutation(spec, rng=random.Random(0))
    assert mutated.validate()
    assert abs(sum(mutated.weights.values()) - 1.0) < 1e-6
    assert abs(sum(mutated.operator_mix.values()) - 1.0) < 1e-6


def test_propose_mutation_obeys_population_ceiling():
    spec = build_spec(population_cap=MAX_POPULATION_CAP)
    mutated = propose_mutation(spec, rng=random.Random(1))
    assert mutated.population_cap <= MAX_POPULATION_CAP
