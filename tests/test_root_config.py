from pathlib import Path, PosixPath

import singular.root_config as root_config


def test_decode_relative_windows_separators_against_config_directory(
    monkeypatch, tmp_path
) -> None:
    base_dir = tmp_path / ".singular"
    monkeypatch.setattr(root_config.os, "name", "nt")

    decoded = root_config._decode_registry_root(
        r"roots\\project", base_dir=base_dir
    )

    assert decoded == (base_dir / "roots" / "project").resolve()
    assert isinstance(decoded, PosixPath)


def test_decode_absolute_windows_path_on_simulated_windows(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(root_config.os, "name", "nt")

    decoded = root_config._decode_registry_root(
        r"C:\\registry\\singular", base_dir=tmp_path / ".singular"
    )

    assert decoded == PosixPath("C:/registry/singular")
    assert isinstance(decoded, PosixPath)


def test_decode_relative_path_is_based_on_global_or_project_config(tmp_path) -> None:
    global_dir = tmp_path / "home" / ".singular"
    project_dir = tmp_path / "workspace" / ".singular"

    assert root_config._decode_registry_root("registry", base_dir=global_dir) == (
        global_dir / "registry"
    ).resolve()
    assert root_config._decode_registry_root("registry", base_dir=project_dir) == (
        project_dir / "registry"
    ).resolve()


def test_decode_posix_absolute_path_is_not_rebased(tmp_path) -> None:
    absolute = tmp_path / "registry"

    assert root_config._decode_registry_root(
        str(absolute), base_dir=tmp_path / "config"
    ) == Path(absolute)
