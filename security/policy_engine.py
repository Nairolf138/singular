"""Policy engine authorizing action requests before execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PolicyRule:
    """Allowlist rule for one class of actions."""

    rule_id: str
    applications: frozenset[str] = frozenset({"*"})
    windows: frozenset[str] = frozenset({"*"})
    screen_zones: frozenset[str] = frozenset({"*"})
    action_types: frozenset[str] = frozenset({"*"})


@dataclass(frozen=True)
class PolicyDecision:
    """Output of the policy engine for one action request."""

    allowed: bool
    blocked: bool
    reason: str
    rule_id: str | None
    risk_level: str
    dry_run: bool
    requires_human_confirmation: bool


class ActionPolicyEngine:
    """Authorize action requests using allowlists and risk gates."""

    def __init__(
        self,
        *,
        rules: list[PolicyRule] | None = None,
        risk_thresholds: dict[str, float] | None = None,
        dry_run: bool = False,
        require_human_confirmation_for_critical: bool = True,
        confirmation_callback: Callable[[Any], bool] | None = None,
        decision_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.rules = rules or [PolicyRule(rule_id="allow_all")]
        self.risk_thresholds = risk_thresholds or {"low": 0.3, "medium": 0.7}
        self.dry_run = dry_run
        self.require_human_confirmation_for_critical = (
            require_human_confirmation_for_critical
        )
        self.confirmation_callback = confirmation_callback
        self.decision_logger = decision_logger

    def evaluate(self, request: Any) -> PolicyDecision:
        """Evaluate one action request and return a decision."""

        risk_score = self._risk_score(request)
        risk_level = self._risk_level(risk_score)
        matching_rule = self._find_matching_rule(request)

        if matching_rule is None:
            decision = PolicyDecision(
                allowed=False,
                blocked=True,
                reason="action_not_allowlisted",
                rule_id=None,
                risk_level=risk_level,
                dry_run=self.dry_run,
                requires_human_confirmation=False,
            )
            self._log_decision(request, decision)
            return decision

        is_critical = self._is_critical(request, risk_level)
        requires_confirmation = (
            self.require_human_confirmation_for_critical and is_critical
        )
        if requires_confirmation:
            is_confirmed = bool(
                self.confirmation_callback(request) if self.confirmation_callback else False
            )
            if not is_confirmed:
                decision = PolicyDecision(
                    allowed=False,
                    blocked=True,
                    reason="critical_action_requires_human_confirmation",
                    rule_id=matching_rule.rule_id,
                    risk_level=risk_level,
                    dry_run=self.dry_run,
                    requires_human_confirmation=True,
                )
                self._log_decision(request, decision)
                return decision

        decision = PolicyDecision(
            allowed=True,
            blocked=False,
            reason="dry_run" if self.dry_run else "allowed_by_rule",
            rule_id=matching_rule.rule_id,
            risk_level=risk_level,
            dry_run=self.dry_run,
            requires_human_confirmation=requires_confirmation,
        )
        self._log_decision(request, decision)
        return decision

    def _find_matching_rule(self, request: Any) -> PolicyRule | None:
        action_type = str(getattr(request, "action_type", ""))
        parameters = getattr(request, "parameters", {}) or {}
        application = str(parameters.get("application", ""))
        window = str(parameters.get("window", ""))
        screen_zone = str(parameters.get("screen_zone", ""))

        for rule in self.rules:
            if not self._in_allowlist(action_type, rule.action_types):
                continue
            if not self._in_allowlist(application, rule.applications):
                continue
            if not self._in_allowlist(window, rule.windows):
                continue
            if not self._in_allowlist(screen_zone, rule.screen_zones):
                continue
            return rule

        return None

    @staticmethod
    def _in_allowlist(value: str, allowlist: frozenset[str]) -> bool:
        return "*" in allowlist or value in allowlist

    def _risk_score(self, request: Any) -> float:
        parameters = getattr(request, "parameters", {}) or {}
        score = parameters.get("risk_score", 0.0)
        try:
            return float(score)
        except (TypeError, ValueError):
            return 0.0

    def _risk_level(self, score: float) -> str:
        low_ceiling = float(self.risk_thresholds.get("low", 0.3))
        medium_ceiling = float(self.risk_thresholds.get("medium", 0.7))

        if score <= low_ceiling:
            return "low"
        if score <= medium_ceiling:
            return "medium"
        return "high"

    @staticmethod
    def _is_critical(request: Any, risk_level: str) -> bool:
        parameters = getattr(request, "parameters", {}) or {}
        if bool(parameters.get("critical", False)):
            return True
        return risk_level == "high"

    def _log_decision(self, request: Any, decision: PolicyDecision) -> None:
        if self.decision_logger is None:
            return

        payload = {
            "action_type": str(getattr(request, "action_type", "")),
            "allowed": decision.allowed,
            "blocked": decision.blocked,
            "reason": decision.reason,
            "rule_id": decision.rule_id,
            "risk_level": decision.risk_level,
            "dry_run": decision.dry_run,
            "requires_human_confirmation": decision.requires_human_confirmation,
        }
        self.decision_logger(payload)
