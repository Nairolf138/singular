from pathlib import Path, PosixPath

import singular.root_config as root_config


def test_config_paths_use_native_paths_when_windows_is_simulated(
    monkeypatch, tmp_path
) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "workspace"
    monkeypatch.setattr(root_config.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(root_config.Path, "cwd", classmethod(lambda cls: cwd))
    monkeypatch.setattr(root_config.os, "name", "nt")

    registry_root = root_config.default_registry_root()
    global_path = root_config.global_config_path()
    project_path = root_config.project_config_path()

    assert registry_root == home / ".singular"
    assert global_path == home / ".singular" / "config.json"
    assert project_path == cwd / ".singular" / "config.json"
    assert isinstance(registry_root, PosixPath)
    assert isinstance(global_path, PosixPath)
    assert isinstance(project_path, PosixPath)


def test_decode_relative_windows_separators_against_config_directory(
    monkeypatch, tmp_path
) -> None:
    base_dir = tmp_path / ".singular"
    monkeypatch.setattr(root_config.os, "name", "nt")

    decoded = root_config._decode_registry_root(r"roots\\project", base_dir=base_dir)

    assert decoded == (base_dir / "roots" / "project").resolve()
    assert isinstance(decoded, PosixPath)


def test_decode_absolute_windows_path_on_simulated_windows(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(root_config.os, "name", "nt")

    decoded = root_config._decode_registry_root(
        r"C:\\registry\\singular", base_dir=tmp_path / ".singular"
    )

    assert decoded == PosixPath("C:/registry/singular")
    assert isinstance(decoded, PosixPath)


def test_decode_relative_path_is_based_on_global_or_project_config(tmp_path) -> None:
    global_dir = tmp_path / "home" / ".singular"
    project_dir = tmp_path / "workspace" / ".singular"

    assert (
        root_config._decode_registry_root("registry", base_dir=global_dir)
        == (global_dir / "registry").resolve()
    )
    assert (
        root_config._decode_registry_root("registry", base_dir=project_dir)
        == (project_dir / "registry").resolve()
    )


def test_decode_posix_absolute_path_is_not_rebased(tmp_path) -> None:
    absolute = tmp_path / "registry"

    assert root_config._decode_registry_root(
        str(absolute), base_dir=tmp_path / "config"
    ) == Path(absolute)


def test_diagnose_registry_root_reports_env_provenance(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SINGULAR_ROOT", str(tmp_path))

    diagnostic = root_config.diagnose_registry_root()

    assert diagnostic == {
        "root": tmp_path.resolve(),
        "source": "environment",
        "exists": True,
    }
