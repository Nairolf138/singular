from pathlib import Path

from singular.psyche import Psyche, Mood
from singular.resource_manager import ResourceManager


def test_feel_updates_traits_and_last_mood() -> None:
    psyche = Psyche()
    mood = psyche.feel(Mood.PROUD)
    assert mood is Mood.PROUD
    assert psyche.last_mood is Mood.PROUD
    assert psyche.curiosity > 0.5
    assert psyche.patience > 0.5
    assert psyche.playfulness > 0.5
    assert psyche.optimism > 0.5
    assert psyche.resilience > 0.5

    # Test clamping at upper bound
    for _ in range(20):
        psyche.feel(Mood.PROUD)
    assert 0.0 <= psyche.curiosity <= 1.0
    assert 0.0 <= psyche.patience <= 1.0
    assert 0.0 <= psyche.playfulness <= 1.0
    assert 0.0 <= psyche.optimism <= 1.0
    assert 0.0 <= psyche.resilience <= 1.0


def test_policies_and_lower_clamp() -> None:
    psyche = Psyche(
        curiosity=0.05,
        patience=0.1,
        playfulness=0.05,
        optimism=0.05,
        resilience=0.05,
    )
    psyche.feel(Mood.FRUSTRATED)
    assert psyche.curiosity >= 0.0
    assert psyche.patience >= 0.0
    assert psyche.playfulness >= 0.0
    assert psyche.optimism >= 0.0
    assert psyche.resilience >= 0.0
    assert psyche.interaction_policy() == "cautious"
    assert psyche.mutation_policy() == "analyze"


def test_trait_based_policy_overrides() -> None:
    high_traits = Psyche(optimism=0.9, resilience=0.9)
    assert high_traits.interaction_policy() == "engaging"
    assert high_traits.mutation_policy() == "exploit"


def test_state_persistence(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "psyche.json"
    psyche = Psyche(
        curiosity=0.2,
        patience=0.3,
        playfulness=0.4,
        optimism=0.6,
        resilience=0.7,
    )
    psyche.feel(Mood.PROUD)
    psyche.save_state(path)
    assert path.exists()

    loaded = Psyche.load_state(path)
    assert loaded.curiosity == psyche.curiosity
    assert loaded.patience == psyche.patience
    assert loaded.playfulness == psyche.playfulness
    assert loaded.optimism == psyche.optimism
    assert loaded.resilience == psyche.resilience
    assert loaded.last_mood == psyche.last_mood


def test_resource_manager_influences_mood(tmp_path: Path) -> None:
    psyche = Psyche()

    rm = ResourceManager(energy=5.0, path=tmp_path / "res.json")
    mood = psyche.update_from_resource_manager(rm)
    assert mood is Mood.FATIGUE
    assert psyche.last_mood is Mood.FATIGUE

    rm = ResourceManager(food=5.0, path=tmp_path / "res2.json")
    mood = psyche.update_from_resource_manager(rm)
    assert mood is Mood.ANGER
    assert psyche.last_mood is Mood.ANGER

    rm = ResourceManager(warmth=5.0, path=tmp_path / "res3.json")
    mood = psyche.update_from_resource_manager(rm)
    assert mood is Mood.LONELY
    assert psyche.last_mood is Mood.LONELY
