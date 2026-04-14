from singular.organisms.birth import _resolve_starter_skills


def test_resolve_starter_skills_falls_back_to_minimal_profile() -> None:
    profiles = {
        "minimal": ["addition", "subtraction", "multiplication"],
        "assistant": ["summary"],
    }

    resolved = _resolve_starter_skills("does-not-exist", ["summary"], profiles=profiles)

    assert resolved == ["addition", "subtraction", "multiplication", "summary"]
