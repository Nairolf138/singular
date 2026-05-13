from pathlib import Path

from singular.orchestrator.lifecycle_clock import load_lifecycle_clock_config


def test_load_lifecycle_clock_defaults_when_file_missing(tmp_path: Path) -> None:
    cfg = load_lifecycle_clock_config(tmp_path / "missing.yaml")

    assert cfg.cycle.veille_seconds == 2.0
    assert cfg.cycle.sommeil_seconds == 3.0
    assert cfg.cycle.introspection_frequency_ticks == 1
    assert cfg.cycle.mutation_window_seconds == 0.2
    assert cfg.phases["action"].cpu_budget_percent == 75.0


def test_load_lifecycle_clock_parses_values(tmp_path: Path) -> None:
    file_path = tmp_path / "lifecycle.yaml"
    file_path.write_text(
        """
cycle:
  veille_seconds: 4
  sommeil_seconds: 8
  introspection_frequency_ticks: 3
  mutation_window_seconds: 0.15
phases:
  action:
    cpu_budget_percent: 65
    slowdown_on_fatigue: 1.8
    allowed_actions: [mutation, evaluation]
""".strip(),
        encoding="utf-8",
    )

    cfg = load_lifecycle_clock_config(file_path)

    assert cfg.cycle.veille_seconds == 4.0
    assert cfg.cycle.sommeil_seconds == 8.0
    assert cfg.cycle.introspection_frequency_ticks == 3
    assert cfg.cycle.mutation_window_seconds == 0.15
    assert cfg.phases["action"].allowed_actions == ("mutation", "evaluation")
    assert cfg.phases["action"].slowdown_on_fatigue == 1.8


def test_load_lifecycle_clock_rejects_invalid_frequency(tmp_path: Path) -> None:
    file_path = tmp_path / "lifecycle.yaml"
    file_path.write_text(
        """
cycle:
  introspection_frequency_ticks: 0
""".strip(),
        encoding="utf-8",
    )

    try:
        load_lifecycle_clock_config(file_path)
    except ValueError as err:
        assert "introspection_frequency_ticks" in str(err)
    else:
        raise AssertionError("expected ValueError")


def test_load_lifecycle_clock_parses_coevolution_values(tmp_path: Path) -> None:
    file_path = tmp_path / "lifecycle.yaml"
    file_path.write_text(
        """
coevolution:
  enabled: true
  robustness_weight: 2.5
  max_test_candidates: 7
  ttl: 5
""".strip(),
        encoding="utf-8",
    )

    cfg = load_lifecycle_clock_config(file_path)

    assert cfg.coevolution.enabled is True
    assert cfg.coevolution.robustness_weight == 2.5
    assert cfg.coevolution.max_test_candidates == 7
    assert cfg.coevolution.ttl == 5
