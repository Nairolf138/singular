import pytest

from graine.meta.dsl import MetaSpec, MetaValidationError, MAX_POPULATION_CAP
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
