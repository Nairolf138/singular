import math
from life.score import score


def test_score_single_run_variance_zero():
    value, var = score("result = 1", runs=1)
    assert isinstance(value, float)
    assert var == 0.0


def test_complexity_penalty_increases_score():
    simple = "result = 1"
    complex_code = "result = 0\nfor i in range(1000):\n    result += i\n"
    simple_score, _ = score(simple, runs=1, alpha=100.0)
    complex_score, _ = score(complex_code, runs=1, alpha=100.0)
    assert complex_score > simple_score
