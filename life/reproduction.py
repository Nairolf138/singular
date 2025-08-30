from __future__ import annotations

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

import ast
import random
from pathlib import Path
from typing import Tuple


__all__ = ["crossover"]


def crossover(parent_a: Path, parent_b: Path, rng: random.Random | None = None) -> Tuple[str, str]:
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

    new_func = ast.FunctionDef(
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
