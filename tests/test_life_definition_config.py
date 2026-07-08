from pathlib import Path

import pytest

import singular.life.life_definition as life_definition
from singular.life.life_definition import load_life_definition_config


def test_load_life_definition_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = load_life_definition_config(tmp_path / "missing.yaml")

    assert cfg.schema_version == "1.0"
    assert cfg.criteria.persistent_identity is True
    assert cfg.criteria.generation_registry is True
    assert cfg.criteria.stable_cycle is True
    assert cfg.criteria.intrinsic_goals is True
    assert cfg.criteria.reproduction_capability is True
    assert cfg.criteria.narrative_continuity is True
    assert cfg.thresholds.minimum_narrative_trajectory_days == 7
    assert cfg.thresholds.minimum_observed_cycles == 3
    assert cfg.thresholds.alive_minimum_score == 0.8
    assert cfg.thresholds.fragile_minimum_score == 0.5
    assert set(cfg.statuses) == {
        "not_alive_yet",
        "fragile",
        "alive",
        "dying",
        "extinct",
    }


def test_load_life_definition_from_dedicated_file(tmp_path: Path) -> None:
    file_path = tmp_path / "life_definition.yaml"
    file_path.write_text(
        """
schema_version: "1.1"
criteria:
  persistent_identity: false
  generation_registry: true
thresholds:
  minimum_narrative_trajectory_days: 14
  minimum_observed_cycles: 9
  maximum_cycle_anomalies: 2
  alive_minimum_score: 0.9
  fragile_minimum_score: 0.4
statuses:
  not_alive_yet: not_alive_yet
  fragile: fragile
  alive: alive
  dying: dying
  extinct: extinct
""".strip(),
        encoding="utf-8",
    )

    cfg = load_life_definition_config(file_path)

    assert cfg.schema_version == "1.1"
    assert cfg.criteria.persistent_identity is False
    assert cfg.criteria.stable_cycle is True
    assert cfg.thresholds.minimum_narrative_trajectory_days == 14
    assert cfg.thresholds.minimum_observed_cycles == 9
    assert cfg.thresholds.maximum_cycle_anomalies == 2
    assert cfg.thresholds.alive_minimum_score == 0.9
    assert cfg.thresholds.fragile_minimum_score == 0.4


def test_load_life_definition_from_lifecycle_section(tmp_path: Path) -> None:
    file_path = tmp_path / "lifecycle.yaml"
    file_path.write_text(
        """
cycle:
  veille_seconds: 2
life_definition:
  schema_version: "1.2"
  thresholds:
    minimum_observed_cycles: 5
""".strip(),
        encoding="utf-8",
    )

    cfg = load_life_definition_config(file_path)

    assert cfg.schema_version == "1.2"
    assert cfg.thresholds.minimum_observed_cycles == 5
    assert cfg.thresholds.minimum_narrative_trajectory_days == 7


def test_load_life_definition_rejects_invalid_threshold_order(tmp_path: Path) -> None:
    file_path = tmp_path / "life_definition.yaml"
    file_path.write_text(
        """
thresholds:
  alive_minimum_score: 0.3
  fragile_minimum_score: 0.5
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="alive_minimum_score"):
        load_life_definition_config(file_path)


def test_load_default_life_definition_falls_back_when_dedicated_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lifecycle_path = tmp_path / "lifecycle.yaml"
    missing_life_definition_path = tmp_path / "life_definition.yaml"
    lifecycle_path.write_text(
        """
cycle:
  veille_seconds: 2
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        life_definition,
        "DEFAULT_LIFE_DEFINITION_CONFIG_PATH",
        missing_life_definition_path,
    )
    monkeypatch.setattr(
        life_definition, "DEFAULT_LIFECYCLE_CONFIG_PATH", lifecycle_path
    )

    cfg = load_life_definition_config()

    assert cfg == life_definition.LifeDefinitionConfig()


def test_load_life_definition_rejects_invalid_boolean_with_clear_error(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "life_definition.yaml"
    file_path.write_text(
        """
criteria:
  persistent_identity: sometimes
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="criteria.persistent_identity must be a boolean"
    ):
        load_life_definition_config(file_path)


def test_load_life_definition_rejects_invalid_numeric_value_with_clear_error(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "life_definition.yaml"
    file_path.write_text(
        """
thresholds:
  minimum_observed_cycles: many
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="thresholds.minimum_observed_cycles must be an integer"
    ):
        load_life_definition_config(file_path)
