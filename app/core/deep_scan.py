from __future__ import annotations

from typing import Any

import numpy as np

from app.core import region_scanners as _region_scanners
from app.core.analysis_schema import (
    EXPORT_TABLE_GUINIER_CANDIDATES,
    EXPORT_TABLE_PEAKS,
    EXPORT_TABLE_POWER_LAW_CANDIDATES,
    RESULT_GROUP_MODEL_FREE,
    merge_standard_metadata,
)
from app.core.data_model import AnalysisResult, CurveData
from app.core.model_free import invariant_measured
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _finite_positive_curve(curve: CurveData, q_range: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    return _region_scanners.finite_positive_curve(curve, q_range)


def scan_guinier_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 5,
    max_candidates: int = 8,
    max_scanned_windows: int = 200,
) -> list[dict[str, Any]]:
    return _region_scanners.scan_guinier_candidates(
        curve,
        q_range,
        min_points=min_points,
        max_candidates=max_candidates,
        max_scanned_windows=max_scanned_windows,
    )


def scan_power_law_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 6,
    max_candidates: int = 10,
    max_scanned_windows: int = 200,
) -> list[dict[str, Any]]:
    return _region_scanners.scan_power_law_candidates(
        curve,
        q_range,
        min_points=min_points,
        max_candidates=max_candidates,
        max_scanned_windows=max_scanned_windows,
    )


def curve_quality_metrics(curve: CurveData, q_range: tuple[float, float] | None = None) -> dict[str, Any]:
    return _region_scanners.curve_quality_metrics(curve, q_range)


def _deep_peak_detection(curve: CurveData, q_range: tuple[float, float] | None) -> tuple[list[dict[str, Any]], list[str]]:
    return _region_scanners.deep_peak_detection(curve, q_range)


def run_deep_scan(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    max_candidates: int = 8,
    max_scanned_windows: int = 200,
) -> AnalysisResult:
    if q_range is None:
        finite_q = curve.q[np.isfinite(curve.q)]
        q_range = (float(np.nanmin(finite_q)), float(np.nanmax(finite_q))) if finite_q.size else (float("nan"), float("nan"))

    quality = curve_quality_metrics(curve, q_range)
    guinier_candidates = scan_guinier_candidates(
        curve,
        q_range,
        max_candidates=max_candidates,
        max_scanned_windows=max_scanned_windows,
    )
    power_law_candidates = scan_power_law_candidates(
        curve,
        q_range,
        max_candidates=max_candidates,
        max_scanned_windows=max_scanned_windows,
    )
    peaks, peak_warnings = _deep_peak_detection(curve, q_range)
    invariant = invariant_measured(curve, q_range)

    checks = [
        validity_check(
            "enough_points",
            quality["positive_log_points"] >= 10,
            severity="error",
            message="Need at least 10 positive finite points for reliable deep scan.",
            value=quality["positive_log_points"],
            threshold=10,
        ),
        validity_check("q_monotonic", quality["q_monotonic"], severity="warning", message="q values should be strictly increasing."),
        validity_check("has_guinier_candidate", bool(guinier_candidates), severity="info", message="No stable automatic Guinier candidate was found."),
        validity_check("has_power_law_candidate", bool(power_law_candidates), severity="info", message="No stable automatic power-law candidate was found."),
        validity_check(
            "non_negative_intensity",
            quality["negative_intensity_points"] == 0,
            severity="warning",
            message="Negative intensity values were found.",
            value=quality["negative_intensity_points"],
        ),
    ]
    label, score = reliability_from_checks(checks)
    warnings = warning_messages_from_checks(checks)
    warnings.extend(peak_warnings)

    best_guinier = guinier_candidates[0] if guinier_candidates else None
    best_power_law = power_law_candidates[0] if power_law_candidates else None
    results = {
        "quality": quality,
        "best_guinier": best_guinier,
        "best_power_law": best_power_law,
        "peak_count": len(peaks),
        "peaks": peaks,
        "finite_invariant": invariant.results.get("Q_measured"),
        "guinier_candidate_count": len(guinier_candidates),
        "power_law_candidate_count": len(power_law_candidates),
        "multiscale_candidate_count": len(peaks) + len([row for row in power_law_candidates if row.get("score", 0.0) >= 0.75]),
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_MODEL_FREE,
        reliability_label=label,
        reliability_score=score,
        validity_checks=checks,
        interpretation_limits=[
            "Deep scan is a model-free triage. It ranks candidate intervals but does not prove a unique structure.",
            "Peak d=2pi/q is a characteristic spacing unless a morphology model is supplied.",
        ],
        export_tables={
            EXPORT_TABLE_GUINIER_CANDIDATES: guinier_candidates,
            EXPORT_TABLE_POWER_LAW_CANDIDATES: power_law_candidates,
            EXPORT_TABLE_PEAKS: peaks,
        },
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="deep_scan",
        q_range=q_range,
        parameters={"max_candidates": max_candidates, "max_scanned_windows": max_scanned_windows},
        results=results,
        warnings=warnings,
    )
