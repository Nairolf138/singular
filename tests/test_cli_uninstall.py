from pathlib import Path

import singular.cli as cli


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".sentinel").write_text("ok", encoding="utf-8")


def test_uninstall_keep_lives_preserves_lives_tree(tmp_path: Path) -> None:
    root = tmp_path / "universe"
    lives_dir = root / "lives"
    registry = lives_dir / "registry.json"
    life_dir = lives_dir / "alpha"
    mem_dir = root / "mem"
    runs_dir = root / "runs"

    _mkdir(life_dir)
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text('{"active": null, "lives": {}}', encoding="utf-8")
    _mkdir(mem_dir)
    _mkdir(runs_dir)

    exit_code = cli.main(
        ["--root", str(root), "uninstall", "--keep-lives", "--yes"]
    )

    assert exit_code == 0
    assert lives_dir.exists()
    assert registry.exists()
    assert life_dir.exists()
    assert not mem_dir.exists()
    assert not runs_dir.exists()


def test_uninstall_purge_lives_removes_all_data(tmp_path: Path) -> None:
    root = tmp_path / "universe"
    lives_dir = root / "lives"
    life_dir = lives_dir / "alpha"
    mem_dir = root / "mem"
    runs_dir = root / "runs"

    _mkdir(life_dir)
    _mkdir(mem_dir)
    _mkdir(runs_dir)

    exit_code = cli.main(
        ["--root", str(root), "uninstall", "--purge-lives", "--yes"]
    )

    assert exit_code == 0
    assert not lives_dir.exists()
    assert not mem_dir.exists()
    assert not runs_dir.exists()
    assert not root.exists()


def test_uninstall_purge_requires_confirmation_without_yes(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "universe"
    lives_dir = root / "lives"
    life_dir = lives_dir / "alpha"
    mem_dir = root / "mem"
    runs_dir = root / "runs"
    _mkdir(life_dir)
    _mkdir(mem_dir)
    _mkdir(runs_dir)

    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    exit_code = cli.main(["--root", str(root), "uninstall", "--purge-lives"])

    assert exit_code == 0
    assert lives_dir.exists()
    assert mem_dir.exists()
    assert runs_dir.exists()
