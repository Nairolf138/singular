import json
from pathlib import Path

import pytest

from singular.cli import main
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
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "square.json"
    _write_spec(
        spec_path,
        "square",
        [{"input": [2], "output": 4}, {"input": [3], "output": 9}],
    )

    main(["quest", str(spec_path)])

    skill_file = tmp_path / "skills" / "square.py"
    assert skill_file.exists()

    skills_data = read_skills(tmp_path / "mem" / "skills.json")
    assert skills_data == {"square": 0.0}

    episodes = read_episodes(tmp_path / "mem" / "episodic.jsonl")
    assert episodes[-1]["status"] == "success"
    assert episodes[-1]["skill"] == "square"

    psyche = json.loads((tmp_path / "mem" / "psyche.json").read_text())
    assert psyche["last_mood"] == "proud"


def test_quest_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "bad.json"
    _write_spec(
        spec_path,
        "badskill",
        [{"input": [2], "output": 4}, {"input": [2], "output": 5}],
    )

    with pytest.raises(RuntimeError):
        main(["quest", str(spec_path)])

    assert not (tmp_path / "skills" / "badskill.py").exists()
    skills_data = read_skills(tmp_path / "mem" / "skills.json")
    assert skills_data == {}

    episodes = read_episodes(tmp_path / "mem" / "episodic.jsonl")
    assert episodes[-1]["status"] == "failure"

    psyche = json.loads((tmp_path / "mem" / "psyche.json").read_text())
    assert psyche["last_mood"] == "frustrated"
