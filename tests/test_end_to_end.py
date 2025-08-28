"""End-to-end scenario: birth → run → synthesize → talk."""

from singular.organisms.birth import birth
from singular.organisms.talk import talk
from singular.runs.run import run
from singular.runs.synthesize import synthesize
from singular.memory import read_episodes


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

    episodes = read_episodes()
    # After run, synthesize and one talk exchange we should have four episodes:
    #   mutation, system (code), user, assistant
    assert len(episodes) == 4
    assert episodes[0]["event"] == "mutation"
    assert episodes[1]["text"] == code
    assert any(f"Reminder: {code}" in out for out in outputs)

