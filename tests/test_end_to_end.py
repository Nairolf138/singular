"""End-to-end scenarios centered on real CLI user journeys."""

from pathlib import Path

from singular.cli import main
from singular.memory import read_episodes
from singular.organisms.birth import birth
from singular.organisms.talk import talk
from singular.runs.run import run
from singular.runs.synthesize import synthesize


def test_full_workflow(monkeypatch, tmp_path):
    """Ensure the basic workflow stores code and recalls it in conversation."""

    monkeypatch.chdir(tmp_path)

    birth()
    code = run()
    synthesize(code)

    inputs = iter(["hi", "quit"])
    outputs: list[str] = []
    monkeypatch.setenv("LLM_PROVIDER", "dummy")
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk()

    episodes = [e for e in read_episodes() if e.get("event") != "perception"]
    # After run, synthesize and one talk exchange we should have four episodes
    # excluding perception captures: mutation, system (code), user, assistant
    assert len(episodes) == 4
    assert episodes[0]["event"] == "mutation"
    assert episodes[1]["text"] == code
    assert any("Mood:" in out for out in outputs)


def test_cli_user_journey_birth_talk_loop_lives_uninstall(monkeypatch, tmp_path):
    """Exercise the critical CLI journey expected by release gates."""

    root = tmp_path / "universe"
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)

    assert main(["--root", str(root), "birth", "--name", "Alpha"]) == 0

    outputs: list[str] = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))
    assert (
        main(["--root", str(root), "--seed", "42", "talk", "--prompt", "bonjour"]) == 0
    )

    active_home = Path((root / "lives").glob("*/").__next__())
    episodes = read_episodes(active_home / "mem" / "episodic.jsonl")
    assert any(
        ep.get("role") == "user" and ep.get("text") == "bonjour" for ep in episodes
    )

    skills_dir = active_home / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "calc.py").write_text("result = 1\n", encoding="utf-8")
    checkpoint = active_home / "runs" / "journey.json"
    assert (
        main(
            [
                "--root",
                str(root),
                "loop",
                "--skills-dir",
                str(skills_dir),
                "--checkpoint",
                str(checkpoint),
                "--budget-seconds",
                "0.05",
                "--run-id",
                "journey",
            ]
        )
        == 0
    )
    assert checkpoint.exists()

    assert main(["--root", str(root), "lives", "list"]) == 0
    assert main(["--root", str(root), "uninstall", "--keep-lives", "--yes"]) == 0
    assert (root / "lives").exists()
    assert not (root / "mem").exists()
    assert not (root / "runs").exists()
