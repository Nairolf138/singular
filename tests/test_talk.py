import random

from singular.cli import main
from singular.organisms.talk import talk, _default_reply
from singular.memory import read_episodes


def test_talk_loop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    inputs = iter(["hello", "next", "quit"])
    monkeypatch.setenv("LLM_PROVIDER", "idontexist")
    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", lambda _name: None)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk()

    episodes = [e for e in read_episodes() if e.get("event") != "perception"]
    assert len(episodes) == 4
    assert episodes[0]["role"] == "user"
    assert episodes[1]["role"] == "assistant"
    assert "Mood: neutral" in episodes[1]["text"]
    assert any("Reminder:" in out for out in outputs)


def test_cli_provider_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "env")

    captured: dict[str, str] = {}

    def fake_load(name: str | None):
        captured["provider"] = name or ""
        return lambda _: "ok"

    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", fake_load)
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda _msg: None)

    main(["talk", "--provider", "cli"])

    assert captured["provider"] == "cli"


def _run_talk(monkeypatch, tmp_path, seed, run):
    subdir = tmp_path / f"{seed}_{run}"
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", lambda _name: None)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))
    talk(seed=seed)
    return outputs[0]


def test_talk_seed_controls_stub(monkeypatch, tmp_path):
    first = _run_talk(monkeypatch, tmp_path, 123, 1)
    second = _run_talk(monkeypatch, tmp_path, 123, 2)
    third = _run_talk(monkeypatch, tmp_path, 321, 3)
    expected_first = _default_reply("hello", random.Random(123)) + " | Mood: neutral"
    expected_third = _default_reply("hello", random.Random(321)) + " | Mood: neutral"
    assert first == expected_first
    assert second == expected_first
    assert third == expected_third
    assert first != third
