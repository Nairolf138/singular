import json
from pathlib import Path

from singular.runs import RunLogger
from singular.runs.explain import summarize_mutation


def test_log_creation(tmp_path: Path) -> None:
    logger = RunLogger("test", root=tmp_path)
    assert (tmp_path / "test" / ".active.lock").exists()
    summary = summarize_mutation(
        operator="op",
        impacted_file="skill.py",
        accepted=True,
        diff="--- a\n+++ b\n-result=1\n+result=0\n",
        ms_base=1.0,
        ms_new=0.8,
        score_base=0.2,
        score_new=0.1,
    )
    logger.log(
        "skill",
        "op",
        "diff",
        True,
        1.0,
        2.0,
        0.2,
        0.1,
        impacted_file="skill.py",
        decision_reason="accepted: score improved",
        human_summary=summary,
    )
    logger.close()
    files = list(tmp_path.glob("test-*.jsonl"))
    assert len(files) == 1
    with files[0].open(encoding="utf-8") as fh:
        line = json.loads(fh.readline())
    assert line["skill"] == "skill"
    assert line["improved"] is True
    assert line["human_summary"]
    assert "op=op" in line["human_summary"]
    assert line["impacted_file"] == "skill.py"

    events_path = tmp_path / "test" / "events.jsonl"
    assert events_path.exists()
    event = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    assert event["version"] == 1
    assert event["event_type"] == "mutation"
    assert event["payload"]["human_summary"] == summary
    assert not (tmp_path / "test" / ".active.lock").exists()


def test_resume_after_crash(tmp_path: Path) -> None:
    logger1 = RunLogger("run", root=tmp_path)
    logger1.log("a", "op", "diff", True, 1.0, 2.0, 0.1, 0.2)
    # Simulate crash without closing (file already flushed in log)
    logger1._file.close()

    logger2 = RunLogger("run", root=tmp_path)
    logger2.log("b", "op", "diff", False, 2.0, 3.0, 0.2, 0.3)
    logger2.close()

    files = list(tmp_path.glob("run-*.jsonl"))
    assert len(files) == 1
    with files[0].open(encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh]
    assert [r["skill"] for r in records] == ["a", "b"]


def test_log_test_coevolution(tmp_path: Path) -> None:
    logger = RunLogger("coevo", root=tmp_path)
    logger.log_test_coevolution(
        skill="foo",
        accepted=True,
        pool_size=4,
        added=2,
        removed=1,
        detection_rate=0.5,
        score_base=1.0,
        score_new=0.9,
        score_combined_base=1.0,
        score_combined_new=1.4,
    )
    logger.close()
    files = list(tmp_path.glob("coevo-*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").splitlines()[0])
    assert record["event"] == "test_coevolution"
    assert record["regression_detection_rate"] == 0.5
    assert record["tests_proposed"] == []
    assert record["tests_retained"] == []
    assert record["mutation_rejected_for_robustness"] is False


def test_log_consciousness_file(tmp_path: Path) -> None:
    logger = RunLogger("mind", root=tmp_path)
    logger.log_consciousness(
        perception_summary="temperature stable",
        evaluated_hypotheses=[{"action": "flip", "score": 0.2}],
        final_choice="flip",
        justification="best weighted score",
        objective="coherence",
        mood="focused",
        energy=77.0,
        success=True,
    )
    logger.close()

    consciousness_path = tmp_path / "mind" / "consciousness.jsonl"
    assert consciousness_path.exists()
    payload = json.loads(consciousness_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["event"] == "consciousness"
    assert payload["objective"] == "coherence"
    assert payload["success"] is True


def test_human_summary_quality_minimum() -> None:
    summary = summarize_mutation(
        operator="arith",
        impacted_file="foo.py",
        accepted=False,
        diff="--- a\n+++ b\n-result=1\n+result=2\n",
        ms_base=1.0,
        ms_new=1.4,
        score_base=0.1,
        score_new=0.3,
    )
    assert "op=arith" in summary
    assert "fichier=foo.py" in summary
    assert "rejetée" in summary
    assert "score" in summary
    assert "perf" in summary


def test_run_logger_aggregates_skill_reputation_from_usage_metrics(tmp_path: Path) -> None:
    logger = RunLogger("telemetry", root=tmp_path, reputation_update_every=1)
    logger.log(
        "skill_x",
        "op_a",
        "diff",
        True,
        2.0,
        3.0,
        0.4,
        0.2,
        usage_metrics={
            "success": True,
            "latency_ms": 3.0,
            "resource_cost": 5.0,
            "perceived_quality": 0.9,
            "user_satisfaction": 0.8,
        },
    )
    logger.log(
        "skill_x",
        "op_b",
        "diff",
        False,
        2.0,
        6.0,
        0.2,
        0.5,
        usage_metrics={
            "success": False,
            "latency_ms": 6.0,
            "resource_cost": 8.0,
            "perceived_quality": 0.2,
            "user_satisfaction": 0.1,
        },
    )
    logger.close()

    reputation_path = tmp_path / "telemetry" / "skill_reputation.json"
    payload = json.loads(reputation_path.read_text(encoding="utf-8"))
    stats = payload["skills"]["skill_x"]
    assert stats["use_count"] == 2
    assert 0.0 <= stats["success_rate"] <= 1.0
    assert stats["mean_cost"] > 0.0
    assert stats["recent_failures"] >= 1
