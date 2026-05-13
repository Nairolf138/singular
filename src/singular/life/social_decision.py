"""Social decision rules for multi-life resource interactions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from singular.social.graph import SocialGraph


@dataclass(frozen=True, slots=True)
class SocialDecision:
    """A deterministic decision about how one life should treat a peer."""

    peer: str
    action: str
    affinity: float
    trust: float
    rivalry: float
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def decide_social_actions(
    actor: str,
    peers: Iterable[str],
    social_graph: SocialGraph,
) -> list[SocialDecision]:
    """Return deterministic social decisions for ``actor`` against each peer.

    Rules are intentionally simple and auditable:
    * high trust and affinity => help;
    * high rivalry => compete, or avoid when trust is too low;
    * otherwise stay neutral.
    """

    decisions: list[SocialDecision] = []
    for peer in sorted(str(name) for name in peers if str(name) != str(actor)):
        relation = social_graph.get_relation(actor, peer)
        affinity = _metric(relation, "affinity", 0.5)
        trust = _metric(relation, "trust", 0.5)
        rivalry = _metric(relation, "rivalry", 0.0)

        if trust >= 0.7 and affinity >= 0.7 and rivalry < 0.65:
            action = "help"
            reason = "trust_and_affinity_high"
        elif rivalry >= 0.75 and trust < 0.4:
            action = "avoid"
            reason = "rivalry_high_trust_low"
        elif rivalry >= 0.65:
            action = "compete"
            reason = "rivalry_high"
        else:
            action = "neutral"
            reason = "balanced_relation"

        decisions.append(
            SocialDecision(
                peer=peer,
                action=action,
                affinity=affinity,
                trust=trust,
                rivalry=rivalry,
                reason=reason,
            )
        )
    return decisions


def _metric(relation: Mapping[str, object], name: str, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(relation.get(name, default))))
    except (TypeError, ValueError):
        return default
