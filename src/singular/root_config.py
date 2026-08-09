"""Persistent configuration helpers for registry root resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
from typing import Any


_CONFIG_DIRNAME = ".singular"
_CONFIG_FILENAME = "config.json"
_REGISTRY_ROOT_KEY = "registry_root"
_HOST_PATH_CLS = type(Path())


def _safe_path(raw: str) -> Path:
    """Build a path with the native class selected when this module loaded."""

    # pathlib selects Path's concrete class from os.name at call time.  Tests
    # and embedders may simulate a platform, but that policy change must not
    # cause construction of a path class unsupported by the actual host.
    normalized = str(raw).replace("\\", "/") if os.name == "nt" else str(raw)
    return _HOST_PATH_CLS(normalized)


def default_registry_root() -> Path:
    """Return the documented fallback registry root."""

    # Go through ``Path`` rather than the cached concrete path class so callers
    # can override the user home (notably embedders and isolated CLI tests).
    home = Path.home()
    return home / _CONFIG_DIRNAME


def global_config_path() -> Path:
    """Return the global config file path."""

    return default_registry_root() / _CONFIG_FILENAME


def project_config_path(cwd: Path | None = None) -> Path:
    """Return the project config file path rooted in cwd."""

    if cwd is not None:
        base = cwd
    else:
        base = Path.cwd()
    return base / _CONFIG_DIRNAME / _CONFIG_FILENAME


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_registry_root(raw: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    configured = _safe_path(raw).expanduser()
    # When ``os.name`` is simulated as ``nt`` on a POSIX host, ``_safe_path``
    # deliberately returns a host-native path.  Preserve the meaning of an
    # absolute Windows value even though PosixPath does not recognise its
    # drive/root syntax.
    is_absolute = configured.is_absolute() or PureWindowsPath(raw).is_absolute()
    if not is_absolute:
        configured = (base_dir / configured).resolve()
    return configured


def load_configured_registry_root(cwd: Path | None = None) -> Path | None:
    """Load a configured root from explicit project/global config."""

    project_path = project_config_path(cwd)
    project_payload = _load_json(project_path)
    project_root = _decode_registry_root(
        project_payload.get(_REGISTRY_ROOT_KEY),
        base_dir=project_path.parent,
    )
    if project_root is not None:
        return project_root

    global_path = global_config_path()
    global_payload = _load_json(global_path)
    return _decode_registry_root(
        global_payload.get(_REGISTRY_ROOT_KEY),
        base_dir=global_path.parent,
    )


def diagnose_registry_root(cwd: Path | None = None) -> dict[str, Any]:
    """Return the effective registry root and its non-secret provenance.

    This is deliberately a data-only helper so installers, the CLI and the web
    dashboard can present the exact same root-resolution decision.
    """

    env_root = os.environ.get("SINGULAR_ROOT")
    configured = load_configured_registry_root(cwd)
    if env_root:
        root, source = _safe_path(env_root).expanduser().resolve(), "environment"
    elif configured is not None:
        root, source = configured.resolve(), "configuration"
    else:
        root, source = default_registry_root().resolve(), "default"
    return {"root": root, "source": source, "exists": root.is_dir()}


def set_configured_registry_root(
    value: str, *, scope: str, cwd: Path | None = None
) -> tuple[Path, Path]:
    """Persist a configured root and return (config_path, resolved_root)."""

    if scope not in {"global", "project"}:
        raise ValueError("scope must be 'global' or 'project'")

    config_path = (
        global_config_path() if scope == "global" else project_config_path(cwd)
    )
    payload = _load_json(config_path)
    payload[_REGISTRY_ROOT_KEY] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    resolved = _decode_registry_root(value, base_dir=config_path.parent)
    if resolved is None:
        raise ValueError("configured registry root must be a non-empty path")
    return config_path, resolved
