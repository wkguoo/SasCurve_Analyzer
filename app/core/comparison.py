from __future__ import annotations

from uuid import uuid4

import numpy as np

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import ComparisonResult, CurveData


def _aligned_values(curve_a: CurveData, curve_b: CurveData, *, interpolate: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    warnings: list[str] = []
    q_a, a_intensity = sort_arrays_by_q(curve_a.q, curve_a.intensity)
    q_b, b_intensity = sort_arrays_by_q(curve_b.q, curve_b.intensity)
    if q_a.shape == q_b.shape and np.allclose(q_a, q_b):
        return q_a.copy(), a_intensity.copy(), b_intensity.copy(), warnings
    if not interpolate:
        raise ValueError("q grids differ; set interpolate=True to compare on a common q grid.")
    q_min = max(float(np.nanmin(q_a)), float(np.nanmin(q_b)))
    q_max = min(float(np.nanmax(q_a)), float(np.nanmax(q_b)))
    if q_min >= q_max:
        raise ValueError("Curves do not share an overlapping q range.")
    point_count = min(q_a.size, q_b.size)
    q_grid = np.linspace(q_min, q_max, point_count)
    warnings.append("q grids differed; both curves were linearly interpolated to a common q grid.")
    return q_grid, np.interp(q_grid, q_a, a_intensity), np.interp(q_grid, q_b, b_intensity), warnings


def compare_curves(curve_a: CurveData, curve_b: CurveData, comparison_type: str, *, interpolate: bool = True) -> ComparisonResult:
    q, a_values, b_values, warnings = _aligned_values(curve_a, curve_b, interpolate=interpolate)
    if comparison_type == "difference":
        values = b_values - a_values
    elif comparison_type == "ratio":
        valid = np.abs(a_values) > 1e-12
        if not np.all(valid):
            warnings.append("Excluded points where curve A intensity is zero or near zero for ratio.")
        q = q[valid]
        values = b_values[valid] / a_values[valid]
    elif comparison_type == "relative_difference":
        valid = np.abs(a_values) > 1e-12
        if not np.all(valid):
            warnings.append("Excluded points where curve A intensity is zero or near zero for relative difference.")
        q = q[valid]
        values = (b_values[valid] - a_values[valid]) / a_values[valid]
    else:
        raise ValueError(f"Unsupported comparison_type: {comparison_type}")

    return ComparisonResult(
        comparison_id=str(uuid4()),
        curve_a_id=curve_a.curve_id,
        curve_b_id=curve_b.curve_id,
        comparison_type=comparison_type,
        q=q,
        values=values,
        q_range=(float(q.min()), float(q.max())) if q.size else (float("nan"), float("nan")),
        warnings=warnings,
    )


def normalized_intensity(curve: CurveData, normalization_type: str, *, q_ref: float | None = None) -> tuple[np.ndarray, list[str]]:
    warnings = ["Normalization is for display or shape comparison only; original CurveData is not modified."]
    if normalization_type == "I/Imax":
        denom = float(np.nanmax(curve.intensity))
    elif normalization_type == "I/I(q_ref)":
        if q_ref is None:
            raise ValueError("q_ref is required for I/I(q_ref).")
        q_sorted, intensity_sorted = sort_arrays_by_q(curve.q, curve.intensity)
        denom = float(np.interp(q_ref, q_sorted, intensity_sorted))
    elif normalization_type == "I/area":
        q_sorted, intensity_sorted = sort_arrays_by_q(curve.q, curve.intensity)
        denom = float(np.trapezoid(intensity_sorted, q_sorted))
    elif normalization_type == "I/Q_measured":
        q_sorted, intensity_sorted = sort_arrays_by_q(curve.q, curve.intensity)
        denom = float(np.trapezoid(q_sorted**2 * intensity_sorted, q_sorted))
    else:
        raise ValueError(f"Unsupported normalization_type: {normalization_type}")
    if abs(denom) <= 1e-12:
        warnings.append("Normalization denominator is zero or near zero.")
        return np.full_like(curve.intensity, np.nan, dtype=float), warnings
    return curve.intensity / denom, warnings

