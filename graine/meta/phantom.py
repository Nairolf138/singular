from __future__ import annotations

from typing import Iterable, Dict

from .dsl import MetaSpec


def replay(history: Iterable[Dict[str, object]]) -> bool:
    """Replay a sequence of historical meta specifications.

    Each historical entry is validated using :func:`MetaSpec.validate`. If any
    entry fails validation, a ``MetaValidationError`` propagates to the caller.
    Returns ``True`` when all entries pass validation.
    """

    for entry in history:
        spec = MetaSpec.from_dict(entry)
        spec.validate()
    return True
