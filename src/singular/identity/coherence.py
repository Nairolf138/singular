"""Identity coherence checks between beliefs, goals, history, and decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from singular.io_utils import append_jsonl_line

_AUDIT_RELATIVE_PATH = Path("mem") / "identity_coherence_audit.jsonl"
_NEGATION_PREFIXES = (
    "not ",
    "no ",
    "never ",
    "avoid ",
    "reject ",
    "against ",
)


@dataclass(frozen=True)
class IdentityInvariants:
    """Non-negotiable long-term identity constraints."""

    life_name: str
    cardinal_values: tuple[str, ...]
    long_term_commitments: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IdentityInvariants":
        return cls(
            life_name=str(payload.get("life_name", "")).strip(),
            cardinal_values=tuple(_normalize_token(value) for value in payload.get("cardinal_values", []) if str(value).strip()),
            long_term_commitments=tuple(
                _normalize_token(value)
                for value in payload.get("long_term_commitments", [])
                if str(value).strip()
            ),
        )


@dataclass(frozen=True)
class CoherenceDecision:
    """Decision gate output."""

    status: str
    accepted: bool
    reasons: tuple[str, ...]
    contradictions: tuple[dict[str, str], ...]
    invariant_violations: tuple[str, ...]


class IdentityCoherenceGuard:
    """Detects drift and guards invariant-breaking decisions."""

    def __init__(
        self,
        *,
        invariants: IdentityInvariants,
        root: Path | str = Path("."),
    ) -> None:
        self.invariants = invariants
        self.root = Path(root)
        self.audit_path = self.root / _AUDIT_RELATIVE_PATH

    def evaluate_decision(
        self,
        *,
        decision: dict[str, Any],
        beliefs: list[dict[str, Any]] | None = None,
        goals: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> CoherenceDecision:
        contradictions = detect_contradictions(
            beliefs=beliefs or [], goals=goals or [], history=history or []
        )
        violations = self._check_invariants(decision)

        reasons: list[str] = []
        status = "allowed"
        accepted = True
        if contradictions:
            status = "degraded"
            reasons.append("decision degraded: contextual contradictions detected")
        if violations:
            status = "blocked"
            accepted = False
            reasons.append("decision blocked: identity invariants violated")

        record = CoherenceDecision(
            status=status,
            accepted=accepted,
            reasons=tuple(reasons),
            contradictions=tuple(contradictions),
            invariant_violations=tuple(violations),
        )
        self._audit_if_needed(decision=decision, record=record)
        return record

    def _check_invariants(self, decision: dict[str, Any]) -> list[str]:
        violations: list[str] = []
        proposed_name = str(decision.get("life_name", "")).strip()
        if proposed_name and self.invariants.life_name and proposed_name != self.invariants.life_name:
            violations.append("life_name_mismatch")

        decision_values = {
            _normalize_token(v)
            for v in decision.get("values", [])
            if str(v).strip()
        }
        missing_values = [
            value for value in self.invariants.cardinal_values if value not in decision_values
        ]
        if missing_values:
            violations.append("cardinal_values_missing:" + ",".join(missing_values))

        summary = _normalize_text(
            " ".join(
                str(part)
                for part in (
                    decision.get("action", ""),
                    decision.get("summary", ""),
                    decision.get("rationale", ""),
                )
                if str(part).strip()
            )
        )
        for commitment in self.invariants.long_term_commitments:
            if commitment and _is_negated(summary, commitment):
                violations.append(f"long_term_commitment_negated:{commitment}")
        return violations

    def _audit_if_needed(self, *, decision: dict[str, Any], record: CoherenceDecision) -> None:
        if record.status == "allowed":
            return
        append_jsonl_line(
            self.audit_path,
            {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "status": record.status,
                "accepted": record.accepted,
                "reasons": list(record.reasons),
                "contradictions": list(record.contradictions),
                "invariant_violations": list(record.invariant_violations),
                "decision": decision,
            },
        )


def detect_contradictions(
    *,
    beliefs: list[dict[str, Any]],
    goals: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Detect proposition-level contradictions across beliefs, goals, and history."""

    statements: list[tuple[str, str, bool, str]] = []
    statements.extend(_extract_statements("belief", beliefs, ("hypothesis", "statement", "name")))
    statements.extend(_extract_statements("goal", goals, ("name", "objective", "summary")))
    statements.extend(_extract_statements("history", history, ("summary", "event", "note")))

    by_canonical: dict[str, list[tuple[str, str, bool]]] = {}
    for source, text, positive, canonical in statements:
        if not canonical:
            continue
        by_canonical.setdefault(canonical, []).append((source, text, positive))

    contradictions: list[dict[str, str]] = []
    for canonical, variants in by_canonical.items():
        positives = [item for item in variants if item[2]]
        negatives = [item for item in variants if not item[2]]
        if positives and negatives:
            contradictions.append(
                {
                    "canonical": canonical,
                    "positive": f"{positives[0][0]}:{positives[0][1]}",
                    "negative": f"{negatives[0][0]}:{negatives[0][1]}",
                }
            )
    return contradictions


def _extract_statements(
    source: str,
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> list[tuple[str, str, bool, str]]:
    rows: list[tuple[str, str, bool, str]] = []
    for item in payloads:
        for key in keys:
            raw = str(item.get(key, "")).strip()
            if not raw:
                continue
            positive, canonical = _canonicalize_statement(raw)
            rows.append((source, raw, positive, canonical))
            break
    return rows


def _canonicalize_statement(value: str) -> tuple[bool, str]:
    lowered = _normalize_text(value)
    for prefix in _NEGATION_PREFIXES:
        if lowered.startswith(prefix):
            return False, lowered[len(prefix) :].strip()
    return True, lowered


def _is_negated(summary: str, commitment: str) -> bool:
    for prefix in _NEGATION_PREFIXES:
        if f"{prefix}{commitment}" in summary:
            return True
    return False


def _normalize_text(value: str) -> str:
    cleaned = " ".join(str(value).strip().lower().split())
    for punctuation in ",.;:!?()[]{}\"'":
        cleaned = cleaned.replace(punctuation, "")
    return cleaned


def _normalize_token(value: Any) -> str:
    return _normalize_text(str(value))
