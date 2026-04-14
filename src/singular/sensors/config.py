"""Configuration loader for host sensor thresholds."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

DEFAULT_HOST_SENSORS_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "host_sensors.yaml"
ENV_HOST_SENSORS_CONFIG_PATH = "SINGULAR_HOST_SENSORS_CONFIG"
ENV_HOST_SENSORS_OVERRIDES = "SINGULAR_HOST_SENSORS_OVERRIDES"


class HostSensorsConfigError(ValueError):
    """Raised when host sensor configuration is invalid."""


@dataclass(frozen=True)
class HostSensorThresholds:
    """Thresholds used to generate ``host.*`` perception events."""

    cpu_warning_percent: float = 85.0
    cpu_critical_percent: float = 95.0
    ram_warning_percent: float = 80.0
    ram_critical_percent: float = 92.0
    temperature_warning_c: float = 75.0
    temperature_critical_c: float = 85.0
    disk_critical_percent: float = 95.0

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _parse_scalar(value: str) -> Any:
    text = value.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [chunk.strip().strip('"').strip("'") for chunk in inner.split(",")]
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text.strip('"').strip("'")


def _load_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, data)]

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.strip().split(":", 1)
        while stack and indent < stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if not value.strip():
            new: dict[str, Any] = {}
            current[key.strip()] = new
            stack.append((indent + 2, new))
            continue
        current[key.strip()] = _parse_scalar(value)
    return data


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        payload = _load_simple_yaml(path)

    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise HostSensorsConfigError("host sensors config must be a mapping")
    return payload


def _coerce_percent(payload: Mapping[str, Any], key: str, *, min_v: float = 0.0, max_v: float = 100.0) -> float:
    if key not in payload:
        raise HostSensorsConfigError(f"missing required key: {key}")
    raw = payload[key]
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise HostSensorsConfigError(f"invalid numeric value for {key}: {raw!r}") from exc
    if value < min_v or value > max_v:
        raise HostSensorsConfigError(f"value for {key} must be within [{min_v}, {max_v}]")
    return value


def _validate_threshold_order(low: float, high: float, *, low_name: str, high_name: str) -> None:
    if low >= high:
        raise HostSensorsConfigError(f"{low_name} must be < {high_name}")


def validate_host_sensors_payload(payload: Mapping[str, Any]) -> HostSensorThresholds:
    """Validate mapping and return strict host sensor thresholds."""

    root = payload.get("host_sensors", payload)
    if not isinstance(root, Mapping):
        raise HostSensorsConfigError("`host_sensors` section must be a mapping")

    expected_root = {"cpu", "ram", "temperature", "disk"}
    unexpected_root = sorted(set(root.keys()) - expected_root)
    if unexpected_root:
        raise HostSensorsConfigError(f"unexpected keys: {', '.join(unexpected_root)}")

    cpu = root.get("cpu", {})
    ram = root.get("ram", {})
    temperature = root.get("temperature", {})
    disk = root.get("disk", {})
    for section_name, section in {
        "cpu": cpu,
        "ram": ram,
        "temperature": temperature,
        "disk": disk,
    }.items():
        if not isinstance(section, Mapping):
            raise HostSensorsConfigError(f"section `{section_name}` must be a mapping")

    cpu_unexpected = sorted(set(cpu.keys()) - {"warning_percent", "critical_percent"})
    ram_unexpected = sorted(set(ram.keys()) - {"warning_percent", "critical_percent"})
    temp_unexpected = sorted(set(temperature.keys()) - {"warning_c", "critical_c"})
    disk_unexpected = sorted(set(disk.keys()) - {"critical_percent"})
    unexpected = cpu_unexpected + ram_unexpected + temp_unexpected + disk_unexpected
    if unexpected:
        raise HostSensorsConfigError(f"unexpected nested keys: {', '.join(unexpected)}")

    cpu_warning = _coerce_percent(cpu, "warning_percent")
    cpu_critical = _coerce_percent(cpu, "critical_percent")
    ram_warning = _coerce_percent(ram, "warning_percent")
    ram_critical = _coerce_percent(ram, "critical_percent")
    temperature_warning = _coerce_percent(temperature, "warning_c", min_v=-50.0, max_v=200.0)
    temperature_critical = _coerce_percent(temperature, "critical_c", min_v=-50.0, max_v=200.0)
    disk_critical = _coerce_percent(disk, "critical_percent")

    _validate_threshold_order(
        cpu_warning,
        cpu_critical,
        low_name="cpu.warning_percent",
        high_name="cpu.critical_percent",
    )
    _validate_threshold_order(
        ram_warning,
        ram_critical,
        low_name="ram.warning_percent",
        high_name="ram.critical_percent",
    )
    _validate_threshold_order(
        temperature_warning,
        temperature_critical,
        low_name="temperature.warning_c",
        high_name="temperature.critical_c",
    )

    return HostSensorThresholds(
        cpu_warning_percent=cpu_warning,
        cpu_critical_percent=cpu_critical,
        ram_warning_percent=ram_warning,
        ram_critical_percent=ram_critical,
        temperature_warning_c=temperature_warning,
        temperature_critical_c=temperature_critical,
        disk_critical_percent=disk_critical,
    )


def _merge_nested(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = _merge_nested(dict(out[key]), value)
        else:
            out[key] = value
    return out


def load_host_sensor_thresholds(path: Path | None = None) -> HostSensorThresholds:
    """Load host thresholds from config with strict validation and env overrides."""

    defaults = HostSensorThresholds()
    base_payload: dict[str, Any] = {
        "host_sensors": {
            "cpu": {
                "warning_percent": defaults.cpu_warning_percent,
                "critical_percent": defaults.cpu_critical_percent,
            },
            "ram": {
                "warning_percent": defaults.ram_warning_percent,
                "critical_percent": defaults.ram_critical_percent,
            },
            "temperature": {
                "warning_c": defaults.temperature_warning_c,
                "critical_c": defaults.temperature_critical_c,
            },
            "disk": {
                "critical_percent": defaults.disk_critical_percent,
            },
        }
    }

    selected = path
    if selected is None:
        raw_path = os.environ.get(ENV_HOST_SENSORS_CONFIG_PATH, "").strip()
        selected = Path(raw_path) if raw_path else DEFAULT_HOST_SENSORS_CONFIG_PATH

    if selected.exists():
        payload = _load_yaml_mapping(selected)
        base_payload = _merge_nested(base_payload, payload)

    overrides_raw = os.environ.get(ENV_HOST_SENSORS_OVERRIDES, "").strip()
    if overrides_raw:
        try:
            override_payload = json.loads(overrides_raw)
        except json.JSONDecodeError as exc:
            raise HostSensorsConfigError(f"invalid JSON in {ENV_HOST_SENSORS_OVERRIDES}") from exc
        if not isinstance(override_payload, Mapping):
            raise HostSensorsConfigError(f"{ENV_HOST_SENSORS_OVERRIDES} must contain a JSON mapping")
        base_payload = _merge_nested(base_payload, dict(override_payload))

    return validate_host_sensors_payload(base_payload)


__all__ = [
    "DEFAULT_HOST_SENSORS_CONFIG_PATH",
    "ENV_HOST_SENSORS_CONFIG_PATH",
    "ENV_HOST_SENSORS_OVERRIDES",
    "HostSensorThresholds",
    "HostSensorsConfigError",
    "load_host_sensor_thresholds",
    "validate_host_sensors_payload",
]
