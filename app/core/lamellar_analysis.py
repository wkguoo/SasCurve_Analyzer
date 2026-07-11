from __future__ import annotations

import math

import numpy as np

from app.core.analysis_schema import EXPORT_TABLE_PEAKS, RESULT_GROUP_LAMELLAR, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.feature_extraction import detect_peaks
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _finite_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _safe_length_from_reciprocal(value) -> float | None:
    numeric = _finite_float(value)
    if numeric is None or numeric <= 0.0:
        return None
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        length = 2.0 * math.pi / numeric
    return float(length) if math.isfinite(length) else None


def _finite_table_value(value):
    if isinstance(value, dict):
        return {key: _finite_table_value(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_finite_table_value(nested) for nested in value]
    if isinstance(value, tuple):
        return [_finite_table_value(nested) for nested in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def lamellar_analysis(curve: CurveData, q_range: tuple[float, float], *, prominence: float | None = None) -> AnalysisResult:
    peak_result = detect_peaks(curve, q_range, prominence=prominence)
    peaks = [
        row
        for row in peak_result.results.get("peaks", [])
        if _finite_float(row.get("peak_q")) is not None and _finite_float(row.get("peak_q")) > 0.0
    ]
    peaks.sort(key=lambda row: float(row["peak_q"]))
    first_q = _finite_float(peaks[0]["peak_q"]) if peaks else None
    long_period = _safe_length_from_reciprocal(first_q)
    indexed_peaks = []
    for peak in peaks:
        peak_q = _finite_float(peak.get("peak_q"))
        q_ratio = _finite_float(peak_q / first_q) if peak_q is not None and first_q else None
        nearest_order = int(round(q_ratio)) if q_ratio is not None and q_ratio > 0.0 else None
        order_error = _finite_float(abs(q_ratio - nearest_order)) if q_ratio is not None and nearest_order else None
        correlation_length = _safe_length_from_reciprocal(peak.get("FWHM"))
        row = _finite_table_value(dict(peak))
        row.update(
            {
                "q_ratio_to_first": q_ratio,
                "nearest_lamellar_order": nearest_order,
                "order_index": nearest_order,
                "order_error": order_error,
                "deviation_from_integer_order": order_error,
                "correlation_length_candidate": correlation_length,
            }
        )
        indexed_peaks.append(row)
    order_errors = [row["order_error"] for row in indexed_peaks[1:] if row.get("order_error") is not None]
    mean_order_error = _finite_float(np.mean(order_errors)) if order_errors else None
    order_backfit_residuals = [
        _finite_float(row["peak_q"] - row["order_index"] * first_q)
        for row in indexed_peaks
        if first_q is not None and row.get("order_index") is not None
    ]
    order_backfit_residuals = [value for value in order_backfit_residuals if value is not None]
    order_index_backfit_rmse = (
        _finite_float(np.sqrt(np.mean(np.square(order_backfit_residuals)))) if len(order_backfit_residuals) >= 2 else None
    )
    order_index_backfit_relative_rmse = (
        _finite_float(order_index_backfit_rmse / first_q) if order_index_backfit_rmse is not None and first_q else None
    )
    peak_orders = [int(row["order_index"]) for row in indexed_peaks if row.get("order_index") is not None]
    checks = [
        validity_check("has_primary_peak", first_q is not None, severity="error", message="No primary peak was detected."),
        validity_check("multiple_orders", len(indexed_peaks) >= 2, severity="warning", message="Only one lamellar peak/order was detected.", value=len(indexed_peaks), threshold=2),
        validity_check("integer_order_spacing", mean_order_error is None or mean_order_error <= 0.12, severity="warning", message="Peak positions do not follow clear integer lamellar order spacing.", value=mean_order_error, threshold=0.12),
    ]
    assumptions = [
        "lamellar_or_periodic_structure_required",
        "sample_type_not_confirmed",
        "first_peak_is_fundamental_assumption",
        "finite_q_coverage",
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    if label == "high":
        label = "assumption_dependent"
    q0_status = "assumption_dependent" if first_q is not None else "missing_prerequisite"
    q0_invalid_reason = (
        "q0 is assigned to the first detected peak and requires the unconfirmed assumption that it is the fundamental periodic order."
        if first_q is not None
        else "No primary scattering peak was detected in the selected q range."
    )
    if long_period is not None:
        d0_status = "assumption_dependent"
        d0_invalid_reason = "d0 = 2π/q0 is a periodic-spacing candidate, not direct proof of a lamellar morphology."
    elif first_q is not None:
        d0_status = "invalid_value"
        d0_invalid_reason = "d0 = 2π/q0 overflowed or became non-finite for the detected q0."
    else:
        d0_status = "missing_prerequisite"
        d0_invalid_reason = "d0 cannot be calculated without an assigned q0 peak."
    results = {
        "primary_peak_q": first_q,
        "q0": first_q,
        "q0_status": q0_status,
        "q0_invalid_reason": q0_invalid_reason,
        "long_period_candidate": long_period,
        "long_period": long_period,
        "d0": long_period,
        "d0_status": d0_status,
        "d0_invalid_reason": d0_invalid_reason,
        "peak_count": len(indexed_peaks),
        "peak_orders": peak_orders if peak_orders else None,
        "peak_orders_status": "assumption_dependent" if peak_orders else "missing_prerequisite",
        "peak_orders_invalid_reason": "Peak orders are conditional on assigning the first detected peak as q0." if peak_orders else "No peaks could be assigned an integer lamellar order.",
        "mean_order_error": mean_order_error,
        "mean_order_error_status": "assumption_dependent" if mean_order_error is not None else "missing_prerequisite",
        "mean_order_error_invalid_reason": "Integer-order deviation requires at least one higher-order peak." if mean_order_error is None else "Deviation is conditional on the q0 fundamental-peak assignment.",
        "order_index_backfit_rmse": order_index_backfit_rmse,
        "order_index_backfit_relative_rmse": order_index_backfit_relative_rmse,
        "order_index_backfit_status": "available" if order_index_backfit_rmse is not None else "missing_prerequisite",
        "order_index_backfit_invalid_reason": None if order_index_backfit_rmse is not None else "At least two indexed peaks are required for an order-index back-fit diagnostic.",
        "indexed_peaks": indexed_peaks,
        "q_extrapolation_status": "finite_range",
        "q_extrapolation_invalid_reason": "Peak indexing uses only the selected measured q range; missing low-order or high-order peaks can change the q0 assignment.",
        "prerequisites": {
            "sample_type": {
                "status": "assumption_required",
                "reason": "q0/d0 interpretation requires a periodic or lamellar sample model that is not confirmed by peak positions alone.",
            },
            "q_coverage": {
                "status": "satisfied" if first_q is not None else "missing_prerequisite",
                "reason": None if first_q is not None else "No primary peak was found in the selected q range.",
            },
            "absolute_intensity": {
                "status": "not_required",
                "reason": "Peak-position indexing does not use absolute intensity calibration.",
            },
            "contrast": {
                "status": "not_required",
                "reason": "Peak-position indexing does not use scattering contrast.",
            },
            "q_extrapolation": {
                "status": "finite_range",
                "reason": "Only observed peak positions in the selected q range are indexed.",
            },
            "porod_plateau": {
                "status": "not_applicable",
                "reason": "No Porod extrapolation is performed in lamellar peak indexing.",
            },
        },
        "assumption_status": "assumption_dependent",
        "analysis_status": "assumption_dependent",
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_LAMELLAR,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Lamellar long period requires a periodic or quasi-periodic morphology assumption.",
            "Single-peak estimates are characteristic spacings; multiple orders are needed for stronger indexing.",
        ],
        export_tables={EXPORT_TABLE_PEAKS: indexed_peaks},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="lamellar",
        q_range=q_range,
        parameters={"prominence": prominence},
        results=results,
        warnings=[*peak_result.warnings, *warning_messages_from_checks(checks)],
    )

