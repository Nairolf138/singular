import random

from singular.cli import main
from singular.memory import read_episodes
from singular.organisms.talk import _default_reply, talk
from singular.providers import (
    LLMProviderClient,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
)


def test_talk_loop(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "next", "quit"])
    monkeypatch.setenv("LLM_PROVIDER", "idontexist")
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk()

    episodes = [e for e in read_episodes() if e.get("event") != "perception"]
    assert len(episodes) == 4
    assert episodes[0]["role"] == "user"
    assert episodes[1]["role"] == "assistant"
    assert episodes[1]["raw_reply"]
    assert "Mood: neutral" in episodes[1]["text"]
    assert outputs[0] == "Provider: idontexist"
    assert any("not found" in out for out in outputs)
    assert any("Reminder:" in out for out in outputs)


def test_cli_provider_precedence(monkeypatch, tmp_path):
    root = tmp_path / "world"
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.delenv("SINGULAR_ROOT", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "env")

    captured: dict[str, str] = {}

    def fake_load(name: str | None):
        captured["provider"] = name or ""
        return LLMProviderClient(name="cli", generate=lambda _prompt, timeout=8.0: "ok")

    monkeypatch.setattr("singular.organisms.talk.load_llm_client", fake_load)
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda _msg: None)

    main(["--root", str(root), "birth", "--name", "Vie Talk"])
    main(["--root", str(root), "talk", "--provider", "cli"])

    assert captured["provider"] == "cli"


def test_talk_handles_keyboard_interrupt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)

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
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)
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
    assert outputs[0] == "Provider: stub"
    assert outputs[-1] == expected


def _run_talk(monkeypatch, tmp_path, seed, run):
    subdir = tmp_path / f"{seed}_{run}"
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))
    talk(seed=seed)
    return outputs


def test_talk_seed_controls_stub(monkeypatch, tmp_path):
    first = _run_talk(monkeypatch, tmp_path, 123, 1)
    second = _run_talk(monkeypatch, tmp_path, 123, 2)
    third = _run_talk(monkeypatch, tmp_path, 321, 3)
    expected_first = _default_reply("hello", random.Random(123)) + " | Mood: neutral"
    expected_third = _default_reply("hello", random.Random(321)) + " | Mood: neutral"
    assert first[0] == "Provider: stub"
    assert second[0] == "Provider: stub"
    assert third[0] == "Provider: stub"
    assert first[-1] == expected_first
    assert second[-1] == expected_first
    assert third[-1] == expected_third
    assert first[-1] != third[-1]


def test_talk_does_not_accumulate_reminder_or_mood(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "next", "again", "quit"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: None)
    outputs: list[str] = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk(seed=7)

    replies = [out for out in outputs if "Mood:" in out]
    assert len(replies) == 3
    for reply in replies:
        assert reply.count("Reminder:") <= 1
        assert reply.count("Mood:") == 1


def test_talk_provider_timeout_message_and_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "quit"])

    def raise_timeout(_prompt: str, *, timeout: float = 8.0) -> str:
        del timeout
        raise ProviderTimeoutError("slow")

    client = LLMProviderClient(name="openai", generate=raise_timeout)
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: client)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs: list[str] = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk(provider="openai", seed=10)

    assert outputs[0] == "Provider: openai"
    assert any("retries exhausted" in out for out in outputs)
    assert any("Using local fallback replies" in out for out in outputs)


def test_talk_provider_quota_message(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "quit"])

    def raise_quota(_prompt: str, *, timeout: float = 8.0) -> str:
        del timeout
        raise ProviderQuotaExceededError("quota")

    client = LLMProviderClient(name="openai", generate=raise_quota)
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: client)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    outputs: list[str] = []
    monkeypatch.setattr("builtins.print", lambda msg: outputs.append(msg))

    talk(provider="openai", seed=11)

    assert any("quota is exceeded" in out for out in outputs)


def test_talk_logs_provider_events(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    inputs = iter(["hello", "quit"])
    events = []

    client = LLMProviderClient(
        name="openai", generate=lambda _prompt, timeout=8.0: "hello"
    )
    monkeypatch.setattr("singular.organisms.talk.load_llm_client", lambda _name: client)
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))
    monkeypatch.setattr("builtins.print", lambda _msg: None)
    monkeypatch.setattr(
        "singular.organisms.talk.log_provider_event",
        lambda **kwargs: events.append(kwargs),
    )

    talk(provider="openai")

    assert events
    assert events[0]["provider"] == "openai"
    assert events[0]["fallback"] is False
    assert events[0]["error_category"] is None
