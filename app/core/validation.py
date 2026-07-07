from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData, ValidationIssue, ValidationReport

SLIGHT_NEGATIVE_ABS_RATIO_THRESHOLD = 1e-3
SLIGHT_NEGATIVE_FRACTION_THRESHOLD = 0.05


def validate_curve(
    curve: CurveData,
    *,
    allow_slight_negative_intensity: bool = True,
    slight_negative_abs_ratio_threshold: float = SLIGHT_NEGATIVE_ABS_RATIO_THRESHOLD,
    slight_negative_fraction_threshold: float = SLIGHT_NEGATIVE_FRACTION_THRESHOLD,
) -> ValidationReport:
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

    finite_i = intensity[np.isfinite(intensity)]
    positive_i = finite_i[finite_i > 0]
    negative_i = int(np.sum(finite_i < 0))
    total_finite_i = int(finite_i.size)
    positive_median = float(np.nanmedian(positive_i)) if positive_i.size else float("nan")
    fallback_scale = float(np.nanmax(np.abs(finite_i))) if finite_i.size else float("nan")
    negative_fraction = float(negative_i / total_finite_i) if total_finite_i else 0.0
    i_min_for_ratio = float(np.nanmin(finite_i)) if finite_i.size else float("nan")
    scale = positive_median if np.isfinite(positive_median) and positive_median > 0 else fallback_scale
    negative_abs_ratio = float(abs(i_min_for_ratio) / scale) if negative_i and np.isfinite(scale) and scale > 0 else 0.0
    if negative_i:
        if (
            allow_slight_negative_intensity
            and negative_abs_ratio <= slight_negative_abs_ratio_threshold
            and negative_fraction <= slight_negative_fraction_threshold
        ):
            issues.append(
                ValidationIssue(
                    "intensity_slight_negative",
                    "info",
                    "I(q) contains slight negative values; this is allowed for calibrated/background-corrected data, but log plots and log-based analyses will exclude non-positive points.",
                    negative_i,
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    "intensity_negative",
                    "warning",
                    "I(q) contains significant negative values; linear plots can show them, but logarithmic plots and log-based analyses will exclude non-positive points.",
                    negative_i,
                )
            )

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

    i_min = float(np.min(finite_i)) if finite_i.size else float("nan")
    i_max = float(np.max(finite_i)) if finite_i.size else float("nan")
    dynamic_range = float(i_max / i_min) if np.isfinite(i_min) and i_min > 0 else float("inf")
    positive_dynamic_range = (
        float(np.max(positive_i) / np.min(positive_i)) if positive_i.size and np.min(positive_i) > 0 else float("inf")
    )
    log_invalid_points = int(np.sum(~np.isfinite(q) | ~np.isfinite(intensity) | (q <= 0) | (intensity <= 0)))
    log_valid_points = int(q.size - log_invalid_points)

    summary = {
        "q_min": float(np.min(finite_q)) if finite_q.size else float("nan"),
        "q_max": float(np.max(finite_q)) if finite_q.size else float("nan"),
        "I_min": i_min,
        "I_max": i_max,
        "data_points": int(q.size),
        "dynamic_range": dynamic_range,
        "positive_dynamic_range": positive_dynamic_range,
        "negative_I_count": negative_i,
        "negative_I_fraction": negative_fraction,
        "I_min_abs_ratio_to_positive_median": negative_abs_ratio,
        "allow_slight_negative_intensity": bool(allow_slight_negative_intensity),
        "slight_negative_abs_ratio_threshold": float(slight_negative_abs_ratio_threshold),
        "slight_negative_fraction_threshold": float(slight_negative_fraction_threshold),
        "log_valid_points": log_valid_points,
        "log_invalid_points": log_invalid_points,
    }
    return ValidationReport(curve_id=curve.curve_id, summary=summary, issues=issues)
