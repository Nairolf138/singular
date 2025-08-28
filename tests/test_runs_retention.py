import importlib


def test_log_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("SINGULAR_RUNS_KEEP", "2")
    import singular.runs.logger as logger
    importlib.reload(logger)
    for i in range(3):
        rl = logger.RunLogger(f"r{i}", root=tmp_path)
        rl.log("s", "op", "d", True, 1.0, 2.0, 0.1, 0.05)
        rl.close()
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 2
    assert not list(tmp_path.glob("r0-*.jsonl"))
    monkeypatch.delenv("SINGULAR_RUNS_KEEP", raising=False)
    importlib.reload(logger)
