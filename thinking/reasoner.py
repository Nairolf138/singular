from __future__ import annotations

from typing import Any, Iterable, Mapping

from singular.beliefs.store import BeliefStore


def evaluate_actions(agent: Any, options: Iterable[Any]) -> Any:
    """Return the action that best aligns with the agent's motivations.

    Parameters
    ----------
    agent:
        Object exposing a ``motivations`` mapping of motivation names to
        numeric weights.
    options:
        Iterable of candidate actions.  Each option should provide an
        ``outcomes`` mapping describing the expected value for each motivation.

    The function computes a score for each option by taking the weighted sum
    of its outcomes using the agent's motivations and returns the option with
    the highest score.  If multiple options tie, the first one encountered is
    returned.
    """

    motivations: Mapping[str, float] = getattr(agent, "motivations", {})
    beliefs = BeliefStore()
    best_option: Any | None = None
    best_score = float("-inf")

    for option in options:
        outcomes: Mapping[str, float] = getattr(option, "outcomes", option)
        hypothesis = getattr(option, "hypothesis", None) or getattr(option, "action", None)
        if hypothesis is None:
            hypothesis = str(getattr(option, "name", "generic"))
        belief_confidence = beliefs.get_confidence(f"action:{hypothesis}", default=0.5)
        score = 0.0
        for name, weight in motivations.items():
            score += weight * outcomes.get(name, 0.0)
        score *= 0.5 + belief_confidence
        if score > best_score:
            best_score = score
            best_option = option

    return best_option
