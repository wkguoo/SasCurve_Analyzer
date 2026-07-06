from __future__ import annotations

import math

import numpy as np

from app.core.analysis_schema import EXPORT_TABLE_PEAKS, RESULT_GROUP_LAMELLAR, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.feature_extraction import detect_peaks
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def lamellar_analysis(curve: CurveData, q_range: tuple[float, float], *, prominence: float | None = None) -> AnalysisResult:
    peak_result = detect_peaks(curve, q_range, prominence=prominence)
    peaks = list(peak_result.results.get("peaks", []))
    peaks.sort(key=lambda row: row.get("peak_q", math.inf))
    first_q = peaks[0]["peak_q"] if peaks else None
    long_period = float(2.0 * math.pi / first_q) if first_q else None
    indexed_peaks = []
    for index, peak in enumerate(peaks):
        q_ratio = float(peak["peak_q"] / first_q) if first_q else None
        nearest_order = int(round(q_ratio)) if q_ratio else None
        order_error = abs(q_ratio - nearest_order) if q_ratio and nearest_order else None
        correlation_length = float(2.0 * math.pi / peak["FWHM"]) if peak.get("FWHM") not in (None, 0.0) else None
        row = dict(peak)
        row.update(
            {
                "q_ratio_to_first": q_ratio,
                "nearest_lamellar_order": nearest_order,
                "order_error": order_error,
                "correlation_length_candidate": correlation_length,
            }
        )
        indexed_peaks.append(row)
    order_errors = [row["order_error"] for row in indexed_peaks[1:] if row.get("order_error") is not None]
    mean_order_error = float(np.mean(order_errors)) if order_errors else None
    checks = [
        validity_check("has_primary_peak", first_q is not None, severity="error", message="No primary peak was detected."),
        validity_check("multiple_orders", len(indexed_peaks) >= 2, severity="warning", message="Only one lamellar peak/order was detected.", value=len(indexed_peaks), threshold=2),
        validity_check("integer_order_spacing", mean_order_error is None or mean_order_error <= 0.12, severity="warning", message="Peak positions do not follow clear integer lamellar order spacing.", value=mean_order_error, threshold=0.12),
    ]
    assumptions = ["lamellar_or_periodic_structure_required"]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    results = {
        "primary_peak_q": first_q,
        "long_period_candidate": long_period,
        "peak_count": len(indexed_peaks),
        "mean_order_error": mean_order_error,
        "indexed_peaks": indexed_peaks,
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

