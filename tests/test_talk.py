import random

from singular.cli import main
from singular.organisms.talk import talk, _default_reply
from singular.memory import read_episodes


def test_talk_loop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
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
    root = tmp_path / "world"
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "env")

    captured: dict[str, str] = {}

    def fake_load(name: str | None):
        captured["provider"] = name or ""
        return lambda _: "ok"

    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", fake_load)
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda _msg: None)

    main(["--root", str(root), "birth", "--name", "Vie Talk"])
    main(["--root", str(root), "talk", "--provider", "cli"])

    assert captured["provider"] == "cli"


def test_talk_handles_keyboard_interrupt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", lambda _name: None)

    def raise_interrupt(_=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk()

    assert any("Exiting conversation." in out for out in outputs)
    episodes = [e for e in read_episodes() if e.get("event") != "perception"]
    assert episodes == []


def test_talk_single_prompt(monkeypatch, tmp_path):
    root = tmp_path / "world"
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setattr("singular.organisms.talk.load_llm_provider", lambda _name: None)
    outputs: list[str] = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    main(["--root", str(root), "birth", "--name", "Vie Talk"])
    outputs.clear()
    main(["--root", str(root), "--seed", "123", "talk", "--prompt", "hello"])

    episodes = [e for e in read_episodes() if e.get("event") != "perception"]
    assert len(episodes) == 2
    assert episodes[0]["role"] == "user"
    assert episodes[0]["text"] == "hello"
    expected = _default_reply("hello", random.Random(123)) + " | Mood: neutral"
    assert outputs[0] == expected


def _run_talk(monkeypatch, tmp_path, seed, run):
    subdir = tmp_path / f"{seed}_{run}"
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
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
