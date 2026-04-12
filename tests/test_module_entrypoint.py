from __future__ import annotations

import ast
import runpy
import sys
import tomllib
from pathlib import Path

import pytest


def _read_project_script_target() -> str:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    return data["project"]["scripts"]["singular"]


def test_package_has_module_entrypoint() -> None:
    module_path = (
        Path(__file__).resolve().parents[1] / "src" / "singular" / "__main__.py"
    )
    assert module_path.exists(), "Le package doit exposer un point d'entrée module"


def test_module_entrypoint_matches_console_script_target() -> None:
    module_path = (
        Path(__file__).resolve().parents[1] / "src" / "singular" / "__main__.py"
    )
    module_tree = ast.parse(module_path.read_text(encoding="utf-8"))

    entry_target = _read_project_script_target()
    module_name, function_name = entry_target.split(":", maxsplit=1)
    expected_import_module = module_name.rsplit(".", maxsplit=1)[-1]

    imported_main = False
    calls_expected_function = False

    for node in module_tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {
            module_name,
            expected_import_module,
        }:
            imported_names = {alias.name for alias in node.names}
            if function_name in imported_names:
                imported_main = True

        if isinstance(node, ast.If):
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                if not isinstance(inner.func, ast.Name):
                    continue
                if inner.func.id == "SystemExit" and inner.args:
                    arg0 = inner.args[0]
                    if (
                        isinstance(arg0, ast.Call)
                        and isinstance(arg0.func, ast.Name)
                        and arg0.func.id == function_name
                    ):
                        calls_expected_function = True

    assert imported_main, (
        "Le point d'entrée module doit importer la fonction ciblée par "
        "[project.scripts].singular"
    )
    assert calls_expected_function, (
        "Le point d'entrée module doit exécuter la même fonction que "
        "l'entrypoint console script"
    )


def test_module_entrypoint_forwards_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("singular.cli.main", lambda: 7)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("singular", run_name="__main__")

    assert excinfo.value.code == 7


def test_module_entrypoint_accepts_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str] | None] = {}

    def fake_main(argv: list[str] | None = None) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("singular.cli.main", fake_main)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("singular", run_name="__main__")

    assert excinfo.value.code == 0
    # __main__.py delegates to cli.main() without passing argv explicitly.
    assert captured["argv"] is None


def test_module_entrypoint_parses_global_format_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["python", "--format", "json", "doctor"])
    monkeypatch.setattr("singular.cli._doctor", lambda *, fix=False: print("ok"))

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("singular", run_name="__main__")

    assert excinfo.value.code == 0
    assert "ok" in capsys.readouterr().out
