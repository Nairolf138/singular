from pathlib import Path
import json

import pytest

from singular.cli import main
from singular.lives import load_registry, resolve_life
from singular.memory import read_episodes


def test_lives_management(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "universe"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(
        "singular.organisms.talk.load_llm_provider", lambda _name: None, raising=False
    )

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    registry = load_registry()
    alpha_slug = registry["active"]
    assert isinstance(alpha_slug, str)
    alpha_meta = registry["lives"][alpha_slug]
    alpha_path = Path(alpha_meta.path)

    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    registry = load_registry()
    beta_slug = registry["active"]
    assert isinstance(beta_slug, str)
    beta_meta = registry["lives"][beta_slug]
    beta_path = Path(beta_meta.path)
    assert beta_slug != alpha_slug

    beta_before = list(read_episodes(beta_path / "mem" / "episodic.jsonl"))

    main(["--root", str(root), "lives", "use", alpha_meta.slug])
    registry = load_registry()
    assert registry["active"] == alpha_meta.slug

    main(["--root", str(root), "talk", "--prompt", "bonjour"])

    alpha_episodes = read_episodes(alpha_path / "mem" / "episodic.jsonl")
    assert any(
        episode.get("role") == "user" and episode.get("text") == "bonjour"
        for episode in alpha_episodes
    )
    beta_after = read_episodes(beta_path / "mem" / "episodic.jsonl")
    assert beta_before == beta_after

    main(["--root", str(root), "lives", "delete", beta_meta.slug])
    registry = load_registry()
    assert registry["active"] == alpha_meta.slug
    assert not beta_path.exists()
    assert resolve_life(None) == alpha_path


def test_loop_ticks_legacy_message(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["loop", "--ticks", "10"])

    assert excinfo.value.code == 2
    stderr = capsys.readouterr().err
    assert "--ticks" in stderr
    assert "singular loop --budget-seconds <secondes>" in stderr
    assert "1 tick ≈ 1 seconde" in stderr


def test_ecosystem_run_accepts_multiple_lives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "ecosystem"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    alpha_slug = load_registry()["active"]
    assert isinstance(alpha_slug, str)
    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    beta_slug = load_registry()["active"]
    assert isinstance(beta_slug, str)

    called: dict[str, object] = {}

    def fake_loop_run(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr("singular.runs.loop.loop", fake_loop_run)
    main(
        [
            "--root",
            str(root),
            "ecosystem",
            "run",
            "--life",
            alpha_slug,
            "--life-group",
            beta_slug,
            "--budget-seconds",
            "0.1",
        ]
    )

    skills_dirs = called["skills_dirs"]
    assert isinstance(skills_dirs, dict)
    assert alpha_slug in skills_dirs
    assert beta_slug in skills_dirs
    assert Path(skills_dirs[alpha_slug]).name == "skills"


def test_lives_list_supports_json_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "universe"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    main(["--root", str(root), "lives", "create", "--name", "Beta"])
    capsys.readouterr()

    main(["--root", str(root), "--format", "json", "lives", "list"])
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["active"]
    assert len(payload["lives"]) == 2
    assert {"Alpha", "Beta"} == {item["name"] for item in payload["lives"]}


def test_status_supports_subcommand_format_and_verbose(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "status-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])

    captured: dict[str, object] = {}

    def fake_status(*, verbose: bool = False, output_format: str = "plain") -> None:
        captured["verbose"] = verbose
        captured["output_format"] = output_format

    monkeypatch.setattr("singular.organisms.status.status", fake_status)
    main(["--root", str(root), "status", "--verbose", "--format", "table"])

    assert captured["verbose"] is True
    assert captured["output_format"] == "table"


def test_cli_root_context_message_when_switching_registry_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"

    monkeypatch.setenv("SINGULAR_ROOT", str(root_a))
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root_a), "lives", "list"])
    first_out = capsys.readouterr().out
    assert "Vous utilisez un autre registre de vies" not in first_out

    main(["--root", str(root_b), "lives", "list"])
    second_out = capsys.readouterr().out
    assert "Vous utilisez un autre registre de vies" in second_out
    assert str(root_b.resolve()) in second_out
    assert str(root_a.resolve()) in second_out


def test_birth_prints_registry_root_used(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "registry-root"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "birth", "--name", "Gamma"])
    out = capsys.readouterr().out
    assert "Registre de vies utilisé:" in out
    assert str(root.resolve()) in out


def test_lives_archive_memorial_clone_guided_commands(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "guided"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)

    main(["--root", str(root), "lives", "create", "--name", "Alpha"])
    capsys.readouterr()
    main(["--root", str(root), "lives", "archive", "alpha"])
    archive_out = capsys.readouterr().out
    assert "Vie archivée" in archive_out
    assert "singular lives memorial" in archive_out

    main(
        [
            "--root",
            str(root),
            "lives",
            "memorial",
            "alpha",
            "--message",
            "Merci Alpha",
        ]
    )
    memorial_out = capsys.readouterr().out
    assert "Mémorial enregistré" in memorial_out
    assert (root / "lives" / "alpha" / "mem" / "memorial.json").exists()

    main(["--root", str(root), "lives", "clone", "alpha", "--new-name", "Alpha 2"])
    registry = load_registry()
    cloned_slug = registry["active"]
    assert isinstance(cloned_slug, str)
    cloned_meta = registry["lives"][cloned_slug]
    assert "alpha" in cloned_meta.parents
    assert cloned_meta.lineage_depth >= 1
    clone_out = capsys.readouterr().out
    assert "Vie clonée" in clone_out
    assert "singular status --verbose" in clone_out
