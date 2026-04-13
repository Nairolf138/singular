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
            "circuit_breaker_threshold": 3,
            "circuit_breaker_window_seconds": 180.0,
            "circuit_breaker_cooldown_seconds": 300.0,
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


@dataclass(frozen=True)
class RuntimePolicy:
    """Strict, versioned governance policy loaded from ``policy.yaml``."""

    version: int
    memory_preserve_threshold: float
    forgetting_enabled: bool
    forgetting_max_episodic_entries: int
    modifiable_paths: tuple[str, ...]
    review_required_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    force_allow_paths: tuple[str, ...]
    safe_mode: bool
    mutation_quota_per_window: int
    mutation_quota_window_seconds: float
    circuit_breaker_threshold: int
    circuit_breaker_window_seconds: float
    circuit_breaker_cooldown_seconds: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "memory": {"preserve_threshold": self.memory_preserve_threshold},
            "forgetting": {
                "enabled": self.forgetting_enabled,
                "max_episodic_entries": self.forgetting_max_episodic_entries,
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
                "circuit_breaker_threshold": self.circuit_breaker_threshold,
                "circuit_breaker_window_seconds": self.circuit_breaker_window_seconds,
                "circuit_breaker_cooldown_seconds": self.circuit_breaker_cooldown_seconds,
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
            f"Autonomie: quota={self.mutation_quota_per_window}/{self.mutation_quota_window_seconds:.0f}s, circuit={self.circuit_breaker_threshold} violations/{self.circuit_breaker_window_seconds:.0f}s, safe_mode={'on' if self.safe_mode else 'off'}.",
        ]


def _validate_runtime_policy(payload: Mapping[str, Any]) -> RuntimePolicy:
    root_keys = {"version", "memory", "forgetting", "permissions", "autonomy"}
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
    permissions = payload["permissions"]
    autonomy = payload["autonomy"]
    for section_name, section in (
        ("memory", memory),
        ("forgetting", forgetting),
        ("permissions", permissions),
        ("autonomy", autonomy),
    ):
        if not isinstance(section, Mapping):
            raise PolicySchemaError(f"section '{section_name}' must be a mapping")

    expected_memory = {"preserve_threshold"}
    expected_forgetting = {"enabled", "max_episodic_entries"}
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
        "circuit_breaker_threshold",
        "circuit_breaker_window_seconds",
        "circuit_breaker_cooldown_seconds",
    }
    for name, section, expected in (
        ("memory", memory, expected_memory),
        ("forgetting", forgetting, expected_forgetting),
        ("permissions", permissions, expected_permissions),
        ("autonomy", autonomy, expected_autonomy),
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

    preserve_threshold = _coerce_float(memory, "preserve_threshold", minimum=0.0)
    if preserve_threshold > 1.0:
        raise PolicySchemaError("'preserve_threshold' must be <= 1.0")

    return RuntimePolicy(
        version=version,
        memory_preserve_threshold=preserve_threshold,
        forgetting_enabled=_coerce_bool(forgetting, "enabled"),
        forgetting_max_episodic_entries=_coerce_int(forgetting, "max_episodic_entries", minimum=1),
        modifiable_paths=_coerce_path_list(permissions, "modifiable_paths"),
        review_required_paths=_coerce_path_list(permissions, "review_required_paths"),
        forbidden_paths=_coerce_path_list(permissions, "forbidden_paths"),
        force_allow_paths=_coerce_path_list(permissions, "force_allow_paths"),
        safe_mode=_coerce_bool(autonomy, "safe_mode"),
        mutation_quota_per_window=_coerce_int(autonomy, "mutation_quota_per_window", minimum=1),
        mutation_quota_window_seconds=_coerce_float(autonomy, "mutation_quota_window_seconds", minimum=1.0),
        circuit_breaker_threshold=_coerce_int(autonomy, "circuit_breaker_threshold", minimum=1),
        circuit_breaker_window_seconds=_coerce_float(autonomy, "circuit_breaker_window_seconds", minimum=1.0),
        circuit_breaker_cooldown_seconds=_coerce_float(autonomy, "circuit_breaker_cooldown_seconds", minimum=1.0),
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
        circuit_breaker_threshold: int = 3,
        circuit_breaker_window_seconds: float = 180.0,
        circuit_breaker_cooldown_seconds: float = 300.0,
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
        self.safe_mode = bool(safe_mode or runtime_policy.safe_mode)
        self.memory_preserve_threshold = runtime_policy.memory_preserve_threshold
        self._mutation_timestamps: deque[datetime] = deque()
        self._violation_timestamps: deque[datetime] = deque()
        self._circuit_open_until: datetime | None = None

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

    def record_violation(self, *, category: str, severity: str = "high") -> None:
        self._prune_history()
        now = self._now()
        self._violation_timestamps.append(now)
        if len(self._violation_timestamps) >= self.circuit_breaker_threshold:
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

    def simulate_write(self, target: Path, *, root: Path | None = None) -> GovernanceDecision:
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

    def enforce_write(self, target: Path, content: str, *, root: Path | None = None) -> GovernanceDecision:
        """Enforce policy with mandatory simulation before writing."""

        decision = self.simulate_write(target, root=root)
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
        self, *, decision: GovernanceDecision, target: Path, justification: str
    ) -> None:
        home = Path(os.environ.get("SINGULAR_HOME", "."))
        journal = home / "mem" / _POLICY_DECISIONS_LOG
        journal.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": self._now().isoformat(),
            "decision": decision.level,
            "allowed": decision.allowed,
            "target": str(target),
            "severity": decision.severity,
            "reason": decision.reason,
            "corrective_action": decision.corrective_action,
            "justification": justification,
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
