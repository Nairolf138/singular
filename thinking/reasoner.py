from __future__ import annotations

from typing import Any, Iterable, Mapping


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
    best_option: Any | None = None
    best_score = float("-inf")

    for option in options:
        outcomes: Mapping[str, float] = getattr(option, "outcomes", option)
        score = 0.0
        for name, weight in motivations.items():
            score += weight * outcomes.get(name, 0.0)
        if score > best_score:
            best_score = score
            best_option = option

    return best_option
