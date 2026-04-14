from __future__ import annotations

import json

import pytest

from singular.sensors.config import (
    HostSensorsConfigError,
    load_host_sensor_thresholds,
    validate_host_sensors_payload,
)


def test_load_host_sensor_thresholds_defaults_when_missing(tmp_path):
    thresholds = load_host_sensor_thresholds(tmp_path / "missing.yaml")

    assert thresholds.cpu_warning_percent == 85.0
    assert thresholds.cpu_critical_percent == 95.0
    assert thresholds.ram_warning_percent == 80.0
    assert thresholds.ram_critical_percent == 92.0
    assert thresholds.temperature_warning_c == 75.0
    assert thresholds.temperature_critical_c == 85.0
    assert thresholds.disk_critical_percent == 95.0


def test_load_host_sensor_thresholds_from_yaml_and_env_override(tmp_path, monkeypatch):
    config = tmp_path / "host_sensors.yaml"
    config.write_text(
        """
host_sensors:
  cpu:
    warning_percent: 70
    critical_percent: 90
  ram:
    warning_percent: 75
    critical_percent: 88
  temperature:
    warning_c: 65
    critical_c: 78
  disk:
    critical_percent: 93
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv(
        "SINGULAR_HOST_SENSORS_OVERRIDES",
        json.dumps({"host_sensors": {"cpu": {"critical_percent": 91}, "disk": {"critical_percent": 96}}}),
    )

    thresholds = load_host_sensor_thresholds(config)

    assert thresholds.cpu_warning_percent == 70.0
    assert thresholds.cpu_critical_percent == 91.0
    assert thresholds.ram_warning_percent == 75.0
    assert thresholds.ram_critical_percent == 88.0
    assert thresholds.temperature_warning_c == 65.0
    assert thresholds.temperature_critical_c == 78.0
    assert thresholds.disk_critical_percent == 96.0


def test_validate_host_sensor_thresholds_rejects_invalid_schema():
    with pytest.raises(HostSensorsConfigError):
        validate_host_sensors_payload(
            {
                "host_sensors": {
                    "cpu": {"warning_percent": 90, "critical_percent": 80},
                    "ram": {"warning_percent": 75, "critical_percent": 90},
                    "temperature": {"warning_c": 70, "critical_c": 80},
                    "disk": {"critical_percent": 95},
                }
            }
        )
