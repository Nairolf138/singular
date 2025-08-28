import importlib


def test_singular_home_override(tmp_path, monkeypatch):
    monkeypatch.setenv("SINGULAR_HOME", str(tmp_path))
    import singular.memory as memory
    import singular.runs.logger as logger
    importlib.reload(memory)
    importlib.reload(logger)
    assert memory.get_mem_dir() == tmp_path / "mem"
    assert logger.RUNS_DIR == tmp_path / "runs"
    # cleanup: restore modules to default state
    monkeypatch.delenv("SINGULAR_HOME", raising=False)
    importlib.reload(memory)
    importlib.reload(logger)
