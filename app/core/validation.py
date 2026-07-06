from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData, ValidationIssue, ValidationReport


def validate_curve(curve: CurveData) -> ValidationReport:
    q = curve.q
    intensity = curve.intensity
    issues: list[ValidationIssue] = []

    q_nan = int(np.isnan(q).sum())
    if q_nan:
        issues.append(ValidationIssue("q_nan", "warning", "q contains NaN values.", q_nan))

    i_nan = int(np.isnan(intensity).sum())
    if i_nan:
        issues.append(ValidationIssue("intensity_nan", "warning", "I(q) contains NaN values.", i_nan))

    finite_q = q[np.isfinite(q)]
    if finite_q.size > 1 and not np.all(np.diff(finite_q) > 0):
        issues.append(ValidationIssue("q_not_monotonic", "warning", "q is not strictly increasing."))

    unique_q = np.unique(finite_q)
    duplicate_count = int(finite_q.size - unique_q.size)
    if duplicate_count:
        issues.append(ValidationIssue("q_duplicate", "warning", "q contains duplicate values.", duplicate_count))

    negative_i = int(np.sum(intensity < 0))
    if negative_i:
        issues.append(ValidationIssue("intensity_negative", "warning", "I(q) contains negative values.", negative_i))

    zero_i = int(np.sum(intensity == 0))
    if zero_i:
        issues.append(ValidationIssue("intensity_zero", "warning", "I(q) contains zero values.", zero_i))

    if curve.error is not None:
        error = curve.error
        error_nan = int(np.isnan(error).sum())
        if error_nan:
            issues.append(ValidationIssue("error_nan", "warning", "error contains NaN values.", error_nan))
        error_negative = int(np.sum(error < 0))
        if error_negative:
            issues.append(ValidationIssue("error_negative", "warning", "error contains negative values.", error_negative))
        error_zero = int(np.sum(error == 0))
        if error_zero:
            issues.append(ValidationIssue("error_zero", "warning", "error contains zero values.", error_zero))

    finite_i = intensity[np.isfinite(intensity)]
    i_min = float(np.min(finite_i)) if finite_i.size else float("nan")
    i_max = float(np.max(finite_i)) if finite_i.size else float("nan")
    dynamic_range = float(i_max / i_min) if np.isfinite(i_min) and i_min > 0 else float("inf")

    summary = {
        "q_min": float(np.min(finite_q)) if finite_q.size else float("nan"),
        "q_max": float(np.max(finite_q)) if finite_q.size else float("nan"),
        "I_min": i_min,
        "I_max": i_max,
        "data_points": int(q.size),
        "dynamic_range": dynamic_range,
    }
    return ValidationReport(curve_id=curve.curve_id, summary=summary, issues=issues)

