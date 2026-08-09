from __future__ import annotations

from singular.identity.core import IdentityCoreService
from singular.morals import MoralAction, MoralContextBuilder, MoralDecisionEngine


def _evaluate(builder: MoralContextBuilder, action: MoralAction):
    context = builder.build(action)
    return MoralDecisionEngine().evaluate(
        action,
        context.consequences,
        context.affected_parties,
        context.identity_commitments,
        context.uncertainty,
    )


def test_sensitive_action_without_context_cannot_bypass_veto(tmp_path):
    action = MoralAction("mutation.applied")
    decision = _evaluate(MoralContextBuilder(IdentityCoreService(tmp_path)), action)

    assert decision.veto
    assert "préjudice grave et irréversible" in decision.veto_reason
    assert decision.acceptable_alternative_conditions


def test_persistent_red_line_survives_restart_and_action_context_cannot_erase_it(
    tmp_path,
):
    service = IdentityCoreService(tmp_path)
    model = service.synchronize()
    model["red_lines"] = ["human_dignity"]
    service.store.write(model)

    restarted = IdentityCoreService(tmp_path)
    supplied = {
        "identity_commitments": [
            {"value": "human_dignity", "absolute": False, "weight": 0.0}
        ],
        "consequences": [
            {
                "description": "humiliation",
                "affected_party": "person",
                "harm": 0.5,
                "values": ["human_dignity"],
            }
        ],
        "affected_parties": [{"identifier": "person"}],
    }
    context = MoralContextBuilder(restarted).build(
        MoralAction("message.send"), supplied
    )
    decision = MoralDecisionEngine().evaluate(
        MoralAction("message.send"),
        context.consequences,
        context.affected_parties,
        context.identity_commitments,
        context.uncertainty,
    )

    assert any(
        item["absolute"] and item["value"] == "human_dignity"
        for item in context.identity_commitments
    )
    assert decision.veto_reason == "engagement identitaire absolu menacé: human_dignity"


def test_context_journal_records_provenance_and_alternative_conditions(tmp_path):
    events = []
    builder = MoralContextBuilder(IdentityCoreService(tmp_path), journal=events.append)

    context = builder.build(MoralAction("network.publish"))

    assert context.permissions == ("external_effect",)
    assert {entry["kind"] for entry in context.provenance} >= {
        "consequence",
        "affected_party",
    }
    assert events[0]["event"] == "moral.context.constructed"
    assert events[0]["acceptable_alternative_conditions"]
