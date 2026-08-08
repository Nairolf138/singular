import json
from pathlib import Path

import pytest

from singular.cli import main
from singular.lives import resolve_life
from singular.memory import read_episodes, read_skills


def _write_spec(path: Path, name: str, examples: list[dict]) -> None:
    spec = {
        "name": name,
        "signature": f"{name}(x)",
        "examples": examples,
        "constraints": {"pure": True, "no_import": True, "time_ms_max": 1000},
    }
    path.write_text(json.dumps(spec), encoding="utf-8")


def test_quest_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "world"
    spec_path = tmp_path / "square.json"
    _write_spec(
        spec_path,
        "square",
        [{"input": [2], "output": 4}, {"input": [3], "output": 9}],
    )

    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)

    main(["--root", str(root), "birth", "--name", "Vie Quest"])
    life_path = resolve_life(None)
    assert life_path is not None

    main(["--root", str(root), "quest", "create", str(spec_path)])

    life_path = resolve_life(None)
    assert life_path is not None

    skill_file = life_path / "skills" / "square.py"
    assert skill_file.exists()

    skills_data = read_skills(life_path / "mem" / "skills.json")
    assert "square" in skills_data
    square_entry = skills_data["square"]
    if isinstance(square_entry, dict):
        assert square_entry.get("score") == 0.0
    else:
        assert square_entry == 0.0

    episodes = read_episodes(life_path / "mem" / "episodic.jsonl")
    assert episodes[-1]["status"] == "success"
    assert episodes[-1]["skill"] == "square"

    psyche = json.loads((life_path / "mem" / "psyche.json").read_text())
    assert psyche["last_mood"] == "proud"


def test_quest_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "world"
    spec_path = tmp_path / "bad.json"
    _write_spec(
        spec_path,
        "badskill",
        [{"input": [2], "output": 4}, {"input": [2], "output": 5}],
    )

    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)

    main(["--root", str(root), "birth", "--name", "Vie Quest"])
    life_path = resolve_life(None)
    assert life_path is not None

    with pytest.raises(RuntimeError):
        main(["--root", str(root), "quest", "create", str(spec_path)])

    assert not (life_path / "skills" / "badskill.py").exists()
    skills_data = read_skills(life_path / "mem" / "skills.json")
    assert "badskill" not in skills_data

    episodes = read_episodes(life_path / "mem" / "episodic.jsonl")
    assert episodes[-1]["status"] == "failure"

    psyche = json.loads((life_path / "mem" / "psyche.json").read_text())
    assert psyche["last_mood"] == "frustrated"


def test_quest_example_prints_complete_json(capsys: pytest.CaptureFixture[str]) -> None:
    main(["quest", "--example"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "repair_loop"
    assert payload["constraints"] == {
        "pure": True,
        "no_import": True,
        "time_ms_max": 50,
    }
    assert payload["triggers"] == [{"signal": "noise", "gte": 0.5}]


def test_quest_schema_prints_without_active_life(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["quest", "--schema"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["required"] == ["name", "signature", "examples", "constraints"]
    assert payload["properties"]["constraints"]["properties"]["pure"] == {"const": True}


def test_quest_invalid_spec_does_not_create_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "world"
    spec_path = tmp_path / "invalid.json"
    spec_path.write_text(
        json.dumps(
            {
                "name": "broken",
                "signature": "broken(x)",
                "examples": [],
                "constraints": {"pure": True, "no_import": True, "time_ms_max": 50},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)

    main(["--root", str(root), "birth", "--name", "Vie Quest Invalid"])
    life_path = resolve_life(None)
    assert life_path is not None
    before = {path.relative_to(life_path) for path in life_path.rglob("*")}

    assert main(["--root", str(root), "quest", "create", str(spec_path)]) == 2

    after = {path.relative_to(life_path) for path in life_path.rglob("*")}
    assert after == before
    assert not (life_path / "skills" / "broken.py").exists()


@pytest.mark.parametrize(
    ("filename", "contents", "message"),
    [
        ("missing.json", None, "introuvable"),
        ("broken.json", "{not json", "JSON invalide"),
    ],
)
def test_quest_reports_file_input_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    filename: str,
    contents: str | None,
    message: str,
) -> None:
    root = tmp_path / "world"
    path = tmp_path / filename
    if contents is not None:
        path.write_text(contents, encoding="utf-8")
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    main(["--root", str(root), "birth", "--name", "Input Errors"])
    capsys.readouterr()

    assert main(["--root", str(root), "quest", "create", str(path)]) == 2

    error = capsys.readouterr().err
    assert str(path) in error
    assert message in error
    assert "quest create <spec>" in error
    assert "quest --example" in error
    assert "quest --schema" in error


def test_quest_reports_unreadable_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "world"
    path = tmp_path / "unreadable.json"
    path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def deny_read(target: Path, *args: object, **kwargs: object) -> str:
        if target == path:
            raise PermissionError("permission denied")
        return original_read_text(target, *args, **kwargs)

    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    main(["--root", str(root), "birth", "--name", "Unreadable Input"])
    capsys.readouterr()
    monkeypatch.setattr(Path, "read_text", deny_read)

    assert main(["--root", str(root), "quest", "create", str(path)]) == 2
    assert f"spécification illisible: {path}" in capsys.readouterr().err


def test_quest_spec_cannot_be_confused_with_subcommand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "spec.json"
    _write_spec(path, "skill", [{"input": [1], "output": 1}])

    with pytest.raises(SystemExit) as exc_info:
        main(["quest", str(path)])

    assert exc_info.value.code == 2
    error = capsys.readouterr().err
    assert "invalid choice" in error
    assert "create" in error and "list" in error
