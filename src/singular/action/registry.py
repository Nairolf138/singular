"""Registry d'actions atomiques autorisées.

Ce module définit un registre strict des actions UI atomiques. Toute action
hors registre est explicitement refusée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


class UnknownActionError(ValueError):
    """Raised when an action is not part of the allowed registry."""


class ActionValidationError(ValueError):
    """Raised when action parameters are invalid."""


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Maximum number of executions in a sliding window."""

    max_calls: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """Policy and validation metadata for one atomic action."""

    name: str
    preconditions: tuple[str, ...]
    parameter_contract: Mapping[str, str]
    risks: tuple[str, ...]
    confirmation_required: bool
    rate_limit: RateLimit
    validator: Callable[[Mapping[str, Any]], dict[str, Any]]


_ALLOWED_MOUSE_BUTTONS = {"left", "middle", "right"}


def _validate_move_mouse(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"x", "y"}:
        raise ActionValidationError("move_mouse requires exactly: x, y")

    x = params["x"]
    y = params["y"]
    if not isinstance(x, int) or not isinstance(y, int):
        raise ActionValidationError("x and y must be integers")
    if x < 0 or y < 0:
        raise ActionValidationError("x and y must be >= 0")
    if x > 10000 or y > 10000:
        raise ActionValidationError("x and y must be <= 10000")

    return {"x": x, "y": y}


def _validate_click(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"button"}:
        raise ActionValidationError("click requires exactly: button")

    button = params["button"]
    if not isinstance(button, str):
        raise ActionValidationError("button must be a string")
    if button not in _ALLOWED_MOUSE_BUTTONS:
        allowed = ", ".join(sorted(_ALLOWED_MOUSE_BUTTONS))
        raise ActionValidationError(f"button must be one of: {allowed}")

    return {"button": button}


def _validate_type_text(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"text"}:
        raise ActionValidationError("type_text requires exactly: text")

    text = params["text"]
    if not isinstance(text, str):
        raise ActionValidationError("text must be a string")
    if text == "":
        raise ActionValidationError("text cannot be empty")
    if len(text) > 1000:
        raise ActionValidationError("text length must be <= 1000")

    return {"text": text}


def _validate_press_hotkey(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"keys"}:
        raise ActionValidationError("press_hotkey requires exactly: keys")

    keys = params["keys"]
    if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)):
        raise ActionValidationError("keys must be a non-empty list of strings")

    cleaned_keys: list[str] = []
    for key in keys:
        if not isinstance(key, str) or not key.strip():
            raise ActionValidationError("each key must be a non-empty string")
        cleaned_keys.append(key.strip().lower())

    if not cleaned_keys:
        raise ActionValidationError("keys must contain at least one key")
    if len(cleaned_keys) > 5:
        raise ActionValidationError("keys cannot contain more than 5 entries")

    return {"keys": cleaned_keys}


def _validate_open_url(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"url"}:
        raise ActionValidationError("open_url requires exactly: url")

    url = params["url"]
    if not isinstance(url, str):
        raise ActionValidationError("url must be a string")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ActionValidationError("url must start with http:// or https://")
    if len(url) > 2048:
        raise ActionValidationError("url length must be <= 2048")

    return {"url": url}


def _validate_focus_window(params: Mapping[str, Any]) -> dict[str, Any]:
    if set(params.keys()) != {"app"}:
        raise ActionValidationError("focus_window requires exactly: app")

    app = params["app"]
    if not isinstance(app, str):
        raise ActionValidationError("app must be a string")
    app = app.strip()
    if not app:
        raise ActionValidationError("app cannot be empty")
    if len(app) > 120:
        raise ActionValidationError("app length must be <= 120")

    return {"app": app}


ACTION_REGISTRY: dict[str, ActionSpec] = {
    "move_mouse": ActionSpec(
        name="move_mouse",
        preconditions=(
            "A desktop/UI session is active and accepts pointer input.",
            "Target coordinates are visible and within current screen bounds.",
        ),
        parameter_contract={
            "x": "int >= 0 and <= 10000",
            "y": "int >= 0 and <= 10000",
        },
        risks=(
            "May move focus to an unintended UI element.",
            "Can trigger hover side effects (tooltips, previews, auto-open).",
        ),
        confirmation_required=False,
        rate_limit=RateLimit(max_calls=120, window_seconds=60),
        validator=_validate_move_mouse,
    ),
    "click": ActionSpec(
        name="click",
        preconditions=(
            "Pointer is positioned on the intended element.",
            "Application window is focused and stable.",
        ),
        parameter_contract={"button": "one of: left|middle|right"},
        risks=(
            "Could trigger destructive buttons if targeting is wrong.",
            "Can submit forms or confirm dialogs unexpectedly.",
        ),
        confirmation_required=True,
        rate_limit=RateLimit(max_calls=60, window_seconds=60),
        validator=_validate_click,
    ),
    "type_text": ActionSpec(
        name="type_text",
        preconditions=(
            "A trusted text input field is focused.",
            "No secret should be exposed in unsafe contexts.",
        ),
        parameter_contract={"text": "non-empty string with max length 1000"},
        risks=(
            "May leak sensitive text into wrong window/chat.",
            "Could alter documents or commands irreversibly.",
        ),
        confirmation_required=True,
        rate_limit=RateLimit(max_calls=30, window_seconds=60),
        validator=_validate_type_text,
    ),
    "press_hotkey": ActionSpec(
        name="press_hotkey",
        preconditions=(
            "Active window is known and user-visible.",
            "Shortcut impact is understood for the focused app.",
        ),
        parameter_contract={"keys": "list[str], 1 to 5 keys"},
        risks=(
            "Can close apps, delete content, or trigger global shortcuts.",
            "May switch context away from the intended task.",
        ),
        confirmation_required=True,
        rate_limit=RateLimit(max_calls=20, window_seconds=60),
        validator=_validate_press_hotkey,
    ),
    "open_url": ActionSpec(
        name="open_url",
        preconditions=(
            "A browser-capable environment is available.",
            "URL is trusted and policy-compliant.",
        ),
        parameter_contract={"url": "string starting with http:// or https://"},
        risks=(
            "Could open phishing or malware pages.",
            "May exfiltrate metadata through external requests.",
        ),
        confirmation_required=True,
        rate_limit=RateLimit(max_calls=10, window_seconds=60),
        validator=_validate_open_url,
    ),
    "focus_window": ActionSpec(
        name="focus_window",
        preconditions=(
            "Target application is running.",
            "Switching focus does not interrupt critical user work.",
        ),
        parameter_contract={"app": "non-empty app name string (max 120 chars)"},
        risks=(
            "Can steal focus during sensitive user actions.",
            "Might target the wrong process when names are ambiguous.",
        ),
        confirmation_required=False,
        rate_limit=RateLimit(max_calls=30, window_seconds=60),
        validator=_validate_focus_window,
    ),
}


def get_action_spec(action: str) -> ActionSpec:
    """Return one allowed action specification, or refuse unknown actions."""
    spec = ACTION_REGISTRY.get(action)
    if spec is None:
        raise UnknownActionError(
            f"action '{action}' refused: not in registry ({', '.join(sorted(ACTION_REGISTRY))})"
        )
    return spec


def validate_action(action: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one action request and return normalized parameters.

    Any action name outside :data:`ACTION_REGISTRY` is rejected.
    """
    spec = get_action_spec(action)
    return spec.validator(params)


def allowed_actions() -> tuple[str, ...]:
    """List allowed action names."""
    return tuple(sorted(ACTION_REGISTRY))


__all__ = [
    "ACTION_REGISTRY",
    "ActionSpec",
    "ActionValidationError",
    "RateLimit",
    "UnknownActionError",
    "allowed_actions",
    "get_action_spec",
    "validate_action",
]
