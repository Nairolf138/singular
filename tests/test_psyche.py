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
