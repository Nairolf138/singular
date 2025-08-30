from __future__ import annotations

"""Perception utilities.

This module provides a :func:`capture_signals` function that gathers basic
sensory inputs.  It includes a few virtual sensors (temperature, a simple
cycle to indicate day or night, and ambient noise).  Optional connectors can
supply real-world data by reading from a file or querying a weather API.  Any
failures in these connectors are ignored so that perception always succeeds.
"""

from pathlib import Path
import os
import random
import time
from typing import Any, Dict


def _read_optional_file() -> Dict[str, Any]:
    """Read data from ``SINGULAR_SENSOR_FILE`` if available."""
    path = os.getenv("SINGULAR_SENSOR_FILE")
    if not path:
        return {}
    try:
        return {"file": Path(path).read_text(encoding="utf-8").strip()}
    except Exception:
        return {}


def _query_optional_weather_api() -> Dict[str, Any]:
    """Query ``SINGULAR_WEATHER_API`` for weather data if possible."""
    url = os.getenv("SINGULAR_WEATHER_API")
    if not url:
        return {}
    try:  # pragma: no cover - network failures are expected
        import requests

        timeout_str = os.getenv("SINGULAR_HTTP_TIMEOUT", "5")
        try:
            timeout = float(timeout_str)
        except ValueError:
            timeout = 5.0
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return {"weather": response.json()}
    except Exception:
        return {}


def capture_signals() -> Dict[str, Any]:
    """Collect sensory signals from virtual and optional real sources."""
    signals: Dict[str, Any] = {
        "temperature": random.uniform(-20.0, 40.0),
        "is_daytime": 6 <= time.localtime().tm_hour < 18,
        "noise": random.random(),
    }
    signals.update(_read_optional_file())
    signals.update(_query_optional_weather_api())
    return signals
