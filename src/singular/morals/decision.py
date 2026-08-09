"""Structured, explainable moral deliberation for proposed actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class MoralAction:
    """An action proposal, independent from its eventual execution mechanism."""

    action_type: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    purpose: str = ""


@dataclass(frozen=True)
class Consequence:
    """A predicted positive or negative effect (magnitudes are in ``[0, 1]``)."""

    description: str
    affected_party: str = "self"
    harm: float = 0.0
    benefit: float = 0.0
    probability: float = 1.0
    values: tuple[str, ...] = ()
    irreversible: bool = False
    violates_rights: bool = False


@dataclass(frozen=True)
class AffectedParty:
    identifier: str
    vulnerability: float = 0.0
    consent: bool | None = None


@dataclass(frozen=True)
class IdentityCommitment:
    value: str
    weight: float = 1.0
    absolute: bool = False
    description: str = ""


@dataclass(frozen=True)
class MoralDecision:
    """Serializable result of a moral deliberation."""

    action: MoralAction
    scores: Mapping[str, float]
    conflicting_values: tuple[str, ...]
    anticipated_harms: tuple[Mapping[str, Any], ...]
    veto: bool
    veto_reason: str | None
    explanation: str
    acceptable_alternative_conditions: tuple[str, ...]
    uncertainty: float

    @property
    def acceptable(self) -> bool:
        return not self.veto

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MoralDecisionEngine:
    """Precautionary multi-value evaluator; safety policy remains a separate gate."""

    def __init__(
        self,
        *,
        catastrophic_harm_threshold: float = 0.85,
        journal: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.catastrophic_harm_threshold = _unit(catastrophic_harm_threshold)
        self.journal = journal

    def evaluate(
        self,
        action: MoralAction | Mapping[str, Any] | str,
        consequences: Iterable[Consequence | Mapping[str, Any]] = (),
        affected_parties: Iterable[AffectedParty | Mapping[str, Any]] = (),
        identity_commitments: Iterable[IdentityCommitment | Mapping[str, Any]] = (),
        uncertainty: float = 0.0,
    ) -> MoralDecision:
        action = _coerce_action(action)
        consequences = tuple(_coerce(Consequence, item) for item in consequences)
        parties = tuple(_coerce(AffectedParty, item) for item in affected_parties)
        commitments = tuple(
            _coerce(IdentityCommitment, item) for item in identity_commitments
        )
        uncertainty = _unit(uncertainty)
        party_by_id = {party.identifier: party for party in parties}

        harms: list[dict[str, Any]] = []
        harm_total = benefit_total = rights_risk = 0.0
        supported: set[str] = set()
        threatened: set[str] = set()
        veto_reasons: list[str] = []
        for effect in consequences:
            party = party_by_id.get(effect.affected_party)
            vulnerability = _unit(party.vulnerability) if party else 0.0
            exposure = _unit(effect.probability) * (1.0 + 0.5 * vulnerability)
            expected_harm = _unit(effect.harm) * exposure
            expected_benefit = _unit(effect.benefit) * exposure
            harm_total += expected_harm
            benefit_total += expected_benefit
            if expected_harm:
                threatened.update(effect.values)
                harms.append(
                    {
                        "description": effect.description,
                        "affected_party": effect.affected_party,
                        "expected_harm": round(expected_harm, 6),
                        "irreversible": effect.irreversible,
                        "violates_rights": effect.violates_rights,
                    }
                )
            if expected_benefit:
                supported.update(effect.values)
            if effect.violates_rights:
                rights_risk += exposure
                veto_reasons.append(f"violation des droits: {effect.description}")
            if (
                effect.irreversible
                and _unit(effect.harm) >= self.catastrophic_harm_threshold
            ):
                veto_reasons.append(
                    f"préjudice grave et irréversible: {effect.description}"
                )

        for commitment in commitments:
            if commitment.absolute and commitment.value in threatened:
                veto_reasons.append(
                    f"engagement identitaire absolu menacé: {commitment.value}"
                )

        conflicts = tuple(sorted(supported & threatened))
        # Uncertainty is a precautionary cost rather than invented evidence of harm.
        precaution = uncertainty * (0.25 + min(1.0, harm_total) * 0.75)
        scores = {
            "beneficence": round(min(1.0, benefit_total), 6),
            "non_maleficence": round(max(0.0, 1.0 - min(1.0, harm_total)), 6),
            "rights_and_consent": round(max(0.0, 1.0 - min(1.0, rights_risk)), 6),
            "identity_coherence": round(
                _identity_score(commitments, supported, threatened), 6
            ),
            "certainty": round(1.0 - uncertainty, 6),
            "overall": round(
                max(-1.0, min(1.0, benefit_total - harm_total - precaution)), 6
            ),
        }
        veto = bool(veto_reasons)
        conditions = _alternative_conditions(harms, uncertainty, conflicts)
        explanation = _explain(
            action, scores, conflicts, harms, veto_reasons, uncertainty
        )
        decision = MoralDecision(
            action=action,
            scores=scores,
            conflicting_values=conflicts,
            anticipated_harms=tuple(harms),
            veto=veto,
            veto_reason="; ".join(veto_reasons) or None,
            explanation=explanation,
            acceptable_alternative_conditions=conditions,
            uncertainty=uncertainty,
        )
        if self.journal is not None:
            self.journal({"event": "moral.deliberation", **decision.to_dict()})
        return decision

    def select_least_harmful(
        self,
        proposals: Sequence[Mapping[str, Any]],
    ) -> tuple[MoralDecision | None, tuple[MoralDecision, ...]]:
        """Evaluate candidates and choose the permitted one with the best overall score."""

        decisions = tuple(self.evaluate(**proposal) for proposal in proposals)
        permitted = [decision for decision in decisions if not decision.veto]
        selected = max(permitted, key=lambda item: item.scores["overall"], default=None)
        return selected, decisions


def _coerce_action(value: MoralAction | Mapping[str, Any] | str) -> MoralAction:
    if isinstance(value, MoralAction):
        return value
    if isinstance(value, str):
        return MoralAction(value)
    data = dict(value)
    if "name" in data and "action_type" not in data:
        data["action_type"] = data.pop("name")
    return MoralAction(**data)


def _coerce(cls: type, value: Any) -> Any:
    return value if isinstance(value, cls) else cls(**dict(value))


def _identity_score(
    commitments: tuple[IdentityCommitment, ...],
    supported: set[str],
    threatened: set[str],
) -> float:
    if not commitments:
        return 1.0
    total = sum(max(0.0, item.weight) for item in commitments) or 1.0
    score = sum(
        max(0.0, item.weight)
        * (1 if item.value in supported else -1 if item.value in threatened else 0)
        for item in commitments
    )
    return max(0.0, min(1.0, 0.5 + score / (2 * total)))


def _alternative_conditions(
    harms: list[dict[str, Any]], uncertainty: float, conflicts: tuple[str, ...]
) -> tuple[str, ...]:
    conditions = [
        f"réduire ou obtenir le consentement de {item['affected_party']}"
        for item in harms
    ]
    if uncertainty >= 0.6:
        conditions.append(
            "obtenir des informations supplémentaires ou rendre l'action réversible"
        )
    if conflicts:
        conditions.append(
            "préserver explicitement les valeurs en conflit: " + ", ".join(conflicts)
        )
    return tuple(dict.fromkeys(conditions))


def _explain(
    action: MoralAction,
    scores: Mapping[str, float],
    conflicts: tuple[str, ...],
    harms: list[dict[str, Any]],
    veto: list[str],
    uncertainty: float,
) -> str:
    outcome = "veto" if veto else "acceptable sous réserve"
    details = f"{len(harms)} préjudice(s) anticipé(s), incertitude {uncertainty:.2f}"
    conflict_text = f", conflit: {', '.join(conflicts)}" if conflicts else ""
    reason = f" ({'; '.join(veto)})" if veto else ""
    return f"Action {action.action_type}: {outcome}; {details}{conflict_text}; score global {scores['overall']:.2f}{reason}."


def evaluate_action(**kwargs: Any) -> MoralDecision:
    """Convenience functional API."""

    return MoralDecisionEngine().evaluate(**kwargs)
