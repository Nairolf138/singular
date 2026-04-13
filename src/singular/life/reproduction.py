"""Utilities for reproducing organisms by combining skills.

Limitations
-----------
The crossover strategy implemented here is intentionally simple: it merely
splices together portions of two parent function bodies. This approach comes
with a few constraints:

* Parent functions must share the exact same signature. Mismatched arguments
  would produce nonsensical hybrids and therefore raise a :class:`ValueError`.
* When a return annotation is present, at least one ``return`` statement must
  remain in the hybrid body. Otherwise the result would violate the declared
  contract and we fail fast with :class:`ValueError`.
* Parent functions need at least one statement each and the resulting hybrid
  body must not be empty.

The algorithm performs no semantic analysis beyond these checks; generated code
may still be meaningless even though it is syntactically valid.
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

from singular.governance.policy import MutationGovernancePolicy


__all__ = [
    "ReproductionVariationPolicy",
    "InheritanceRules",
    "compute_parent_compatibility",
    "inherit_psyche",
    "inherit_values",
    "inherit_episodic_memory",
    "crossover",
    "authorize_reproduction_write",
]


@dataclass(frozen=True)
class ReproductionVariationPolicy:
    """Bound mutation intensity and parental compatibility."""

    mutation_intensity: float = 0.1
    compatibility_threshold: float = 0.3
    numeric_min: float = 0.0
    numeric_max: float = 1.0


@dataclass(frozen=True)
class InheritanceRules:
    """Describe inheritance behaviour for non-code memory artefacts."""

    inherit_partial_memory: bool = True
    memory_episode_limit: int = 50




def authorize_reproduction_write(
    target_path: Path,
    code: str,
    governance_policy: MutationGovernancePolicy | None = None,
) -> tuple[bool, str]:
    """Simulate then enforce policy for reproduction output writes."""

    policy = governance_policy or MutationGovernancePolicy()
    root = target_path.parent.parent if target_path.parent.name == "skills" else target_path.parent
    decision = policy.simulate_write(target_path, root=root)
    if not decision.allowed:
        return False, f"{decision.reason}; corrective_action={decision.corrective_action}"

    enforced = policy.enforce_write(target_path, code, root=root)
    if not enforced.allowed:
        return False, f"{enforced.reason}; corrective_action={enforced.corrective_action}"
    return True, "authorized"


def compute_parent_compatibility(parent_a: dict[str, Any], parent_b: dict[str, Any]) -> float:
    """Estimate compatibility based on shared psyche keys."""

    keys_a = set(parent_a.keys())
    keys_b = set(parent_b.keys())
    union = keys_a | keys_b
    if not union:
        return 1.0
    return len(keys_a & keys_b) / len(union)


def _bounded_numeric_inheritance(
    val_a: float,
    val_b: float,
    *,
    rng: random.Random,
    policy: ReproductionVariationPolicy,
) -> float:
    base = (val_a + val_b) / 2
    amplitude = abs(val_a - val_b) * max(0.0, policy.mutation_intensity)
    variation = rng.uniform(-amplitude, amplitude)
    mutated = base + variation
    return max(policy.numeric_min, min(policy.numeric_max, mutated))


def inherit_psyche(
    psyche_a: dict[str, Any],
    psyche_b: dict[str, Any],
    *,
    rng: random.Random,
    policy: ReproductionVariationPolicy,
) -> dict[str, Any]:
    """Inherit psyche traits/values under variation bounds."""

    child_psyche: dict[str, Any] = {}
    for key in sorted(set(psyche_a) | set(psyche_b)):
        val_a = psyche_a.get(key)
        val_b = psyche_b.get(key)
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            child_psyche[key] = _bounded_numeric_inheritance(
                float(val_a),
                float(val_b),
                rng=rng,
                policy=policy,
            )
            continue
        options = [v for v in (val_a, val_b) if v is not None]
        if options:
            child_psyche[key] = rng.choice(options)
    return child_psyche


def inherit_values(
    values_a: dict[str, Any],
    values_b: dict[str, Any],
    *,
    rng: random.Random,
    policy: ReproductionVariationPolicy,
) -> dict[str, Any]:
    """Inherit governance values map while bounding numeric drift."""

    result: dict[str, Any] = {}
    for key in sorted(set(values_a) | set(values_b)):
        val_a = values_a.get(key)
        val_b = values_b.get(key)
        if isinstance(val_a, dict) and isinstance(val_b, dict):
            result[key] = inherit_values(val_a, val_b, rng=rng, policy=policy)
            continue
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            result[key] = _bounded_numeric_inheritance(
                float(val_a),
                float(val_b),
                rng=rng,
                policy=policy,
            )
            continue
        options = [v for v in (val_a, val_b) if v is not None]
        if options:
            result[key] = rng.choice(options)
    return result


def inherit_episodic_memory(
    episodes_a: list[dict[str, Any]],
    episodes_b: list[dict[str, Any]],
    *,
    rng: random.Random,
    rules: InheritanceRules,
) -> list[dict[str, Any]]:
    """Merge episodic memory with optional partial inheritance."""

    if not rules.inherit_partial_memory:
        return []

    combined = [*episodes_a, *episodes_b]
    if not combined:
        return []
    sample_size = min(len(combined), max(0, rules.memory_episode_limit))
    if sample_size == 0:
        return []
    if len(combined) <= sample_size:
        return combined
    selected = rng.sample(combined, sample_size)
    selected.sort(key=lambda ep: str(ep.get("ts", "")))
    return selected


def crossover(
    parent_a: Path, parent_b: Path, rng: random.Random | None = None
) -> Tuple[str, str]:
    """Create a hybrid skill from two parent skill directories.

    Parameters
    ----------
    parent_a, parent_b:
        Directories containing skill ``.py`` files. A random skill from each
        parent is chosen and their abstract syntax trees are combined to form a
        new hybrid skill. The hybrid function uses the argument signature of the
        first parent's function and merges the bodies by taking the first half of
        ``parent_a``'s statements followed by the second half of ``parent_b``'s
        statements.
    rng:
        Optional :class:`random.Random` instance for reproducibility.

    Returns
    -------
    tuple
        ``(filename, code)`` of the newly created hybrid skill.
    """

    rng = rng or random.Random()

    skills_a = list(Path(parent_a).glob("*.py"))
    skills_b = list(Path(parent_b).glob("*.py"))
    if not skills_a or not skills_b:
        raise ValueError("both parents must have at least one skill")

    file_a = rng.choice(skills_a)
    file_b = rng.choice(skills_b)

    try:
        tree_a = ast.parse(file_a.read_text(encoding="utf-8"))
    except SyntaxError as e:
        raise ValueError(f"invalid syntax in skill file {file_a}") from e

    try:
        tree_b = ast.parse(file_b.read_text(encoding="utf-8"))
    except SyntaxError as e:
        raise ValueError(f"invalid syntax in skill file {file_b}") from e

    func_a = next((n for n in tree_a.body if isinstance(n, ast.FunctionDef)), None)
    func_b = next((n for n in tree_b.body if isinstance(n, ast.FunctionDef)), None)
    if func_a is None or func_b is None:
        raise ValueError("skills must contain a function definition")

    if ast.dump(func_a.args) != ast.dump(func_b.args):
        raise ValueError("parent functions must have matching signatures")

    if not func_a.body or not func_b.body:
        raise ValueError("parent functions must not have empty bodies")

    split_a = len(func_a.body) // 2
    split_b = len(func_b.body) // 2
    new_body = func_a.body[:split_a] + func_b.body[split_b:]
    if not new_body:
        raise ValueError("resulting function body is empty")

    needs_return = func_a.returns is not None or func_b.returns is not None
    has_return = any(isinstance(n, ast.Return) for n in new_body)
    if needs_return and not has_return:
        raise ValueError("hybrid function missing required return statement")

    new_func = ast.FunctionDef(  # type: ignore[call-overload]
        name=f"hybrid_{func_a.name}_{func_b.name}",
        args=func_a.args,
        body=new_body,
        decorator_list=[],
        returns=func_a.returns or func_b.returns,
        type_comment=None,
    )

    module = ast.Module(body=[new_func], type_ignores=[])
    ast.fix_missing_locations(module)
    code = ast.unparse(module)
    filename = f"{new_func.name}.py"
    return filename, code
