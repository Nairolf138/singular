import random

from singular.life.test_coevolution import (
    LivingTestPool,
    TestCandidate,
    propose_test_candidates,
)


def test_regression_detection_rate():
    pool = LivingTestPool(tests=[TestCandidate("result == 1")], ttl={"result == 1": 3})
    rate = pool.regression_detection_rate("result = 1", "result = 2")
    assert rate == 1.0


def test_pool_evolve_removes_dead_tests():
    pool = LivingTestPool(
        tests=[TestCandidate("result == 1")],
        ttl={"result == 1": 1},
        initial_ttl=1,
    )
    delta = pool.evolve("result = 2", [], random.Random(0))
    assert delta["removed"] == 1
    assert not pool.tests


def test_candidate_proposals_are_seed_reproducible():
    c1 = propose_test_candidates("result = 3", random.Random(7), limit=3)
    c2 = propose_test_candidates("result = 3", random.Random(7), limit=3)
    assert [c.expr for c in c1] == [c.expr for c in c2]
