from singular.life.profiling import LifeLoopProfiler, cache_candidates_from_phases


def test_life_loop_profiler_records_required_phases_and_cache_candidates() -> None:
    profiler = LifeLoopProfiler()
    profiler.record_duration("mutation", 2.5)
    profiler.record_cache("sandbox_scoring", hit=False)
    profiler.record_cache("sandbox_scoring", hit=True)

    summary = profiler.summary()

    assert "mutation" in summary["phases"]
    assert "checkpoint_write" in summary["phases"]
    assert summary["phases"]["mutation"]["total_ms"] == 2.5
    assert summary["phases"]["sandbox_scoring"]["cache_hits"] == 1
    assert summary["cache_candidates"][0]["phase"] == "sandbox_scoring"
    assert "asynchrone" in summary["async_distribution_note"]


def test_cache_candidates_include_config_loading() -> None:
    candidates = cache_candidates_from_phases(
        {
            "config_loading": {"calls": 1, "cache_hits": 2, "cache_misses": 1},
            "sandbox_scoring": {"cache_hits": 0, "cache_misses": 0},
        }
    )

    assert any(candidate["phase"] == "config_loading" for candidate in candidates)
