from __future__ import annotations

from typing import Callable

from singular.resource_manager import ResourceManager

from .vital import VitalState


def restore_survival_resources(
    *,
    state: VitalState | str,
    energy: float,
    resources: float,
    available_energy: float = 0.0,
    available_resources: float = 0.0,
    target: float = 1.0,
) -> tuple[float, float, dict[str, float]]:
    """Use only available simulation reserves to support pre-death recovery."""

    state = VitalState(state)
    if state not in {VitalState.AT_RISK, VitalState.CRITICAL, VitalState.TERMINAL}:
        return energy, resources, {"energy": 0.0, "resources": 0.0}
    energy_gain = min(max(target - energy, 0.0), max(available_energy, 0.0))
    resource_gain = min(max(target - resources, 0.0), max(available_resources, 0.0))
    return (
        energy + energy_gain,
        resources + resource_gain,
        {"energy": energy_gain, "resources": resource_gain},
    )


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
