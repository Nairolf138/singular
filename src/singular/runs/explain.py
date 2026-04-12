"""Helpers for human-readable mutation explanations."""

from __future__ import annotations


def _score_impact(score_base: float, score_new: float) -> tuple[str, str]:
    delta = score_new - score_base
    if delta < 0:
        return ("amélioration", f"score {score_base:.3f} → {score_new:.3f} ({delta:.3f})")
    if delta > 0:
        return ("régression", f"score {score_base:.3f} → {score_new:.3f} (+{delta:.3f})")
    return ("stable", f"score inchangé ({score_new:.3f})")


def _perf_impact(ms_base: float, ms_new: float) -> str:
    delta = ms_new - ms_base
    if delta < 0:
        return f"perf: plus rapide ({ms_base:.2f}ms → {ms_new:.2f}ms, {delta:.2f}ms)"
    if delta > 0:
        return f"perf: plus lent ({ms_base:.2f}ms → {ms_new:.2f}ms, +{delta:.2f}ms)"
    return f"perf: inchangée ({ms_new:.2f}ms)"


def summarize_mutation(
    *,
    operator: str,
    impacted_file: str,
    accepted: bool,
    diff: str,
    ms_base: float,
    ms_new: float,
    score_base: float,
    score_new: float,
) -> str:
    """Build a compact sentence explaining a mutation decision."""

    score_status, score_msg = _score_impact(score_base, score_new)
    perf_msg = _perf_impact(ms_base, ms_new)

    if accepted:
        if score_status == "amélioration":
            reason = "acceptée (score amélioré)"
        elif score_status == "stable":
            reason = "acceptée (score stable)"
        else:
            reason = "acceptée (règle exploratoire/coévolution)"
    else:
        if score_status == "régression":
            reason = "rejetée (score dégradé)"
        else:
            reason = "rejetée (n'apporte pas de gain mesurable)"

    changed_lines = max(0, sum(1 for line in diff.splitlines() if line.startswith(("+", "-"))) - 2)

    return (
        f"op={operator}; fichier={impacted_file}; {reason}; "
        f"impact: {score_msg}; {perf_msg}; diff={changed_lines} lignes"
    )
