from __future__ import annotations

import json
from pathlib import Path

import pytest

from singular.cli import main
from singular.lives import load_registry


@pytest.mark.parametrize(
    "creation_command",
    [["birth"], ["lives", "create"]],
)
def test_birth_alias_and_lives_create_persist_initial_psyche_overrides(
    creation_command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(
        [
            "--root",
            str(root),
            *creation_command,
            "--name",
            "Prudent",
            "--curiosity",
            "0.2",
            "--patience",
            "0.9",
            "--playfulness",
            "0.1",
            "--optimism",
            "0.55",
            "--resilience",
            "0.95",
        ]
    )

    registry = load_registry()
    slug = registry["active"]
    assert isinstance(slug, str)
    meta = registry["lives"][slug]

    psyche_path = Path(meta.path) / "mem" / "psyche.json"
    payload = json.loads(psyche_path.read_text(encoding="utf-8"))

    assert payload["curiosity"] == 0.2
    assert payload["patience"] == 0.9
    assert payload["playfulness"] == 0.1
    assert payload["optimism"] == 0.55
    assert payload["resilience"] == 0.95


@pytest.mark.parametrize(
    "creation_command",
    [["birth"], ["lives", "create"]],
)
def test_birth_alias_and_lives_create_reject_out_of_range_psyche_override(
    creation_command: list[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([*creation_command, "--curiosity", "1.5"])
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    "creation_command",
    [["birth"], ["lives", "create"]],
)
def test_birth_alias_and_lives_create_use_minimal_starter_profile_by_default(
    creation_command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), *creation_command, "--name", "Minimal"])

    registry = load_registry()
    slug = registry["active"]
    life_home = Path(registry["lives"][slug].path)
    skills = sorted(path.name for path in (life_home / "skills").glob("*.py"))
    assert skills == ["addition.py", "multiplication.py", "subtraction.py"]


@pytest.mark.parametrize(
    "creation_command",
    [["birth"], ["lives", "create"]],
)
def test_birth_alias_and_lives_create_apply_explicit_starter_profile(
    creation_command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(
        [
            "--root",
            str(root),
            *creation_command,
            "--name",
            "Operator",
            "--starter-profile",
            "ops",
        ]
    )

    registry = load_registry()
    slug = registry["active"]
    life_home = Path(registry["lives"][slug].path)
    skills = sorted(path.name for path in (life_home / "skills").glob("*.py"))
    assert skills == [
        "intent_classification.py",
        "metrics.py",
        "planning.py",
        "summary.py",
        "validation.py",
    ]


@pytest.mark.parametrize(
    "creation_command",
    [["birth"], ["lives", "create"]],
)
def test_birth_alias_and_lives_create_unknown_profile_falls_back_to_minimal_and_adds_explicit_skills(
    creation_command: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(
        [
            "--root",
            str(root),
            *creation_command,
            "--name",
            "Fallback",
            "--starter-profile",
            "unknown-profile",
            "--starter-skill",
            "summary",
        ]
    )

    registry = load_registry()
    slug = registry["active"]
    life_home = Path(registry["lives"][slug].path)
    skills = sorted(path.name for path in (life_home / "skills").glob("*.py"))
    assert skills == ["addition.py", "multiplication.py", "subtraction.py", "summary.py"]


def test_birth_prints_deprecation_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "birth", "--name", "Legacy"])
    stderr = capsys.readouterr().err
    assert "déprécié" in stderr
    assert "singular lives create --name" in stderr
