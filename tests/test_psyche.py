from pathlib import Path

from singular.psyche import Psyche, Mood
from singular.resource_manager import ResourceManager
from singular.motivation import GoalPolicy, Objective


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


def test_objective_policy_persistence_and_schema(tmp_path: Path) -> None:
    path = tmp_path / "mem" / "psyche.json"
    psyche = Psyche(
        objectives={
            "survie": Objective(
                "survie",
                weight=0.7,
                parent=None,
                horizon_ticks=4,
                policy=GoalPolicy(besoin=0.9, priorite=0.8, urgence=1.0, alignement_valeurs=0.7),
            )
        }
    )
    psyche.feel(Mood.PROUD)
    psyche.save_state(path)

    loaded = Psyche.load_state(path)
    assert loaded.schema_version >= 2
    assert loaded.mood_history
    assert loaded.objectives["survie"].horizon_ticks == 4
    assert loaded.objectives["survie"].policy.urgence == 1.0


def test_weighted_axes_and_operator_bias() -> None:
    psyche = Psyche(
        objectives={
            "root": Objective(
                "root",
                weight=1.0,
                policy=GoalPolicy(besoin=0.6, priorite=0.9, urgence=0.2, alignement_valeurs=0.9),
            ),
            "urgent": Objective(
                "urgent",
                weight=0.5,
                parent="root",
                horizon_ticks=3,
                policy=GoalPolicy(besoin=0.9, priorite=0.5, urgence=1.0, alignement_valeurs=0.4),
            ),
        }
    )
    axes = psyche.weighted_objective_axes()
    assert set(axes) == {"long_term", "sandbox", "resource"}
    assert abs(sum(axes.values()) - 1.0) < 1e-6
    biases = psyche.operator_bias(["op_a", "op_b", "op_c"])
    assert set(biases) == {"op_a", "op_b", "op_c"}
