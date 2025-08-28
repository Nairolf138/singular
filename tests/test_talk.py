from singular.cli import main
from singular.organisms.talk import talk
from singular.memory import read_episodes


def test_talk_loop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    inputs = iter(["hello", "next", "quit"])
    monkeypatch.setenv("LLM_PROVIDER", "dummy")
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk()

    episodes = read_episodes()
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

    monkeypatch.setattr(
        "singular.organisms.talk.load_llm_provider", fake_load
    )
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda _msg: None)

    main(["talk", "--provider", "cli"])

    assert captured["provider"] == "cli"
