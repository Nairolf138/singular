from singular.environment.world_resources import CompetitorIntent, WorldResourcePool


def test_world_resource_pool_cooperation_shares_cost_and_grants_bonus() -> None:
    pool = WorldResourcePool(cpu_budget=10.0, mutation_slots=4.0, attention_score=5.0)

    resolution = pool.consume_for_action(
        life_id="alpha",
        cpu_cost=2.0,
        mutation_cost=1.0,
        attention_cost=1.0,
        cooperation_partners=["beta"],
    )

    assert resolution.granted is True
    assert resolution.cooperation_partners == ["beta"]
    assert resolution.relation_bonus > 0.0
    assert pool.cpu_budget < 10.0
    assert pool.mutation_slots < 4.0
    assert pool.attention_score < 5.0


def test_world_resource_pool_competition_records_contention_and_conflicts() -> None:
    pool = WorldResourcePool(cpu_budget=1.0, mutation_slots=0.5, attention_score=0.5)

    resolution = pool.consume_for_action(
        life_id="alpha",
        cpu_cost=2.0,
        mutation_cost=1.0,
        attention_cost=1.0,
        priority=1,
        bid=0.2,
        competitor_intents=[CompetitorIntent(life_id="beta", priority=2, bid=1.5)],
    )

    assert resolution.granted is False
    assert resolution.contention is True
    assert "alpha" in resolution.conflicts or "beta" in resolution.conflicts
    assert resolution.rivalry_penalty > 0.0
    assert pool.contention_log
