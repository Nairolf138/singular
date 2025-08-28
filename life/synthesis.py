"""Skill synthesis from specifications."""

from __future__ import annotations

from pathlib import Path
import ast

from . import sandbox, quest


def _build_stub(spec: quest.Spec) -> str:
    """Return Python source implementing a mapping based on *spec* examples."""

    arity = len(spec.examples[0].inputs) if spec.examples else 0
    arg_names = [f"arg{i}" for i in range(arity)]

    # Build dictionary of examples
    keys = []
    values = []
    for ex in spec.examples:
        keys.append(ast.Constant(tuple(ex.inputs)))
        values.append(ast.Constant(ex.output))
    cases = ast.Dict(keys=keys, values=values)

    # Build function body: return cases.get((args), None)
    tuple_args = ast.Tuple([ast.Name(a, ast.Load()) for a in arg_names], ast.Load())
    get_call = ast.Call(
        func=ast.Attribute(value=ast.Name("cases", ast.Load()), attr="get", ctx=ast.Load()),
        args=[tuple_args, ast.Constant(None)],
        keywords=[],
    )
    body = [
        ast.Assign(targets=[ast.Name("cases", ast.Store())], value=cases),
        ast.Return(get_call),
    ]

    func = ast.FunctionDef(
        name=spec.name,
        args=ast.arguments(
            posonlyargs=[],
            args=[ast.arg(a) for a in arg_names],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        ),
        body=body,
        decorator_list=[],
    )

    module = ast.Module(body=[func], type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.unparse(module)


def _verify(code: str, spec: quest.Spec) -> bool:
    """Return ``True`` if *code* satisfies all examples in *spec* when run in the sandbox."""

    for ex in spec.examples:
        args = ", ".join(repr(x) for x in ex.inputs)
        test = f"{code}\nresult = {spec.name}({args})"
        try:
            out = sandbox.run(test, timeout=spec.constraints.time_ms_max / 1000)
        except Exception:
            return False
        if out != ex.output:
            return False
    return True


def synthesise(spec_path: Path, skills_dir: Path | None = None) -> Path:
    """Generate a skill from *spec_path* and persist it to *skills_dir*.

    A :class:`RuntimeError` is raised if the synthesised code fails any
    example. The time limit declared in the specification is enforced during
    verification.
    """

    spec = quest.load(spec_path)
    code = _build_stub(spec)
    if not _verify(code, spec):
        raise RuntimeError("generated skill does not satisfy examples")

    skills_dir = skills_dir or Path("skills")
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skills_dir / f"{spec.name}.py"
    skill_path.write_text(code, encoding="utf-8")

    _log_birth(spec.name)
    return skill_path


def _log_birth(name: str) -> None:
    """Append *name* to the births log."""

    log_dir = Path("runs")
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "births.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{name}\n")
