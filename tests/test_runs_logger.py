import json
from pathlib import Path

from singular.runs import RunLogger


def test_log_creation(tmp_path: Path) -> None:
    logger = RunLogger("test", root=tmp_path)
    logger.log("skill", "op", "diff", True, 1.0, 2.0, 0.2, 0.1)
    logger.close()
    files = list(tmp_path.glob("test-*.jsonl"))
    assert len(files) == 1
    with files[0].open(encoding="utf-8") as fh:
        line = json.loads(fh.readline())
    assert line["skill"] == "skill"
    assert line["improved"] is True


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
