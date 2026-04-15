"""Persistent configuration helpers for registry root resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path, PosixPath
from typing import Any


_CONFIG_DIRNAME = ".singular"
_CONFIG_FILENAME = "config.json"
_REGISTRY_ROOT_KEY = "registry_root"


def _safe_path(raw: str) -> Path:
    try:
        return Path(raw)
    except NotImplementedError:
        # Handles tests that monkeypatch os.name to "nt" on non-Windows hosts.
        return PosixPath(str(raw).replace("\\", "/"))


def default_registry_root() -> Path:
    """Return the documented fallback registry root."""

    try:
        home = Path.home()
    except NotImplementedError:
        home = _safe_path(os.path.expanduser("~"))
    return home / _CONFIG_DIRNAME


def global_config_path() -> Path:
    """Return the global config file path."""

    root = default_registry_root()
    try:
        return root / _CONFIG_FILENAME
    except NotImplementedError:
        return _safe_path(f"{root}/{_CONFIG_FILENAME}")


def project_config_path(cwd: Path | None = None) -> Path:
    """Return the project config file path rooted in cwd."""

    if cwd is not None:
        base = cwd
    else:
        try:
            base = Path.cwd()
        except NotImplementedError:
            base = _safe_path(os.getcwd())
    try:
        return base / _CONFIG_DIRNAME / _CONFIG_FILENAME
    except NotImplementedError:
        return _safe_path(f"{base}/{_CONFIG_DIRNAME}/{_CONFIG_FILENAME}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _decode_registry_root(raw: Any, *, base_dir: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    configured = Path(raw).expanduser()
    if not configured.is_absolute():
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


def set_configured_registry_root(
    value: str, *, scope: str, cwd: Path | None = None
) -> tuple[Path, Path]:
    """Persist a configured root and return (config_path, resolved_root)."""

    if scope not in {"global", "project"}:
        raise ValueError("scope must be 'global' or 'project'")

    config_path = global_config_path() if scope == "global" else project_config_path(cwd)
    payload = _load_json(config_path)
    payload[_REGISTRY_ROOT_KEY] = value
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    resolved = _decode_registry_root(value, base_dir=config_path.parent)
    if resolved is None:
        raise ValueError("configured registry root must be a non-empty path")
    return config_path, resolved
