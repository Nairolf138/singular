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

    main(["--root", str(root), "quest", str(spec_path)])

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
        main(["--root", str(root), "quest", str(spec_path)])

    assert not (life_path / "skills" / "badskill.py").exists()
    skills_data = read_skills(life_path / "mem" / "skills.json")
    assert "badskill" not in skills_data

    episodes = read_episodes(life_path / "mem" / "episodic.jsonl")
    assert episodes[-1]["status"] == "failure"

    psyche = json.loads((life_path / "mem" / "psyche.json").read_text())
    assert psyche["last_mood"] == "frustrated"
