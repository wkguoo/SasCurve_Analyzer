from __future__ import annotations

from app.core.data_model import CurveData


def compute_correlation_function(curve: CurveData, q_range: tuple[float, float], options: dict | None = None):
    raise NotImplementedError(
        "Correlation function analysis is reserved for a later validated implementation. "
        "It usually requires low-q and high-q extrapolation and structure-specific assumptions."
    )

