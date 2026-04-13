"""Governance policy for mutation and reproduction writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import deque
import logging
from pathlib import Path

from .values import ValueWeights

log = logging.getLogger(__name__)


AUTH_AUTO = "auto"
AUTH_REVIEW_REQUIRED = "review-required"
AUTH_BLOCKED = "blocked"


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
        self.modifiable_paths = tuple(p.strip("/") for p in modifiable_paths)
        self.review_required_paths = tuple(p.strip("/") for p in review_required_paths)
        self.forbidden_paths = tuple(p.strip("/") for p in forbidden_paths)
        self.value_weights = (value_weights or ValueWeights()).normalized()
        self.mutation_quota_per_window = max(int(mutation_quota_per_window), 1)
        self.mutation_quota_window_seconds = max(float(mutation_quota_window_seconds), 1.0)
        self.circuit_breaker_threshold = max(int(circuit_breaker_threshold), 1)
        self.circuit_breaker_window_seconds = max(float(circuit_breaker_window_seconds), 1.0)
        self.circuit_breaker_cooldown_seconds = max(float(circuit_breaker_cooldown_seconds), 1.0)
        self.safe_mode = bool(safe_mode)
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
            return decision

        if target.exists() and self.value_weights.preservation_memoire >= 0.6:
            previous = target.read_text(encoding="utf-8")
            if len(content.strip()) < len(previous.strip()) * 0.2:
                return GovernanceDecision(
                    level=AUTH_BLOCKED,
                    allowed=False,
                    reason=(
                        "write blocked by memory-preservation guard: "
                        "new content appears to truncate existing knowledge"
                    ),
                    corrective_action="retry with a non-destructive mutation or request manual review",
                    severity="high",
                )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._prune_history()
        self._mutation_timestamps.append(self._now())
        return decision


__all__ = [
    "AUTH_AUTO",
    "AUTH_REVIEW_REQUIRED",
    "AUTH_BLOCKED",
    "GovernanceDecision",
    "MutationGovernancePolicy",
]
