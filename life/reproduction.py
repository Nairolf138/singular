from __future__ import annotations

"""Utilities for reproducing organisms by combining skills."""

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

    tree_a = ast.parse(file_a.read_text(encoding="utf-8"))
    tree_b = ast.parse(file_b.read_text(encoding="utf-8"))

    func_a = next((n for n in tree_a.body if isinstance(n, ast.FunctionDef)), None)
    func_b = next((n for n in tree_b.body if isinstance(n, ast.FunctionDef)), None)
    if func_a is None or func_b is None:
        raise ValueError("skills must contain a function definition")

    split_a = len(func_a.body) // 2
    split_b = len(func_b.body) // 2
    new_body = func_a.body[:split_a] + func_b.body[split_b:]
    if not new_body:
        new_body = [ast.Pass()]

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
