"""Access to resources shipped with the :mod:`singular` package."""

from __future__ import annotations

from importlib.resources import files
from importlib.resources.abc import Traversable


def config_resource(*parts: str) -> Traversable:
    """Return a traversable for a bundled runtime configuration."""

    resource = files("singular.data").joinpath("configs")
    for part in parts:
        resource = resource.joinpath(part)
    return resource
