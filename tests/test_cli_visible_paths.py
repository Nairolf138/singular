from __future__ import annotations

from pathlib import Path

import pytest

from singular.cli import main


@pytest.fixture
def life_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    root = tmp_path / "root"
    main(["--root", str(root), "lives", "create", "--name", "Ada"])
    # Register values that the CLI itself assigned so monkeypatch restores the
    # process environment after this in-process CLI test.
    monkeypatch.setenv("SINGULAR_ROOT", str(root))
    monkeypatch.setenv("SINGULAR_HOME", str(root / "lives" / "ada"))
    return root


@pytest.mark.parametrize(
    "command",
    [
        ["skills", "list"],
        ["quest", "list"],
        ["self-narrative", "summarize"],
        ["cognition", "self-observe"],
        ["social", "interact", "bob", "cooperation"],
    ],
)
def test_visible_paths_accept_global_and_local_life(
    life_root: Path, command: list[str]
) -> None:
    assert main(["--root", str(life_root), "--life", "ada", *command]) in (None, 0)
    assert main(["--root", str(life_root), *command, "--life", "ada"]) in (None, 0)


@pytest.mark.parametrize(
    "command",
    [
        ["skills", "list"],
        ["quest", "list"],
        ["self-narrative", "summarize"],
        ["cognition", "self-observe"],
        ["social", "interact", "bob", "cooperation"],
    ],
)
def test_visible_paths_reject_unknown_life(life_root: Path, command: list[str]) -> None:
    with pytest.raises(SystemExit, match="Vie introuvable: missing"):
        main(["--root", str(life_root), *command, "--life", "missing"])


@pytest.mark.parametrize(
    "group", ["skills", "quest", "social", "self-narrative", "cognition"]
)
def test_visible_groups_require_an_action(group: str) -> None:
    with pytest.raises(SystemExit) as error:
        main([group])
    assert error.value.code == 2


def test_deprecated_quest_alias_reports_migration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["quest", "--example"])
    assert "quest create" in capsys.readouterr().err


def test_quest_create_documented_inspection_syntax(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["quest", "create", "--example"]) == 0
    assert '"name"' in capsys.readouterr().out
