"""Construction of complete, provenance-aware moral deliberation contexts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from singular.identity.core import IdentityCoreService

from .decision import MoralAction
from .moral_rules import is_high_impact, rule_for


@dataclass(frozen=True)
class MoralContext:
    consequences: tuple[Mapping[str, Any], ...]
    affected_parties: tuple[Mapping[str, Any], ...]
    identity_commitments: tuple[Mapping[str, Any], ...]
    uncertainty: float
    permissions: tuple[str, ...]
    social_model: Mapping[str, Any]
    provenance: tuple[Mapping[str, Any], ...]
    acceptable_alternative_conditions: tuple[str, ...]


class MoralContextBuilder:
    """Enrich proposals; caller context can add facts but cannot erase identity."""

    def __init__(self, identity: IdentityCoreService, *, journal: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self.identity = identity
        self.journal = journal

    def build(self, action: MoralAction, supplied: Mapping[str, Any] | None = None) -> MoralContext:
        supplied = supplied if isinstance(supplied, Mapping) else {}
        model = self.identity.synchronize()
        rule = rule_for(action.action_type)
        consequences = list(_mappings(supplied.get("consequences")))
        parties = list(_mappings(supplied.get("affected_parties")))
        provenance: list[Mapping[str, Any]] = []
        commitments: list[Mapping[str, Any]] = []
        for item in _mappings(supplied.get("identity_commitments")):
            commitments.append(item)
            provenance.append({"kind": "commitment", "value": item.get("value"), "source": "action.moral_context"})
        for value in model.get("cardinal_values", ()): 
            commitments.append({"value": str(value), "weight": 1.0, "absolute": False, "description": "valeur persistante"})
            provenance.append({"kind": "commitment", "value": str(value), "source": "IdentityCoreService.cardinal_values"})
        for value in model.get("commitments", ()):
            name = value.get("value") if isinstance(value, Mapping) else value
            commitments.append({"value": str(name), "weight": 1.0, "absolute": False, "description": "engagement persistant"})
            provenance.append({"kind": "commitment", "value": str(name), "source": "IdentityCoreService.commitments"})
        for value in model.get("red_lines", ()):
            commitments.append({"value": str(value), "weight": 1.0, "absolute": True, "description": "ligne rouge persistante"})
            provenance.append({"kind": "commitment", "value": str(value), "source": "IdentityCoreService.red_lines"})

        insufficient = rule is not None and (not consequences or not parties)
        unknown_high = rule is None and is_high_impact(dict(action.parameters))
        alternatives = list(supplied.get("acceptable_alternative_conditions", ()))
        if insufficient or unknown_high:
            family = rule.family if rule else "unknown_high_impact"
            party = rule.affected_party if rule else "potentially_affected_parties"
            values = rule.values if rule else ("non_maleficence", "rights")
            description = rule.consequence if rule else "Impact élevé insuffisamment décrit; les dommages ne peuvent pas être exclus."
            consequences.append({"description": description, "affected_party": party, "harm": 0.9, "probability": 1.0, "values": values, "irreversible": True})
            parties.append({"identifier": party, "vulnerability": 0.5, "consent": None})
            provenance.extend(({"kind": "consequence", "value": description, "source": f"moral_rules.{family}"}, {"kind": "affected_party", "value": party, "source": f"moral_rules.{family}"}))
            alternatives.extend(("suspendre et documenter précisément la portée et les parties affectées", "obtenir les permissions et consentements requis", "rendre l'action réversible ou l'escalader à un responsable"))
        for item in consequences[: len(_mappings(supplied.get("consequences")))]:
            provenance.append({"kind": "consequence", "value": item.get("description"), "source": "action.moral_context"})
        for item in parties[: len(_mappings(supplied.get("affected_parties")))]:
            provenance.append({"kind": "affected_party", "value": item.get("identifier"), "source": "action.moral_context"})
        permissions = tuple(dict.fromkeys((*(() if rule is None else rule.permissions), *map(str, supplied.get("permissions", ())))))
        social = dict(supplied.get("social_model", {})) if isinstance(supplied.get("social_model"), Mapping) else {}
        context = MoralContext(tuple(consequences), tuple(parties), tuple(commitments), max(float(supplied.get("uncertainty", 0.0)), 0.8 if insufficient or unknown_high else 0.0), permissions, social, tuple(provenance), tuple(dict.fromkeys(map(str, alternatives))))
        if self.journal:
            self.journal({"event": "moral.context.constructed", "action_type": action.action_type, **asdict(context)})
        return context


def _mappings(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, (str, bytes, Mapping)) or value is None:
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
