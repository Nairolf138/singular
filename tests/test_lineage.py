from __future__ import annotations

from singular.life.lineage import (
    children_of,
    create_lineage_record,
    lineage_path,
    load_lineage,
    parents_of,
    record_child,
    register_lineage,
    save_lineage,
)


def test_register_lineage_links_parents_children_generation_and_scores() -> None:
    registry = {}
    register_lineage(registry, "root", score=0.7, mutation_source="seed")
    child = register_lineage(
        registry,
        "child",
        parents=["root"],
        mutation_source="eq_rewrite_reduce_sum",
        score=0.9,
        metadata={"accepted": True},
    )

    assert child.parents == ("root",)
    assert child.generation == 1
    assert child.mutation_source == "eq_rewrite_reduce_sum"
    assert child.score == 0.9
    assert registry["root"].children == ("child",)
    assert children_of(registry, "root") == ("child",)
    assert parents_of(registry, "child") == ("root",)


def test_lineage_path_and_persistence_round_trip(tmp_path) -> None:
    registry = {}
    register_lineage(registry, "root")
    record_child(registry, "root", "child", mutation_source="mutation_a", score=1.0)
    record_child(
        registry, "child", "grandchild", mutation_source="mutation_b", score=1.2
    )

    assert lineage_path(registry, "grandchild") == ("root", "child", "grandchild")

    path = tmp_path / "lineage.json"
    save_lineage(path, registry)
    loaded = load_lineage(path)

    assert loaded["grandchild"].generation == 2
    assert loaded["grandchild"].mutation_source == "mutation_b"
    assert loaded["grandchild"].score == 1.2
    assert loaded["child"].children == ("grandchild",)


def test_create_lineage_record_rejects_empty_ids() -> None:
    try:
        create_lineage_record("   ")
    except ValueError as exc:
        assert "organism_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
