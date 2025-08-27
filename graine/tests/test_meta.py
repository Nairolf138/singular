import pytest
import random

from graine.meta.dsl import MetaSpec, MetaValidationError, MAX_POPULATION_CAP
from graine.meta.evolve import propose_mutation
from graine.meta.phantom import replay
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


def test_meta_rejects_excess_diff_max():
    spec = build_spec(diff_max=DIFF_LIMIT + 1)
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_meta_rejects_forbidden_relaxation():
    spec = build_spec(forbidden=["net"]) 
    with pytest.raises(MetaValidationError):
        spec.validate()


def test_phantom_rejects_invalid_history():
    bad_entry = {
        "weights": {"perf": 1.0},
        "operator_mix": {"CONST_TUNE": 1.0},
        "population_cap": MAX_POPULATION_CAP + 1,
    }
    with pytest.raises(MetaValidationError):
        replay([bad_entry])


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
