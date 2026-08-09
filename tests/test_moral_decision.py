from singular.morals import MoralDecisionEngine


def test_absolute_veto_for_rights_violation() -> None:
    decision = MoralDecisionEngine().evaluate(
        "publish_private_data",
        [
            {
                "description": "privacy breach",
                "harm": 0.7,
                "violates_rights": True,
                "values": ("privacy",),
            }
        ],
        [{"identifier": "user", "vulnerability": 0.5}],
        [{"value": "privacy", "absolute": True}],
        0.1,
    )

    assert decision.veto is True
    assert "droits" in (decision.veto_reason or "")


def test_conflict_between_two_values_is_made_explicit() -> None:
    decision = MoralDecisionEngine().evaluate(
        "tell_difficult_truth",
        [
            {
                "description": "supports autonomy",
                "benefit": 0.8,
                "values": ("autonomy",),
            },
            {"description": "causes distress", "harm": 0.3, "values": ("autonomy",)},
        ],
        identity_commitments=[{"value": "autonomy"}],
    )

    assert decision.conflicting_values == ("autonomy",)
    assert decision.veto is False


def test_high_uncertainty_reduces_score_and_requires_more_information() -> None:
    engine = MoralDecisionEngine()
    low = engine.evaluate("act", uncertainty=0.1)
    high = engine.evaluate("act", uncertainty=0.9)

    assert high.scores["overall"] < low.scores["overall"]
    assert any(
        "informations" in item for item in high.acceptable_alternative_conditions
    )


def test_selects_less_harmful_acceptable_alternative() -> None:
    selected, considered = MoralDecisionEngine().select_least_harmful(
        [
            {
                "action": "force",
                "consequences": [{"description": "injury", "harm": 0.8}],
            },
            {
                "action": "negotiate",
                "consequences": [{"description": "delay", "harm": 0.1, "benefit": 0.3}],
            },
        ]
    )

    assert len(considered) == 2
    assert selected is not None
    assert selected.action.action_type == "negotiate"
