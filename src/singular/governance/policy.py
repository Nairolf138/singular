"""Governance policy for mutation and reproduction writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import deque
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

from .values import ValueWeights

log = logging.getLogger(__name__)


AUTH_AUTO = "auto"
AUTH_REVIEW_REQUIRED = "review-required"
AUTH_BLOCKED = "blocked"
AUTH_FORCED = "forced"
POLICY_SCHEMA_VERSION = 1

_ROOT_POLICY_FILE = "policy.yaml"
_POLICY_DECISIONS_LOG = "policy_decisions.jsonl"


class PolicySchemaError(ValueError):
    """Raised when ``policy.yaml`` does not respect strict governance schema."""


def _default_policy_payload() -> dict[str, Any]:
    return {
        "version": POLICY_SCHEMA_VERSION,
        "memory": {"preserve_threshold": 0.6},
        "forgetting": {"enabled": True, "max_episodic_entries": 5000},
        "sensors": {
            "allowed": ["host_metrics", "artifact_scan", "virtual_environment"],
            "blocked": [],
            "max_export_granularity": "standard",
            "anonymization": {
                "enabled": True,
                "block_sensitive_by_default": True,
                "allow_sensitive_metrics_opt_in": False,
                "redact_machine_user_info": True,
                "sensitive_metric_keys_blocklist": [
                    "hostname",
                    "host_name",
                    "fqdn",
                    "cwd",
                    "cwd_path",
                    "path",
                    "paths",
                    "user",
                    "username",
                    "home",
                    "mount_path",
                    "absolute_path",
                ],
            },
        },
        "permissions": {
            "modifiable_paths": ["skills"],
            "review_required_paths": ["skills/experimental"],
            "forbidden_paths": ["src", ".git", "mem", "runs", "tests"],
            "force_allow_paths": [],
        },
        "autonomy": {
            "safe_mode": False,
            "mutation_quota_per_window": 25,
            "mutation_quota_window_seconds": 300.0,
            "runtime_call_quota_per_hour": 240,
            "runtime_blacklisted_capabilities": [],
            "auto_rollback_failure_threshold": 5,
            "auto_rollback_cost_threshold": 10.0,
            "skill_creation_quota_per_window": 3,
            "skill_creation_quota_window_seconds": 900.0,
            "file_creation_review_required": False,
            "safe_mode_review_required_skill_families": ["network", "shell", "filesystem"],
            "circuit_breaker_threshold": 3,
            "circuit_breaker_window_seconds": 180.0,
            "circuit_breaker_cooldown_seconds": 300.0,
            "skill_circuit_breaker_failure_threshold": 3,
            "skill_circuit_breaker_cost_threshold": 5.0,
            "skill_circuit_breaker_cooldown_seconds": 600.0,
        },
        "social": {
            "max_influence_per_life": 0.35,
            "blocked_hostile_behaviors": [
                "threat.explicit",
                "harassment.explicit",
                "sabotage.explicit",
                "abuse.explicit",
            ],
            "conflict_events": [
                "conflict.explicit",
                "betrayal",
                "resource_conflict",
            ],
            "conflict_mediation_threshold": 3,
            "conflict_window_seconds": 900.0,
            "mediation_cooldown_seconds": 600.0,
            "prudent_mode_on_mediation": True,
        },
    }


def _coerce_bool(payload: Mapping[str, Any], key: str) -> bool:
    if key not in payload or not isinstance(payload[key], bool):
        raise PolicySchemaError(f"'{key}' must be a boolean")
    return bool(payload[key])


def _coerce_float(payload: Mapping[str, Any], key: str, *, minimum: float = 0.0) -> float:
    if key not in payload:
        raise PolicySchemaError(f"missing required key: {key}")
    try:
        cast = float(payload[key])
    except (TypeError, ValueError) as exc:
        raise PolicySchemaError(f"'{key}' must be numeric") from exc
    if cast < minimum:
        raise PolicySchemaError(f"'{key}' must be >= {minimum}")
    return cast


def _coerce_int(payload: Mapping[str, Any], key: str, *, minimum: int = 0) -> int:
    if key not in payload:
        raise PolicySchemaError(f"missing required key: {key}")
    value = payload[key]
    if isinstance(value, bool):
        raise PolicySchemaError(f"'{key}' must be an integer")
    try:
        cast = int(value)
    except (TypeError, ValueError) as exc:
        raise PolicySchemaError(f"'{key}' must be an integer") from exc
    if cast < minimum:
        raise PolicySchemaError(f"'{key}' must be >= {minimum}")
    return cast


def _coerce_path_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    if key not in payload:
        raise PolicySchemaError(f"missing required key: {key}")
    raw = payload[key]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise PolicySchemaError(f"'{key}' must be a list of path strings")
    return tuple(item.strip("/ ") for item in raw if item.strip("/ "))


def _coerce_string_list(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    if key not in payload:
        raise PolicySchemaError(f"missing required key: {key}")
    raw = payload[key]
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise PolicySchemaError(f"'{key}' must be a list of strings")
    return tuple(item.strip() for item in raw if item.strip())


def _coerce_enum(payload: Mapping[str, Any], key: str, allowed: set[str]) -> str:
    if key not in payload or not isinstance(payload[key], str):
        raise PolicySchemaError(f"'{key}' must be a string")
    value = payload[key].strip().lower()
    if value not in allowed:
        raise PolicySchemaError(f"'{key}' must be one of: {', '.join(sorted(allowed))}")
    return value


@dataclass(frozen=True)
class RuntimePolicy:
    """Strict, versioned governance policy loaded from ``policy.yaml``."""

    version: int
    memory_preserve_threshold: float
    forgetting_enabled: bool
    forgetting_max_episodic_entries: int
    sensors_allowed: tuple[str, ...]
    sensors_blocked: tuple[str, ...]
    sensors_max_export_granularity: str
    sensors_anonymization_enabled: bool
    sensors_block_sensitive_by_default: bool
    sensors_allow_sensitive_metrics_opt_in: bool
    sensors_redact_machine_user_info: bool
    sensors_sensitive_metric_keys_blocklist: tuple[str, ...]
    modifiable_paths: tuple[str, ...]
    review_required_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    force_allow_paths: tuple[str, ...]
    safe_mode: bool
    mutation_quota_per_window: int
    mutation_quota_window_seconds: float
    skill_creation_quota_per_window: int
    skill_creation_quota_window_seconds: float
    file_creation_review_required: bool
    runtime_call_quota_per_hour: int
    runtime_blacklisted_capabilities: tuple[str, ...]
    auto_rollback_failure_threshold: int
    auto_rollback_cost_threshold: float
    safe_mode_review_required_skill_families: tuple[str, ...]
    circuit_breaker_threshold: int
    circuit_breaker_window_seconds: float
    circuit_breaker_cooldown_seconds: float
    skill_circuit_breaker_failure_threshold: int
    skill_circuit_breaker_cost_threshold: float
    skill_circuit_breaker_cooldown_seconds: float
    social_max_influence_per_life: float
    social_blocked_hostile_behaviors: tuple[str, ...]
    social_conflict_events: tuple[str, ...]
    social_conflict_mediation_threshold: int
    social_conflict_window_seconds: float
    social_mediation_cooldown_seconds: float
    social_prudent_mode_on_mediation: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "memory": {"preserve_threshold": self.memory_preserve_threshold},
            "forgetting": {
                "enabled": self.forgetting_enabled,
                "max_episodic_entries": self.forgetting_max_episodic_entries,
            },
            "sensors": {
                "allowed": list(self.sensors_allowed),
                "blocked": list(self.sensors_blocked),
                "max_export_granularity": self.sensors_max_export_granularity,
                "anonymization": {
                    "enabled": self.sensors_anonymization_enabled,
                    "block_sensitive_by_default": self.sensors_block_sensitive_by_default,
                    "allow_sensitive_metrics_opt_in": self.sensors_allow_sensitive_metrics_opt_in,
                    "redact_machine_user_info": self.sensors_redact_machine_user_info,
                    "sensitive_metric_keys_blocklist": list(
                        self.sensors_sensitive_metric_keys_blocklist
                    ),
                },
            },
            "permissions": {
                "modifiable_paths": list(self.modifiable_paths),
                "review_required_paths": list(self.review_required_paths),
                "forbidden_paths": list(self.forbidden_paths),
                "force_allow_paths": list(self.force_allow_paths),
            },
            "autonomy": {
                "safe_mode": self.safe_mode,
                "mutation_quota_per_window": self.mutation_quota_per_window,
                "mutation_quota_window_seconds": self.mutation_quota_window_seconds,
                "runtime_call_quota_per_hour": self.runtime_call_quota_per_hour,
                "runtime_blacklisted_capabilities": list(self.runtime_blacklisted_capabilities),
                "auto_rollback_failure_threshold": self.auto_rollback_failure_threshold,
                "auto_rollback_cost_threshold": self.auto_rollback_cost_threshold,
                "skill_creation_quota_per_window": self.skill_creation_quota_per_window,
                "skill_creation_quota_window_seconds": self.skill_creation_quota_window_seconds,
                "file_creation_review_required": self.file_creation_review_required,
                "safe_mode_review_required_skill_families": list(
                    self.safe_mode_review_required_skill_families
                ),
                "circuit_breaker_threshold": self.circuit_breaker_threshold,
                "circuit_breaker_window_seconds": self.circuit_breaker_window_seconds,
                "circuit_breaker_cooldown_seconds": self.circuit_breaker_cooldown_seconds,
                "skill_circuit_breaker_failure_threshold": self.skill_circuit_breaker_failure_threshold,
                "skill_circuit_breaker_cost_threshold": self.skill_circuit_breaker_cost_threshold,
                "skill_circuit_breaker_cooldown_seconds": self.skill_circuit_breaker_cooldown_seconds,
            },
            "social": {
                "max_influence_per_life": self.social_max_influence_per_life,
                "blocked_hostile_behaviors": list(self.social_blocked_hostile_behaviors),
                "conflict_events": list(self.social_conflict_events),
                "conflict_mediation_threshold": self.social_conflict_mediation_threshold,
                "conflict_window_seconds": self.social_conflict_window_seconds,
                "mediation_cooldown_seconds": self.social_mediation_cooldown_seconds,
                "prudent_mode_on_mediation": self.social_prudent_mode_on_mediation,
            },
        }

    def impact_summary(self) -> list[str]:
        return [
            f"Mémoire: blocage des truncatures si réécriture < {self.memory_preserve_threshold:.0%} du contenu existant.",
            (
                "Oubli: activé"
                if self.forgetting_enabled
                else "Oubli: désactivé (rétention infinie des épisodes)."
            )
            + f" max_episodic_entries={self.forgetting_max_episodic_entries}.",
            f"Permissions: {len(self.modifiable_paths)} zones auto, {len(self.review_required_paths)} zones review, {len(self.forbidden_paths)} zones interdites.",
            (
                "Autonomie: "
                f"quota-mutation={self.mutation_quota_per_window}/{self.mutation_quota_window_seconds:.0f}s, "
                f"quota-runtime={self.runtime_call_quota_per_hour}/h, "
                f"quota-creation={self.skill_creation_quota_per_window}/{self.skill_creation_quota_window_seconds:.0f}s, "
                f"review-creation={'on' if self.file_creation_review_required else 'off'}, "
                f"circuit={self.circuit_breaker_threshold} violations/{self.circuit_breaker_window_seconds:.0f}s, "
                f"safe_mode={'on' if self.safe_mode else 'off'}."
            ),
        ]


def _validate_runtime_policy(payload: Mapping[str, Any]) -> RuntimePolicy:
    mutable_payload = dict(payload)
    mutable_payload.setdefault("sensors", _default_policy_payload()["sensors"])
    mutable_payload.setdefault("social", _default_policy_payload()["social"])
    payload = mutable_payload
    root_keys = {"version", "memory", "forgetting", "sensors", "permissions", "autonomy", "social"}
    unexpected = sorted(set(payload.keys()) - root_keys)
    if unexpected:
        raise PolicySchemaError(f"unexpected root keys: {', '.join(unexpected)}")
    if sorted(payload.keys()) != sorted(root_keys):
        missing = sorted(root_keys - set(payload.keys()))
        raise PolicySchemaError(f"missing root keys: {', '.join(missing)}")

    version = _coerce_int(payload, "version", minimum=1)
    if version != POLICY_SCHEMA_VERSION:
        raise PolicySchemaError(
            f"unsupported policy version: {version} (expected {POLICY_SCHEMA_VERSION})"
        )

    memory = payload["memory"]
    forgetting = payload["forgetting"]
    sensors = payload["sensors"]
    permissions = payload["permissions"]
    autonomy_raw = payload["autonomy"]
    social = payload["social"]
    autonomy = dict(autonomy_raw) if isinstance(autonomy_raw, Mapping) else autonomy_raw
    if isinstance(autonomy, dict):
        autonomy.setdefault("skill_creation_quota_per_window", 3)
        autonomy.setdefault("skill_creation_quota_window_seconds", 900.0)
        autonomy.setdefault("file_creation_review_required", False)
        autonomy.setdefault("runtime_call_quota_per_hour", 240)
        autonomy.setdefault("runtime_blacklisted_capabilities", [])
        autonomy.setdefault("auto_rollback_failure_threshold", 5)
        autonomy.setdefault("auto_rollback_cost_threshold", 10.0)
        autonomy.setdefault(
            "safe_mode_review_required_skill_families",
            ["network", "shell", "filesystem"],
        )
        autonomy.setdefault("skill_circuit_breaker_failure_threshold", 3)
        autonomy.setdefault("skill_circuit_breaker_cost_threshold", 5.0)
        autonomy.setdefault("skill_circuit_breaker_cooldown_seconds", 600.0)
    for section_name, section in (
        ("memory", memory),
        ("forgetting", forgetting),
        ("permissions", permissions),
        ("sensors", sensors),
        ("autonomy", autonomy),
        ("social", social),
    ):
        if not isinstance(section, Mapping):
            raise PolicySchemaError(f"section '{section_name}' must be a mapping")

    expected_memory = {"preserve_threshold"}
    expected_forgetting = {"enabled", "max_episodic_entries"}
    expected_sensors = {"allowed", "blocked", "max_export_granularity", "anonymization"}
    expected_sensors_anonymization = {
        "enabled",
        "block_sensitive_by_default",
        "allow_sensitive_metrics_opt_in",
        "redact_machine_user_info",
        "sensitive_metric_keys_blocklist",
    }
    expected_permissions = {
        "modifiable_paths",
        "review_required_paths",
        "forbidden_paths",
        "force_allow_paths",
    }
    expected_autonomy = {
        "safe_mode",
        "mutation_quota_per_window",
        "mutation_quota_window_seconds",
        "runtime_call_quota_per_hour",
        "runtime_blacklisted_capabilities",
        "auto_rollback_failure_threshold",
        "auto_rollback_cost_threshold",
        "skill_creation_quota_per_window",
        "skill_creation_quota_window_seconds",
        "file_creation_review_required",
        "safe_mode_review_required_skill_families",
        "circuit_breaker_threshold",
        "circuit_breaker_window_seconds",
        "circuit_breaker_cooldown_seconds",
        "skill_circuit_breaker_failure_threshold",
        "skill_circuit_breaker_cost_threshold",
        "skill_circuit_breaker_cooldown_seconds",
    }
    expected_social = {
        "max_influence_per_life",
        "blocked_hostile_behaviors",
        "conflict_events",
        "conflict_mediation_threshold",
        "conflict_window_seconds",
        "mediation_cooldown_seconds",
        "prudent_mode_on_mediation",
    }
    for name, section, expected in (
        ("memory", memory, expected_memory),
        ("forgetting", forgetting, expected_forgetting),
        ("permissions", permissions, expected_permissions),
        ("sensors", sensors, expected_sensors),
        ("autonomy", autonomy, expected_autonomy),
        ("social", social, expected_social),
    ):
        section_unexpected = sorted(set(section.keys()) - expected)
        if section_unexpected:
            raise PolicySchemaError(
                f"section '{name}' has unexpected keys: {', '.join(section_unexpected)}"
            )
        section_missing = sorted(expected - set(section.keys()))
        if section_missing:
            raise PolicySchemaError(
                f"section '{name}' missing keys: {', '.join(section_missing)}"
            )
    anonymization = sensors["anonymization"]
    if not isinstance(anonymization, Mapping):
        raise PolicySchemaError("section 'sensors.anonymization' must be a mapping")
    anonymization_unexpected = sorted(set(anonymization.keys()) - expected_sensors_anonymization)
    if anonymization_unexpected:
        raise PolicySchemaError(
            "section 'sensors.anonymization' has unexpected keys: "
            + ", ".join(anonymization_unexpected)
        )
    anonymization_missing = sorted(expected_sensors_anonymization - set(anonymization.keys()))
    if anonymization_missing:
        raise PolicySchemaError(
            "section 'sensors.anonymization' missing keys: " + ", ".join(anonymization_missing)
        )

    preserve_threshold = _coerce_float(memory, "preserve_threshold", minimum=0.0)
    if preserve_threshold > 1.0:
        raise PolicySchemaError("'preserve_threshold' must be <= 1.0")
    max_influence = _coerce_float(social, "max_influence_per_life", minimum=0.0)
    if max_influence > 1.0:
        raise PolicySchemaError("'max_influence_per_life' must be <= 1.0")

    return RuntimePolicy(
        version=version,
        memory_preserve_threshold=preserve_threshold,
        forgetting_enabled=_coerce_bool(forgetting, "enabled"),
        forgetting_max_episodic_entries=_coerce_int(forgetting, "max_episodic_entries", minimum=1),
        sensors_allowed=_coerce_string_list(sensors, "allowed"),
        sensors_blocked=_coerce_string_list(sensors, "blocked"),
        sensors_max_export_granularity=_coerce_enum(
            sensors, "max_export_granularity", {"minimal", "standard", "detailed"}
        ),
        sensors_anonymization_enabled=_coerce_bool(anonymization, "enabled"),
        sensors_block_sensitive_by_default=_coerce_bool(
            anonymization, "block_sensitive_by_default"
        ),
        sensors_allow_sensitive_metrics_opt_in=_coerce_bool(
            anonymization, "allow_sensitive_metrics_opt_in"
        ),
        sensors_redact_machine_user_info=_coerce_bool(anonymization, "redact_machine_user_info"),
        sensors_sensitive_metric_keys_blocklist=_coerce_string_list(
            anonymization, "sensitive_metric_keys_blocklist"
        ),
        modifiable_paths=_coerce_path_list(permissions, "modifiable_paths"),
        review_required_paths=_coerce_path_list(permissions, "review_required_paths"),
        forbidden_paths=_coerce_path_list(permissions, "forbidden_paths"),
        force_allow_paths=_coerce_path_list(permissions, "force_allow_paths"),
        safe_mode=_coerce_bool(autonomy, "safe_mode"),
        mutation_quota_per_window=_coerce_int(autonomy, "mutation_quota_per_window", minimum=1),
        mutation_quota_window_seconds=_coerce_float(autonomy, "mutation_quota_window_seconds", minimum=1.0),
        runtime_call_quota_per_hour=_coerce_int(autonomy, "runtime_call_quota_per_hour", minimum=1),
        runtime_blacklisted_capabilities=_coerce_string_list(
            autonomy,
            "runtime_blacklisted_capabilities",
        ),
        auto_rollback_failure_threshold=_coerce_int(
            autonomy, "auto_rollback_failure_threshold", minimum=1
        ),
        auto_rollback_cost_threshold=_coerce_float(
            autonomy, "auto_rollback_cost_threshold", minimum=0.0
        ),
        skill_creation_quota_per_window=_coerce_int(
            autonomy,
            "skill_creation_quota_per_window",
            minimum=1,
        ),
        skill_creation_quota_window_seconds=_coerce_float(
            autonomy,
            "skill_creation_quota_window_seconds",
            minimum=1.0,
        ),
        file_creation_review_required=_coerce_bool(autonomy, "file_creation_review_required"),
        safe_mode_review_required_skill_families=_coerce_string_list(
            autonomy,
            "safe_mode_review_required_skill_families",
        ),
        circuit_breaker_threshold=_coerce_int(autonomy, "circuit_breaker_threshold", minimum=1),
        circuit_breaker_window_seconds=_coerce_float(autonomy, "circuit_breaker_window_seconds", minimum=1.0),
        circuit_breaker_cooldown_seconds=_coerce_float(autonomy, "circuit_breaker_cooldown_seconds", minimum=1.0),
        skill_circuit_breaker_failure_threshold=_coerce_int(
            autonomy,
            "skill_circuit_breaker_failure_threshold",
            minimum=1,
        ),
        skill_circuit_breaker_cost_threshold=_coerce_float(
            autonomy,
            "skill_circuit_breaker_cost_threshold",
            minimum=0.0,
        ),
        skill_circuit_breaker_cooldown_seconds=_coerce_float(
            autonomy,
            "skill_circuit_breaker_cooldown_seconds",
            minimum=1.0,
        ),
        social_max_influence_per_life=max_influence,
        social_blocked_hostile_behaviors=_coerce_string_list(social, "blocked_hostile_behaviors"),
        social_conflict_events=_coerce_string_list(social, "conflict_events"),
        social_conflict_mediation_threshold=_coerce_int(
            social, "conflict_mediation_threshold", minimum=1
        ),
        social_conflict_window_seconds=_coerce_float(
            social, "conflict_window_seconds", minimum=1.0
        ),
        social_mediation_cooldown_seconds=_coerce_float(
            social, "mediation_cooldown_seconds", minimum=1.0
        ),
        social_prudent_mode_on_mediation=_coerce_bool(social, "prudent_mode_on_mediation"),
    )


def get_global_policy_file() -> Path:
    root = Path(os.environ.get("SINGULAR_ROOT", "."))
    return root / _ROOT_POLICY_FILE


def ensure_global_policy_file(path: Path | None = None) -> Path:
    target = Path(path) if path is not None else get_global_policy_file()
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _default_policy_payload()
    target.write_text(_dump_policy_payload(payload), encoding="utf-8")
    return target


def load_runtime_policy(path: Path | None = None) -> RuntimePolicy:
    policy_path = ensure_global_policy_file(path)
    payload = _load_policy_payload(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise PolicySchemaError("policy.yaml must contain a mapping")
    return _validate_runtime_policy(payload)


def save_runtime_policy(policy: RuntimePolicy, path: Path | None = None) -> Path:
    target = Path(path) if path is not None else get_global_policy_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    _validate_runtime_policy(policy.to_payload())
    target.write_text(_dump_policy_payload(policy.to_payload()), encoding="utf-8")
    return target


def _load_policy_payload(raw: str) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PolicySchemaError(
                "PyYAML absent: policy.yaml must contain JSON-compatible content."
            ) from exc
        if not isinstance(data, Mapping):
            raise PolicySchemaError("policy payload must be a mapping")
        return data
    data = yaml.safe_load(raw)
    if not isinstance(data, Mapping):
        raise PolicySchemaError("policy payload must be a mapping")
    return data


def _dump_policy_payload(payload: Mapping[str, Any]) -> str:
    try:
        import yaml  # type: ignore
    except ImportError:
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return yaml.safe_dump(dict(payload), sort_keys=False)


@dataclass(frozen=True)
class GovernanceDecision:
    """Decision returned by policy simulation or enforcement."""

    level: str
    allowed: bool
    reason: str
    corrective_action: str
    severity: str = "info"


class MutationGovernancePolicy:
    """Path-based governance with mandatory write simulation."""

    def __init__(
        self,
        *,
        modifiable_paths: tuple[str, ...] = ("skills",),
        review_required_paths: tuple[str, ...] = ("skills/experimental",),
        forbidden_paths: tuple[str, ...] = (
            "src",
            ".git",
            "mem",
            "runs",
            "tests",
        ),
        value_weights: ValueWeights | None = None,
        mutation_quota_per_window: int = 25,
        mutation_quota_window_seconds: float = 300.0,
        runtime_call_quota_per_hour: int = 240,
        runtime_blacklisted_capabilities: tuple[str, ...] | None = None,
        auto_rollback_failure_threshold: int = 5,
        auto_rollback_cost_threshold: float = 10.0,
        skill_creation_quota_per_window: int = 3,
        skill_creation_quota_window_seconds: float = 900.0,
        file_creation_review_required: bool = False,
        safe_mode_review_required_skill_families: tuple[str, ...] | None = None,
        circuit_breaker_threshold: int = 3,
        circuit_breaker_window_seconds: float = 180.0,
        circuit_breaker_cooldown_seconds: float = 300.0,
        skill_circuit_breaker_failure_threshold: int = 3,
        skill_circuit_breaker_cost_threshold: float = 5.0,
        skill_circuit_breaker_cooldown_seconds: float = 600.0,
        safe_mode: bool = False,
    ) -> None:
        runtime_policy = load_runtime_policy()
        self.runtime_policy = runtime_policy
        self.modifiable_paths = tuple(
            p.strip("/") for p in (modifiable_paths or runtime_policy.modifiable_paths)
        )
        self.review_required_paths = tuple(
            p.strip("/") for p in (review_required_paths or runtime_policy.review_required_paths)
        )
        self.forbidden_paths = tuple(
            p.strip("/") for p in (forbidden_paths or runtime_policy.forbidden_paths)
        )
        self.force_allow_paths = tuple(p.strip("/") for p in runtime_policy.force_allow_paths)
        self.value_weights = (value_weights or ValueWeights()).normalized()
        self.mutation_quota_per_window = max(
            int(mutation_quota_per_window or runtime_policy.mutation_quota_per_window), 1
        )
        self.mutation_quota_window_seconds = max(
            float(
                mutation_quota_window_seconds
                or runtime_policy.mutation_quota_window_seconds
            ),
            1.0,
        )
        self.runtime_call_quota_per_hour = max(
            int(runtime_call_quota_per_hour or runtime_policy.runtime_call_quota_per_hour),
            1,
        )
        blacklisted_capabilities = (
            runtime_blacklisted_capabilities
            if runtime_blacklisted_capabilities is not None
            else runtime_policy.runtime_blacklisted_capabilities
        )
        self.runtime_blacklisted_capabilities = frozenset(
            item.strip().lower() for item in blacklisted_capabilities if item.strip()
        )
        self.auto_rollback_failure_threshold = max(
            int(auto_rollback_failure_threshold or runtime_policy.auto_rollback_failure_threshold),
            1,
        )
        self.auto_rollback_cost_threshold = max(
            float(auto_rollback_cost_threshold or runtime_policy.auto_rollback_cost_threshold),
            0.0,
        )
        self.skill_creation_quota_per_window = max(
            int(
                skill_creation_quota_per_window
                or runtime_policy.skill_creation_quota_per_window
            ),
            1,
        )
        self.skill_creation_quota_window_seconds = max(
            float(
                skill_creation_quota_window_seconds
                or runtime_policy.skill_creation_quota_window_seconds
            ),
            1.0,
        )
        self.file_creation_review_required = bool(
            file_creation_review_required or runtime_policy.file_creation_review_required
        )
        required_skill_families = (
            safe_mode_review_required_skill_families
            if safe_mode_review_required_skill_families is not None
            else runtime_policy.safe_mode_review_required_skill_families
        )
        self.safe_mode_review_required_skill_families = frozenset(
            item.strip().lower() for item in required_skill_families if item.strip()
        )
        self.circuit_breaker_threshold = max(
            int(circuit_breaker_threshold or runtime_policy.circuit_breaker_threshold), 1
        )
        self.circuit_breaker_window_seconds = max(
            float(
                circuit_breaker_window_seconds
                or runtime_policy.circuit_breaker_window_seconds
            ),
            1.0,
        )
        self.circuit_breaker_cooldown_seconds = max(
            float(
                circuit_breaker_cooldown_seconds
                or runtime_policy.circuit_breaker_cooldown_seconds
            ),
            1.0,
        )
        self.skill_circuit_breaker_failure_threshold = max(
            int(
                skill_circuit_breaker_failure_threshold
                or runtime_policy.skill_circuit_breaker_failure_threshold
            ),
            1,
        )
        self.skill_circuit_breaker_cost_threshold = max(
            float(
                skill_circuit_breaker_cost_threshold
                or runtime_policy.skill_circuit_breaker_cost_threshold
            ),
            0.0,
        )
        self.skill_circuit_breaker_cooldown_seconds = max(
            float(
                skill_circuit_breaker_cooldown_seconds
                or runtime_policy.skill_circuit_breaker_cooldown_seconds
            ),
            1.0,
        )
        self.safe_mode = bool(safe_mode or runtime_policy.safe_mode)
        self.memory_preserve_threshold = runtime_policy.memory_preserve_threshold
        self.sensors_allowed = frozenset(
            item.strip().lower() for item in runtime_policy.sensors_allowed if item.strip()
        )
        self.sensors_blocked = frozenset(
            item.strip().lower() for item in runtime_policy.sensors_blocked if item.strip()
        )
        self.sensors_max_export_granularity = runtime_policy.sensors_max_export_granularity
        self.sensors_anonymization_enabled = runtime_policy.sensors_anonymization_enabled
        self.sensors_block_sensitive_by_default = runtime_policy.sensors_block_sensitive_by_default
        self.sensors_allow_sensitive_metrics_opt_in = runtime_policy.sensors_allow_sensitive_metrics_opt_in
        self.sensors_redact_machine_user_info = runtime_policy.sensors_redact_machine_user_info
        self.sensors_sensitive_metric_keys_blocklist = frozenset(
            item.strip().lower()
            for item in runtime_policy.sensors_sensitive_metric_keys_blocklist
            if item.strip()
        )
        self.social_max_influence_per_life = max(
            float(runtime_policy.social_max_influence_per_life),
            0.0,
        )
        self.social_blocked_hostile_behaviors = frozenset(
            item.strip().lower() for item in runtime_policy.social_blocked_hostile_behaviors if item.strip()
        )
        self.social_conflict_events = frozenset(
            item.strip().lower() for item in runtime_policy.social_conflict_events if item.strip()
        )
        self.social_conflict_mediation_threshold = max(
            int(runtime_policy.social_conflict_mediation_threshold), 1
        )
        self.social_conflict_window_seconds = max(
            float(runtime_policy.social_conflict_window_seconds), 1.0
        )
        self.social_mediation_cooldown_seconds = max(
            float(runtime_policy.social_mediation_cooldown_seconds), 1.0
        )
        self.social_prudent_mode_on_mediation = bool(runtime_policy.social_prudent_mode_on_mediation)
        self._mutation_timestamps: deque[datetime] = deque()
        self._skill_creation_timestamps: deque[datetime] = deque()
        self._violation_timestamps: deque[datetime] = deque()
        self._circuit_open_until: datetime | None = None
        self._runtime_call_timestamps: deque[datetime] = deque()
        self._skill_failure_timestamps: dict[str, deque[datetime]] = {}
        self._skill_cost_totals: dict[str, float] = {}
        self._skill_circuit_open_until: dict[str, datetime] = {}
        self._social_influence: dict[tuple[str, str], float] = {}
        self._social_conflict_timestamps: dict[tuple[str, str], deque[datetime]] = {}
        self._social_mediation_until: dict[tuple[str, str], datetime] = {}
        self._social_prudent_until: datetime | None = None

    def allow_sensor(self, sensor_name: str) -> bool:
        name = sensor_name.strip().lower()
        if not name:
            return False
        if name in self.sensors_blocked:
            self._journal_sensor_access_denial(
                sensor_name=sensor_name,
                reason="sensor explicitly blocked by policy.sensors.blocked",
            )
            return False
        if self.sensors_allowed and name not in self.sensors_allowed:
            self._journal_sensor_access_denial(
                sensor_name=sensor_name,
                reason="sensor not present in policy.sensors.allowed allowlist",
            )
            return False
        return True

    def sanitize_sensor_metrics(
        self,
        *,
        sensor_name: str,
        metrics: Mapping[str, Any],
        requested_granularity: str = "detailed",
        explicit_sensitive_opt_in: bool = False,
    ) -> dict[str, Any]:
        if not self.allow_sensor(sensor_name):
            return {}

        requested = requested_granularity.strip().lower()
        order = {"minimal": 0, "standard": 1, "detailed": 2}
        requested_level = order.get(requested, 2)
        max_level = order.get(self.sensors_max_export_granularity, 1)
        effective_level = min(requested_level, max_level)
        effective_granularity = ("minimal", "standard", "detailed")[effective_level]
        allowed_by_granularity: dict[str, set[str]] = {
            "host_metrics": {
                "minimal": {
                    "cpu_percent",
                    "ram_used_percent",
                    "disk_used_percent",
                    "host_temperature_c",
                },
                "standard": {
                    "cpu_percent",
                    "cpu_load_1m",
                    "ram_used_percent",
                    "ram_available_mb",
                    "disk_used_percent",
                    "disk_free_gb",
                    "host_temperature_c",
                    "process_cpu_percent",
                    "process_rss_mb",
                },
                "detailed": set(metrics.keys()),
            }
        }
        sensor_key = sensor_name.strip().lower()
        sensor_rules = allowed_by_granularity.get(sensor_key, {})
        allowed_keys = sensor_rules.get(effective_granularity, set(metrics.keys()))
        payload = {key: value for key, value in metrics.items() if key in allowed_keys}

        sensitive_opt_in_enabled = explicit_sensitive_opt_in and (
            self.sensors_allow_sensitive_metrics_opt_in
        )
        if (
            self.sensors_anonymization_enabled
            and self.sensors_block_sensitive_by_default
            and not sensitive_opt_in_enabled
        ):
            payload = {
                key: value
                for key, value in payload.items()
                if key.strip().lower() not in self.sensors_sensitive_metric_keys_blocklist
            }
        if self.sensors_anonymization_enabled and self.sensors_redact_machine_user_info:
            payload = {
                key: value
                for key, value in payload.items()
                if not any(
                    marker in key.strip().lower()
                    for marker in ("host", "hostname", "user", "username", "path")
                )
                or key in {"host_temperature_c"}
            }
        return payload

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def mutations_enabled(self) -> bool:
        if self.safe_mode:
            return False
        if self._circuit_open_until is None:
            return True
        if self._now() < self._circuit_open_until:
            return False
        self._circuit_open_until = None
        return True

    def mutation_lock_reason(self) -> str | None:
        if self.safe_mode:
            return "safe-mode enabled"
        if self._circuit_open_until is not None and self._now() < self._circuit_open_until:
            return "circuit-breaker open after repeated violations"
        return None

    def _prune_history(self) -> None:
        now = self._now()
        quota_cutoff = now - timedelta(seconds=self.mutation_quota_window_seconds)
        while self._mutation_timestamps and self._mutation_timestamps[0] < quota_cutoff:
            self._mutation_timestamps.popleft()
        violation_cutoff = now - timedelta(seconds=self.circuit_breaker_window_seconds)
        while self._violation_timestamps and self._violation_timestamps[0] < violation_cutoff:
            self._violation_timestamps.popleft()
        creation_cutoff = now - timedelta(seconds=self.skill_creation_quota_window_seconds)
        while (
            self._skill_creation_timestamps
            and self._skill_creation_timestamps[0] < creation_cutoff
        ):
            self._skill_creation_timestamps.popleft()
        runtime_cutoff = now - timedelta(hours=1)
        while self._runtime_call_timestamps and self._runtime_call_timestamps[0] < runtime_cutoff:
            self._runtime_call_timestamps.popleft()
        for skill_name, failures in list(self._skill_failure_timestamps.items()):
            failure_cutoff = now - timedelta(seconds=self.skill_circuit_breaker_cooldown_seconds)
            while failures and failures[0] < failure_cutoff:
                failures.popleft()
            if not failures:
                self._skill_failure_timestamps.pop(skill_name, None)
                self._skill_cost_totals.pop(skill_name, None)
        for skill_name, open_until in list(self._skill_circuit_open_until.items()):
            if now >= open_until:
                self._skill_circuit_open_until.pop(skill_name, None)
        social_cutoff = now - timedelta(seconds=self.social_conflict_window_seconds)
        for pair, timestamps in list(self._social_conflict_timestamps.items()):
            while timestamps and timestamps[0] < social_cutoff:
                timestamps.popleft()
            if not timestamps:
                self._social_conflict_timestamps.pop(pair, None)
        for pair, open_until in list(self._social_mediation_until.items()):
            if now >= open_until:
                self._social_mediation_until.pop(pair, None)
        if self._social_prudent_until is not None and now >= self._social_prudent_until:
            self._social_prudent_until = None

    def record_violation(self, *, category: str, severity: str = "high") -> None:
        self._prune_history()
        now = self._now()
        was_open = self._circuit_open_until is not None and now < self._circuit_open_until
        self._violation_timestamps.append(now)
        if not was_open and len(self._violation_timestamps) >= self.circuit_breaker_threshold:
            self._circuit_open_until = now + timedelta(seconds=self.circuit_breaker_cooldown_seconds)
            log.error(
                "governance circuit breaker opened: category=%s severity=%s threshold=%s cooldown=%ss",
                category,
                severity,
                self.circuit_breaker_threshold,
                self.circuit_breaker_cooldown_seconds,
            )

    def _relative(self, target: Path, root: Path) -> Path:
        target_resolved = target.resolve()
        root_resolved = root.resolve()
        try:
            return target_resolved.relative_to(root_resolved)
        except ValueError:
            return target_resolved

    @staticmethod
    def _matches(rel: Path, prefixes: tuple[str, ...]) -> bool:
        rel_txt = rel.as_posix()
        return any(rel_txt == p or rel_txt.startswith(f"{p}/") for p in prefixes)

    def _skill_circuit_open(self, skill_name: str) -> bool:
        open_until = self._skill_circuit_open_until.get(skill_name)
        return open_until is not None and self._now() < open_until

    @staticmethod
    def _pair_key(life_a: str, life_b: str) -> tuple[str, str]:
        return tuple(sorted((life_a.strip().lower(), life_b.strip().lower())))

    def social_prudent_mode_enabled(self) -> bool:
        self._prune_history()
        return self._social_prudent_until is not None and self._now() < self._social_prudent_until

    def evaluate_interlife_interaction(
        self,
        *,
        source_life: str,
        target_life: str,
        interaction: str,
        influence_delta: float = 0.0,
    ) -> GovernanceDecision:
        self._prune_history()
        interaction_key = interaction.strip().lower()
        pair = self._pair_key(source_life, target_life)
        if not pair[0] or not pair[1] or pair[0] == pair[1]:
            decision = GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason="inter-life interaction requires two distinct lives",
                corrective_action="retry with distinct source_life and target_life identifiers",
                severity="medium",
            )
            self._journal_decision(
                decision=decision,
                target=Path(f"interaction://{source_life}->{target_life}/{interaction_key or 'unknown'}"),
                justification="Décision bloquée: interaction inter-vies invalide (identifiants incohérents).",
                category="inter_life",
            )
            return decision
        if interaction_key in self.social_blocked_hostile_behaviors:
            decision = GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"explicit hostile behavior '{interaction_key}' is blocked by policy",
                corrective_action="remove hostile behavior and retry with neutral collaboration protocol",
                severity="critical",
            )
            self._journal_decision(
                decision=decision,
                target=Path(f"interaction://{pair[0]}->{pair[1]}/{interaction_key}"),
                justification="Décision bloquée: comportement hostile explicite détecté entre vies.",
                category="inter_life",
            )
            return decision
        mediation_until = self._social_mediation_until.get(pair)
        if mediation_until is not None and self._now() < mediation_until:
            decision = GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason="interaction paused by active mediation cooldown for this life pair",
                corrective_action="wait for mediation cooldown expiry before resuming interactions",
                severity="high",
            )
            self._journal_decision(
                decision=decision,
                target=Path(f"interaction://{pair[0]}->{pair[1]}/{interaction_key}"),
                justification="Décision bloquée: médiation active, interactions conflictuelles en pause.",
                category="inter_life",
            )
            return decision
        if self.social_prudent_mode_enabled():
            decision = GovernanceDecision(
                level=AUTH_REVIEW_REQUIRED,
                allowed=False,
                reason="global prudent mode active after social mediation escalation",
                corrective_action="wait for prudent window expiry or request manual supervision",
                severity="medium",
            )
            self._journal_decision(
                decision=decision,
                target=Path(f"interaction://{pair[0]}->{pair[1]}/{interaction_key}"),
                justification="Décision prudente: mode prudent global actif suite à une médiation.",
                category="inter_life",
            )
            return decision
        projected_influence = self._social_influence.get(pair, 0.0) + float(influence_delta)
        if abs(projected_influence) > self.social_max_influence_per_life:
            decision = GovernanceDecision(
                level=AUTH_REVIEW_REQUIRED,
                allowed=False,
                reason=(
                    "inter-life influence cap exceeded: "
                    f"|{projected_influence:.3f}|>{self.social_max_influence_per_life:.3f}"
                ),
                corrective_action="reduce influence transfer or trigger supervised negotiation",
                severity="medium",
            )
            self._journal_decision(
                decision=decision,
                target=Path(f"interaction://{pair[0]}->{pair[1]}/{interaction_key}"),
                justification="Décision prudente: plafond d'influence inter-vies dépassé.",
                category="inter_life",
            )
            return decision
        return GovernanceDecision(
            level=AUTH_AUTO,
            allowed=True,
            reason=f"inter-life interaction '{interaction_key}' authorized",
            corrective_action="none",
            severity="info",
        )

    def record_interlife_interaction(
        self,
        *,
        source_life: str,
        target_life: str,
        interaction: str,
        influence_delta: float = 0.0,
    ) -> GovernanceDecision:
        decision = self.evaluate_interlife_interaction(
            source_life=source_life,
            target_life=target_life,
            interaction=interaction,
            influence_delta=influence_delta,
        )
        pair = self._pair_key(source_life, target_life)
        interaction_key = interaction.strip().lower()
        if not decision.allowed:
            return decision
        self._social_influence[pair] = self._social_influence.get(pair, 0.0) + float(influence_delta)
        if interaction_key in self.social_conflict_events:
            now = self._now()
            timestamps = self._social_conflict_timestamps.setdefault(pair, deque())
            timestamps.append(now)
            if len(timestamps) >= self.social_conflict_mediation_threshold:
                self._social_mediation_until[pair] = now + timedelta(
                    seconds=self.social_mediation_cooldown_seconds
                )
                if self.social_prudent_mode_on_mediation:
                    self._social_prudent_until = now + timedelta(
                        seconds=self.social_mediation_cooldown_seconds
                    )
                mediation_decision = GovernanceDecision(
                    level=AUTH_BLOCKED,
                    allowed=False,
                    reason=(
                        "conflict threshold reached: automatic mediation/cooldown activated "
                        f"({len(timestamps)}/{self.social_conflict_mediation_threshold})"
                    ),
                    corrective_action=(
                        "pause conflicting interactions; resume with prudent mode and manual reconciliation"
                    ),
                    severity="high",
                )
                self._journal_decision(
                    decision=mediation_decision,
                    target=Path(f"interaction://{pair[0]}->{pair[1]}/mediation"),
                    justification=(
                        "Médiation automatique déclenchée: seuil de conflit atteint, "
                        "interactions conflictuelles suspendues."
                    ),
                    category="inter_life",
                )
        return decision

    def evaluate_skill_execution(
        self,
        *,
        skill_name: str,
        capability: str | None = None,
        operation_cost: float = 0.0,
    ) -> GovernanceDecision:
        self._prune_history()
        normalized_capability = (capability or "").strip().lower()
        normalized_skill = skill_name.strip().lower()
        skill_family = normalized_skill.split(".", 1)[0]
        if normalized_capability in self.runtime_blacklisted_capabilities:
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"capability '{normalized_capability}' blacklisted by runtime policy",
                corrective_action="remove blacklisted capability or request manual authorization",
                severity="high",
            )
        if self._skill_circuit_open(normalized_skill):
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"skill circuit-breaker active for '{normalized_skill}'",
                corrective_action="wait cooldown before re-enabling this skill",
                severity="critical",
            )
        if len(self._runtime_call_timestamps) >= self.runtime_call_quota_per_hour:
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"runtime call quota exceeded ({self.runtime_call_quota_per_hour}/h)",
                corrective_action="wait for hourly window reset",
                severity="medium",
            )
        if self.safe_mode and skill_family in self.safe_mode_review_required_skill_families:
            return GovernanceDecision(
                level=AUTH_REVIEW_REQUIRED,
                allowed=False,
                reason=(
                    f"safe-mode requires manual review for skill family '{skill_family}'"
                ),
                corrective_action="request human approval before executing this skill family",
                severity="high",
            )
        if operation_cost >= self.skill_circuit_breaker_cost_threshold:
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=(
                    "skill execution blocked: operation cost exceeds "
                    f"threshold ({operation_cost:.2f}>={self.skill_circuit_breaker_cost_threshold:.2f})"
                ),
                corrective_action="reduce execution cost or split task before retry",
                severity="high",
            )
        return GovernanceDecision(
            level=AUTH_AUTO,
            allowed=True,
            reason=f"skill '{normalized_skill}' authorized for runtime execution",
            corrective_action="none",
            severity="info",
        )

    def record_skill_execution(
        self,
        *,
        skill_name: str,
        success: bool,
        operation_cost: float = 0.0,
    ) -> None:
        self._prune_history()
        now = self._now()
        normalized_skill = skill_name.strip().lower()
        self._runtime_call_timestamps.append(now)
        if success:
            self._skill_failure_timestamps.pop(normalized_skill, None)
            self._skill_cost_totals.pop(normalized_skill, None)
            return
        failures = self._skill_failure_timestamps.setdefault(normalized_skill, deque())
        failures.append(now)
        self._skill_cost_totals[normalized_skill] = (
            self._skill_cost_totals.get(normalized_skill, 0.0) + max(operation_cost, 0.0)
        )
        if (
            len(failures) >= self.skill_circuit_breaker_failure_threshold
            or self._skill_cost_totals[normalized_skill] >= self.auto_rollback_cost_threshold
            or len(failures) >= self.auto_rollback_failure_threshold
        ):
            self._skill_circuit_open_until[normalized_skill] = now + timedelta(
                seconds=self.skill_circuit_breaker_cooldown_seconds
            )

    def skill_reactivation_allowed(self, skill_name: str) -> bool:
        self._prune_history()
        return not self._skill_circuit_open(skill_name.strip().lower())

    def simulate_write(
        self,
        target: Path,
        *,
        root: Path | None = None,
        operation: str = "mutation_write",
    ) -> GovernanceDecision:
        """Simulate authorization before a filesystem write."""

        self._prune_history()
        if self.safe_mode:
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason="safe-mode blocks all mutation writes",
                corrective_action="disable safe-mode to resume autonomous mutations",
                severity="high",
            )
        if not self.mutations_enabled():
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason="circuit-breaker active after repeated governance/sandbox violations",
                corrective_action="wait cooldown or reset governance counters",
                severity="critical",
            )
        if len(self._mutation_timestamps) >= self.mutation_quota_per_window:
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=(
                    "mutation quota exceeded "
                    f"({self.mutation_quota_per_window}/{self.mutation_quota_window_seconds:.0f}s)"
                ),
                corrective_action="wait for quota window reset or reduce mutation frequency",
                severity="medium",
            )
        if operation == "skill_creation" and (
            len(self._skill_creation_timestamps) >= self.skill_creation_quota_per_window
        ):
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=(
                    "skill-creation quota exceeded "
                    f"({self.skill_creation_quota_per_window}/{self.skill_creation_quota_window_seconds:.0f}s)"
                ),
                corrective_action="wait for quota reset or reduce automatic skill genesis attempts",
                severity="medium",
            )

        if root is None:
            root = target.parent.parent if target.parent.name == "skills" else target.parent
        rel = self._relative(target, root)

        if rel.is_absolute():
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"target '{target}' is outside governed root '{root}'",
                corrective_action="write inside an organism skills/ directory",
                severity="high",
            )

        if self._matches(rel, self.forbidden_paths):
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"path '{rel.as_posix()}' is in forbidden zone",
                corrective_action="choose a path under an allowlisted mutable zone",
                severity="high",
            )
        if self._matches(rel, self.force_allow_paths):
            return GovernanceDecision(
                level=AUTH_FORCED,
                allowed=True,
                reason=f"path '{rel.as_posix()}' autorisé par override force_allow_paths",
                corrective_action="none",
                severity="warn",
            )

        if self._matches(rel, self.review_required_paths):
            if self.value_weights.securite >= self.value_weights.utilite_utilisateur:
                return GovernanceDecision(
                    level=AUTH_BLOCKED,
                    allowed=False,
                    reason=(
                        f"path '{rel.as_posix()}' escalated to blocked zone "
                        "by value weights (security-first)"
                    ),
                    corrective_action="request explicit human review before mutating this zone",
                    severity="critical",
                )
            return GovernanceDecision(
                level=AUTH_REVIEW_REQUIRED,
                allowed=False,
                reason=f"path '{rel.as_posix()}' requires manual review",
                corrective_action="request human review or move target to auto-authorized zone",
                severity="medium",
            )

        if self._matches(rel, self.modifiable_paths):
            if operation == "skill_creation" and self.file_creation_review_required:
                return GovernanceDecision(
                    level=AUTH_REVIEW_REQUIRED,
                    allowed=False,
                    reason=f"file creation for '{rel.as_posix()}' requires manual review",
                    corrective_action="request human review for this file creation",
                    severity="medium",
                )
            return GovernanceDecision(
                level=AUTH_AUTO,
                allowed=True,
                reason=f"path '{rel.as_posix()}' is allowlisted for autonomous writes",
                corrective_action="none",
                severity="info",
            )

        return GovernanceDecision(
            level=AUTH_BLOCKED,
            allowed=False,
            reason=f"path '{rel.as_posix()}' is not allowlisted",
            corrective_action="add this zone to policy allowlist after validation",
            severity="medium",
        )

    def enforce_write(
        self,
        target: Path,
        content: str,
        *,
        root: Path | None = None,
        operation: str = "mutation_write",
    ) -> GovernanceDecision:
        """Enforce policy with mandatory simulation before writing."""

        decision = self.simulate_write(target, root=root, operation=operation)
        if not decision.allowed:
            self.record_violation(category="governance_violation", severity=decision.severity)
            log.warning(
                "governance blocked write: target=%s level=%s severity=%s reason=%s corrective_action=%s",
                target,
                decision.level,
                decision.severity,
                decision.reason,
                decision.corrective_action,
            )
            self._journal_decision(
                decision=decision,
                target=target,
                justification=(
                    "Décision bloquée: la politique active interdit cette mutation. "
                    f"Raison policy: {decision.reason}."
                ),
            )
            return decision

        if target.exists() and self.value_weights.preservation_memoire >= self.memory_preserve_threshold:
            previous = target.read_text(encoding="utf-8")
            if len(content.strip()) < len(previous.strip()) * self.memory_preserve_threshold:
                blocked = GovernanceDecision(
                    level=AUTH_BLOCKED,
                    allowed=False,
                    reason=(
                        "write blocked by memory-preservation guard: "
                        "new content appears to truncate existing knowledge"
                    ),
                    corrective_action="retry with a non-destructive mutation or request manual review",
                    severity="high",
                )
                self._journal_decision(
                    decision=blocked,
                    target=target,
                    justification=(
                        "Décision bloquée: garde mémoire activée par la politique. "
                        f"Seuil de préservation={self.memory_preserve_threshold:.0%}."
                    ),
                )
                return blocked

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._prune_history()
        self._mutation_timestamps.append(self._now())
        if operation == "skill_creation":
            self._skill_creation_timestamps.append(self._now())
        if decision.level == AUTH_FORCED:
            self._journal_decision(
                decision=decision,
                target=target,
                justification=(
                    "Décision forcée: override explicite via force_allow_paths. "
                    f"Raison policy: {decision.reason}."
                ),
            )
        return decision

    def _journal_decision(
        self,
        *,
        decision: GovernanceDecision,
        target: Path,
        justification: str,
        category: str = "governance",
    ) -> None:
        home = Path(os.environ.get("SINGULAR_HOME", "."))
        journal = home / "mem" / _POLICY_DECISIONS_LOG
        journal.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": self._now().isoformat(),
            "decision": decision.level,
            "allowed": decision.allowed,
            "target": str(target),
            "category": category,
            "severity": decision.severity,
            "reason": decision.reason,
            "corrective_action": decision.corrective_action,
            "justification": justification,
        }
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _journal_sensor_access_denial(self, *, sensor_name: str, reason: str) -> None:
        home = Path(os.environ.get("SINGULAR_HOME", "."))
        journal = home / "mem" / _POLICY_DECISIONS_LOG
        journal.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": self._now().isoformat(),
            "decision": AUTH_BLOCKED,
            "allowed": False,
            "target": f"sensor://{sensor_name}",
            "category": "sensor_access",
            "severity": "medium",
            "reason": reason,
            "corrective_action": "explicitly allow this sensor in policy.sensors.allowed",
            "justification": "Décision bloquée: accès capteur refusé par la politique sensors.",
        }
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


__all__ = [
    "AUTH_AUTO",
    "AUTH_REVIEW_REQUIRED",
    "AUTH_BLOCKED",
    "AUTH_FORCED",
    "POLICY_SCHEMA_VERSION",
    "PolicySchemaError",
    "RuntimePolicy",
    "get_global_policy_file",
    "ensure_global_policy_file",
    "load_runtime_policy",
    "save_runtime_policy",
    "GovernanceDecision",
    "MutationGovernancePolicy",
]
