import pytest

from life.sandbox import run, SandboxError


def test_basic_execution():
    assert run('result = max(1, 2)') == 2


def test_forbidden_import():
    with pytest.raises(SandboxError):
        run('import os')


def test_forbidden_name():
    with pytest.raises(SandboxError):
        run('open("foo")')


def test_timeout():
    with pytest.raises(TimeoutError):
        run('while True: pass', timeout=0.5)


def test_memory_limit():
    with pytest.raises(MemoryError):
        run("'x' * (300 * 1024 * 1024)")
