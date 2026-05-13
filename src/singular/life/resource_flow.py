from __future__ import annotations

from typing import Callable

from singular.resource_manager import ResourceManager


def manage_resources(
    resource_manager: ResourceManager,
    cpu_seconds: float,
    test_runner: Callable[[], int] | None = None,
) -> list[str]:
    """Run the resource phase and return current resource manager moods."""

    resource_manager.consume_energy(cpu_seconds)
    if test_runner:
        try:
            passed = test_runner()
        except Exception:
            passed = 0
        resource_manager.add_food(passed)
    return resource_manager.mood()
