from graine.target.src.evaluate import benchmark


def _noop(xs):
    for _ in xs:
        pass


def test_benchmark_statistics_keys():
    res = benchmark(_noop, range(3), runs=5, warmups=1, bootstrap_samples=10, cpu=None)
    assert "median" in res and "iqr" in res and "ic95" in res
    low, high = res["ic95"]
    assert low <= res["median"] <= high


class _Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, xs):
        self.calls += 1


def test_benchmark_honours_warmups():
    counter = _Counter()
    benchmark(counter, range(1), runs=3, warmups=2, bootstrap_samples=10, cpu=None)
    assert counter.calls == 5
