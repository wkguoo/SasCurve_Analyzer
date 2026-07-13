"""Process-local cancel checks for long numerical loops.

Batch orchestration can install a cancel predicate without putting callables on
``AutoBatchConfig`` (which must stay JSON/fingerprint safe).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_CancelPredicate = Callable[[], bool]
_cancel_requested: ContextVar[_CancelPredicate | None] = ContextVar(
    "sas_curve_analyzer_cancel_requested",
    default=None,
)


def cancellation_requested() -> bool:
    """Return True when the active batch/run has requested a safe stop."""

    predicate = _cancel_requested.get()
    if predicate is None:
        return False
    try:
        return bool(predicate())
    except Exception:
        return False


@contextmanager
def cancel_scope(predicate: _CancelPredicate | None) -> Iterator[None]:
    """Install ``predicate`` for the duration of a nested block."""

    token = _cancel_requested.set(predicate)
    try:
        yield
    finally:
        _cancel_requested.reset(token)


__all__ = ["cancel_scope", "cancellation_requested"]
