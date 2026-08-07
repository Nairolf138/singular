from __future__ import annotations

import json
from pathlib import Path

from singular.identity.core import IdentityCoreService
from singular.identity.self_model import SCHEMA_VERSION, SelfModelStore
from singular.psyche import Psyche


def test_legacy_migration_separates_facts_and_preserves_evidence(tmp_path: Path) -> None:
    path = tmp_path / "self_model.json"
    path.write_text(json.dumps({"traits": {"patient": .8}, "preferences": {},
                                "constraints": {}, "updated_at": "2020-01-01T00:00:00+00:00"}))
    store = SelfModelStore(path)
    migrated = store.apply_facts([{"kind": "user_fact", "value": "born in Paris",
                                   "source": "conversation:42", "confidence": .9,
                                   "observed_at": "2024-01-01T00:00:00+00:00"}])

    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["stable_id"]
    assert "born in Paris" not in migrated["traits"]
    fact = migrated["autobiographical_facts"]["born in Paris"]
    assert (fact["source"], fact["confidence"], fact["observed_at"], fact["last_confirmed_at"]) == (
        "conversation:42", .9, "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00")
    assert SelfModelStore(path).read()["stable_id"] == migrated["stable_id"]


def test_restart_and_consolidation_keep_durable_identity(tmp_path: Path) -> None:
    mem = tmp_path / "life" / "mem"
    mem.mkdir(parents=True)
    (mem / "biography.json").write_text(json.dumps({
        "identity": {"id": "stable-1", "name": "Ariane"},
        "birth_certificate": {"event_type": "birth_certificate", "issued_at": "2024-01-01"},
        "self_summaries": [{"text": "Née pour apprendre."}],
    }))
    psyche = Psyche(identity_commitments={"values": ["truth"], "red_lines": ["harm"]},
                    identity_wounds=.7)
    service = IdentityCoreService(tmp_path / "life")
    first = service.synchronize(psyche)
    first["commitments"] = ["keep promises"]
    service.store.write(first)

    # Several sessions and evidence compactions must not compact invariants.
    for _ in range(3):
        restarted = IdentityCoreService(tmp_path / "life")
        restarted.store.compact(1)
        current = restarted.synchronize(Psyche())

    assert current["name"] == "Ariane"
    assert current["biographical_summary"] == "Née pour apprendre."
    assert current["commitments"] == ["keep promises"]
    assert current["identity_wounds"] == [{"kind": "legacy_psyche_wound", "severity": .7}]
    assert restarted.coherence_invariants().long_term_commitments == ("keep promises",)
