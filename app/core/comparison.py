from __future__ import annotations

from uuid import uuid4

import numpy as np

from app.core.data_model import ComparisonResult, CurveData


def _aligned_values(curve_a: CurveData, curve_b: CurveData, *, interpolate: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    warnings: list[str] = []
    if curve_a.q.shape == curve_b.q.shape and np.allclose(curve_a.q, curve_b.q):
        return curve_a.q.copy(), curve_a.intensity.copy(), curve_b.intensity.copy(), warnings
    if not interpolate:
        raise ValueError("q grids differ; set interpolate=True to compare on a common q grid.")
    q_min = max(float(np.nanmin(curve_a.q)), float(np.nanmin(curve_b.q)))
    q_max = min(float(np.nanmax(curve_a.q)), float(np.nanmax(curve_b.q)))
    if q_min >= q_max:
        raise ValueError("Curves do not share an overlapping q range.")
    point_count = min(curve_a.q.size, curve_b.q.size)
    q_grid = np.linspace(q_min, q_max, point_count)
    warnings.append("q grids differed; both curves were linearly interpolated to a common q grid.")
    return q_grid, np.interp(q_grid, curve_a.q, curve_a.intensity), np.interp(q_grid, curve_b.q, curve_b.intensity), warnings


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
        denom = float(np.interp(q_ref, curve.q, curve.intensity))
    elif normalization_type == "I/area":
        denom = float(np.trapezoid(curve.intensity, curve.q))
    elif normalization_type == "I/Q_measured":
        denom = float(np.trapezoid(curve.q**2 * curve.intensity, curve.q))
    else:
        raise ValueError(f"Unsupported normalization_type: {normalization_type}")
    if abs(denom) <= 1e-12:
        warnings.append("Normalization denominator is zero or near zero.")
        return np.full_like(curve.intensity, np.nan, dtype=float), warnings
    return curve.intensity / denom, warnings

