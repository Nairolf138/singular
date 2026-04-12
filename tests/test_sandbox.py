import pytest

from singular.life.sandbox import run, SandboxError


def test_basic_execution():
    assert run("result = max(1, 2)") == 2


def test_spawn_context_simple_execution():
    assert run("result = 1") == 1


def test_forbidden_import():
    with pytest.raises(SandboxError):
        run("import os")


def test_forbidden_name():
    with pytest.raises(SandboxError):
        run('open("foo")')


def test_timeout():
    with pytest.raises(TimeoutError):
        run("while True: pass", timeout=0.5)


def test_memory_limit():
    with pytest.raises(MemoryError):
        run("'x' * (300 * 1024 * 1024)")


def test_forbidden_network_access():
    with pytest.raises(SandboxError):
        run("import socket\nsocket.socket()")


def test_forbidden_subprocess_access():
    with pytest.raises(SandboxError):
        run("import subprocess\nsubprocess.run(['echo', 'hi'])")

def test_run_windows_cleanup_guard(monkeypatch, caplog):
    import singular.life.sandbox as sandbox_module

    class InlineProcess:
        def __init__(self, target, args):
            self._target = target
            self._args = args
            self._alive = False

        def start(self):
            self._alive = True
            self._target(*self._args)
            self._alive = False

        def join(self, _timeout=None):
            return None

        def is_alive(self):
            return self._alive

        def terminate(self):
            self._alive = False

    class InlineQueue:
        def __init__(self):
            self._items = []

        def put(self, value):
            self._items.append(value)

        def get(self):
            return self._items.pop(0)

        def empty(self):
            return not self._items

    class InlineContext:
        def Queue(self):
            return InlineQueue()

        def Process(self, target, args):
            return InlineProcess(target, args)

    monkeypatch.setattr(sandbox_module.multiprocessing, "get_context", lambda _name: InlineContext())

    real_chdir = sandbox_module.os.chdir
    chdir_calls = []

    def fake_chdir(path):
        chdir_calls.append(path)
        if len(chdir_calls) == 2:
            raise OSError("simulated windows cleanup lock")
        return real_chdir(path)

    monkeypatch.setattr(sandbox_module.os, "chdir", fake_chdir)

    caplog.set_level("WARNING", logger=sandbox_module.__name__)
    assert sandbox_module.run("result = 1") == 1
    assert len(chdir_calls) == 2
    assert "failed to restore cwd during sandbox cleanup" in caplog.text

