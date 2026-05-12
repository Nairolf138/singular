from singular.life.loop import score_code_with_error
from singular.organisms.birth import _SKILL_TEMPLATES, _resolve_starter_skills


def test_resolve_starter_skills_falls_back_to_minimal_profile() -> None:
    profiles = {
        "minimal": ["addition", "subtraction", "multiplication"],
        "assistant": ["summary"],
    }

    resolved = _resolve_starter_skills("does-not-exist", ["summary"], profiles=profiles)

    assert resolved == ["addition", "subtraction", "multiplication", "summary"]


def test_starter_skill_templates_satisfy_sandbox_scoring_contract() -> None:
    for skill_name, source in _SKILL_TEMPLATES.items():
        score = score_code_with_error(source)

        assert (
            score.ok is True
        ), f"{skill_name}: {score.error_type} {score.error_message}"
