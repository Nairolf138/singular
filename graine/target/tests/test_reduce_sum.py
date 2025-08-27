import random

from graine.target.src.algorithms.reduce_sum import reduce_sum


# Unit tests

def test_unit_basic_sum():
    assert reduce_sum([1, 2, 3]) == 6


def test_unit_negative_numbers():
    assert reduce_sum([-1, -2, -3]) == -6


def test_unit_empty_iterable():
    assert reduce_sum([]) == 0


# Integration tests

def test_integration_with_generator():
    data = (i for i in range(5))
    assert reduce_sum(data) == 10


def test_integration_with_map():
    data = map(int, ["1", "2", "3"])
    assert reduce_sum(data) == 6


# Property-based tests using randomised examples (≥10 000 cases)

def test_property_equivalent_to_builtin_sum_random_cases_large():
    for _ in range(10000):
        length = random.randint(0, 20)
        xs = [random.randint(-1000, 1000) for _ in range(length)]
        assert reduce_sum(xs) == sum(xs)


# Metamorphic tests

def test_metamorphic_permutation_invariance_random():
    xs = [random.randint(-10, 10) for _ in range(20)]
    shuffled = xs[:]
    random.shuffle(shuffled)
    assert reduce_sum(xs) == reduce_sum(shuffled)


def test_metamorphic_add_constant_random():
    xs = [random.randint(-10, 10) for _ in range(20)]
    k = random.randint(-10, 10)
    shifted = [x + k for x in xs]
    assert reduce_sum(shifted) == reduce_sum(xs) + k * len(xs)
