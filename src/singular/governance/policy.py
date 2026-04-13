"""Governance policy for mutation and reproduction writes."""

from __future__ import annotations

from dataclasses import dataclass
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
    ) -> None:
        self.modifiable_paths = tuple(p.strip("/") for p in modifiable_paths)
        self.review_required_paths = tuple(p.strip("/") for p in review_required_paths)
        self.forbidden_paths = tuple(p.strip("/") for p in forbidden_paths)
        self.value_weights = (value_weights or ValueWeights()).normalized()

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

        if root is None:
            root = target.parent.parent if target.parent.name == "skills" else target.parent
        rel = self._relative(target, root)

        if rel.is_absolute():
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"target '{target}' is outside governed root '{root}'",
                corrective_action="write inside an organism skills/ directory",
            )

        if self._matches(rel, self.forbidden_paths):
            return GovernanceDecision(
                level=AUTH_BLOCKED,
                allowed=False,
                reason=f"path '{rel.as_posix()}' is in forbidden zone",
                corrective_action="choose a path under an allowlisted mutable zone",
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
                )
            return GovernanceDecision(
                level=AUTH_REVIEW_REQUIRED,
                allowed=False,
                reason=f"path '{rel.as_posix()}' requires manual review",
                corrective_action="request human review or move target to auto-authorized zone",
            )

        if self._matches(rel, self.modifiable_paths):
            return GovernanceDecision(
                level=AUTH_AUTO,
                allowed=True,
                reason=f"path '{rel.as_posix()}' is allowlisted for autonomous writes",
                corrective_action="none",
            )

        return GovernanceDecision(
            level=AUTH_BLOCKED,
            allowed=False,
            reason=f"path '{rel.as_posix()}' is not allowlisted",
            corrective_action="add this zone to policy allowlist after validation",
        )

    def enforce_write(self, target: Path, content: str, *, root: Path | None = None) -> GovernanceDecision:
        """Enforce policy with mandatory simulation before writing."""

        decision = self.simulate_write(target, root=root)
        if not decision.allowed:
            log.warning(
                "governance blocked write: target=%s level=%s reason=%s corrective_action=%s",
                target,
                decision.level,
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
                )

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return decision


__all__ = [
    "AUTH_AUTO",
    "AUTH_REVIEW_REQUIRED",
    "AUTH_BLOCKED",
    "GovernanceDecision",
    "MutationGovernancePolicy",
]
