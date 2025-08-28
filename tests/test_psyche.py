from pathlib import Path

from singular.psyche import Psyche


def test_feel_updates_traits_and_last_mood() -> None:
    psyche = Psyche()
    mood = psyche.feel("proud")
    assert mood == "proud"
    assert psyche.last_mood == "proud"
    assert psyche.curiosity > 0.5
    assert psyche.patience > 0.5
    assert psyche.playfulness > 0.5

    # Test clamping at upper bound
    for _ in range(20):
        psyche.feel("proud")
    assert 0.0 <= psyche.curiosity <= 1.0
    assert 0.0 <= psyche.patience <= 1.0
    assert 0.0 <= psyche.playfulness <= 1.0


def test_policies_and_lower_clamp() -> None:
    psyche = Psyche(curiosity=0.05, patience=0.1, playfulness=0.05)
    psyche.feel("frustrated")
    assert psyche.curiosity >= 0.0
    assert psyche.patience >= 0.0
    assert psyche.playfulness >= 0.0
    assert psyche.interaction_policy() == "retry"
    assert psyche.mutation_policy() == "explore"


def test_state_persistence(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "psyche.json"
    psyche = Psyche(curiosity=0.2, patience=0.3, playfulness=0.4)
    psyche.feel("proud")
    psyche.save_state(path)
    assert path.exists()

    loaded = Psyche.load_state(path)
    assert loaded.curiosity == psyche.curiosity
    assert loaded.patience == psyche.patience
    assert loaded.playfulness == psyche.playfulness
    assert loaded.last_mood == psyche.last_mood
