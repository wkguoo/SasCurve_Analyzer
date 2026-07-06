from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.core.analysis_schema import (
    EXPORT_TABLE_GUINIER_CANDIDATES,
    EXPORT_TABLE_PEAKS,
    EXPORT_TABLE_POWER_LAW_CANDIDATES,
    RESULT_GROUP_MODEL_FREE,
    merge_standard_metadata,
)
from app.core.data_model import AnalysisResult, CurveData
from app.core.feature_extraction import detect_peaks
from app.core.fitting import linear_fit
from app.core.model_free import guinier_analysis, invariant_measured, power_law_analysis
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _finite_positive_curve(curve: CurveData, q_range: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    q_min = float(np.nanmin(curve.q)) if q_range is None else q_range[0]
    q_max = float(np.nanmax(curve.q)) if q_range is None else q_range[1]
    mask = (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & (curve.intensity > 0)
        & (curve.q >= q_min)
        & (curve.q <= q_max)
    )
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if q.size > 1:
        order = np.argsort(q)
        q = q[order]
        intensity = intensity[order]
    return q, intensity


def _rms(values: list[float] | np.ndarray) -> float | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return float(np.sqrt(np.mean(arr**2)))


def scan_guinier_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 5,
    max_candidates: int = 8,
) -> list[dict[str, Any]]:
    q, _ = _finite_positive_curve(curve, q_range)
    if q.size < min_points:
        return []

    low_limit = max(min_points, min(q.size, max(12, q.size // 3)))
    window_sizes = sorted({min_points, min(max(min_points + 2, q.size // 12), low_limit), min(max(min_points + 4, q.size // 6), low_limit)})
    step = max(1, low_limit // 12)
    candidates: list[dict[str, Any]] = []
    for width in window_sizes:
        if width < min_points or width > low_limit:
            continue
        for start in range(0, low_limit - width + 1, step):
            q_min = float(q[start])
            q_max = float(q[start + width - 1])
            result = guinier_analysis(curve, (q_min, q_max), min_points=min_points)
            rg = result.results.get("Rg")
            r2 = result.results.get("R2")
            qrg_max = result.results.get("qRg_max")
            slope = result.results.get("slope")
            residual_rms = _rms(result.results.get("residuals", []))
            if rg is None or r2 is None:
                score = 0.0
            else:
                qrg_penalty = max(0.0, float(qrg_max or 0.0) - 1.3) * 0.35
                slope_penalty = 0.4 if slope is not None and slope >= 0 else 0.0
                score = max(0.0, min(1.0, float(r2) - qrg_penalty - slope_penalty))
            candidates.append(
                {
                    "q_min": q_min,
                    "q_max": q_max,
                    "fit_points": result.results.get("fit_points"),
                    "Rg": rg,
                    "I0": result.results.get("I0"),
                    "lnI0": result.results.get("lnI0"),
                    "qRg_min": result.results.get("qRg_min"),
                    "qRg_max": qrg_max,
                    "R2": r2,
                    "reduced_chi_square": result.results.get("reduced_chi_square"),
                    "residual_rms": residual_rms,
                    "score": score,
                    "warnings": result.warnings,
                }
            )
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:max_candidates]


def scan_power_law_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 6,
    max_candidates: int = 10,
) -> list[dict[str, Any]]:
    q, intensity = _finite_positive_curve(curve, q_range)
    if q.size < min_points:
        return []
    window_sizes = sorted({min_points, min(max(min_points + 2, q.size // 8), q.size), min(max(min_points + 4, q.size // 4), q.size)})
    step = max(1, q.size // 24)
    candidates: list[dict[str, Any]] = []
    for width in window_sizes:
        if width < min_points or width > q.size:
            continue
        for start in range(0, q.size - width + 1, step):
            q_min = float(q[start])
            q_max = float(q[start + width - 1])
            result = power_law_analysis(curve, (q_min, q_max), min_points=min_points)
            alpha = result.results.get("alpha")
            r2 = result.results.get("R2")
            segment = intensity[start : start + width]
            q_segment = q[start : start + width]
            local_alpha = -np.gradient(np.log(segment), np.log(q_segment)) if width >= 3 else np.asarray([])
            local_std = float(np.std(local_alpha)) if local_alpha.size else None
            if r2 is None or alpha is None:
                score = 0.0
            else:
                stability_penalty = min(0.4, float(local_std or 0.0))
                score = max(0.0, min(1.0, float(r2) - stability_penalty))
            if alpha is None:
                interpretation = "not_interpretable"
            elif abs(alpha - 4.0) <= 0.3:
                interpretation = "porod_like"
            elif 1.0 < alpha < 3.0:
                interpretation = "mass_fractal_candidate"
            elif 3.0 < alpha < 4.0:
                interpretation = "surface_fractal_candidate"
            else:
                interpretation = "empirical_power_law"
            candidates.append(
                {
                    "q_min": q_min,
                    "q_max": q_max,
                    "fit_points": result.results.get("fit_points"),
                    "alpha": alpha,
                    "prefactor": result.results.get("prefactor"),
                    "R2": r2,
                    "local_alpha_std": local_std,
                    "interpretation": interpretation,
                    "score": score,
                    "warnings": result.warnings,
                }
            )
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:max_candidates]


def curve_quality_metrics(curve: CurveData, q_range: tuple[float, float] | None = None) -> dict[str, Any]:
    q_all = curve.q
    i_all = curve.intensity
    q, intensity = _finite_positive_curve(curve, q_range)
    finite_i = i_all[np.isfinite(i_all)]
    quality: dict[str, Any] = {
        "q_min": float(np.nanmin(q_all)) if q_all.size else None,
        "q_max": float(np.nanmax(q_all)) if q_all.size else None,
        "I_min": float(np.nanmin(finite_i)) if finite_i.size else None,
        "I_max": float(np.nanmax(finite_i)) if finite_i.size else None,
        "data_points": int(q_all.size),
        "positive_log_points": int(q.size),
        "negative_intensity_points": int(np.sum(i_all < 0)),
        "zero_intensity_points": int(np.sum(i_all == 0)),
        "nan_points": int(np.sum(~np.isfinite(q_all)) + np.sum(~np.isfinite(i_all))),
        "q_monotonic": bool(q_all.size < 2 or np.all(np.diff(q_all[np.isfinite(q_all)]) > 0)),
    }
    if q.size >= 2:
        quality["dynamic_range"] = float(np.nanmax(intensity) / np.nanmin(intensity)) if np.nanmin(intensity) > 0 else None
        quality["integrated_intensity"] = float(np.trapezoid(intensity, q))
        quality["finite_invariant"] = float(np.trapezoid(q**2 * intensity, q))
    else:
        quality["dynamic_range"] = None
        quality["integrated_intensity"] = None
        quality["finite_invariant"] = None
    if q.size >= 7:
        log_i = np.log(intensity)
        second_diff = np.diff(log_i, n=2)
        quality["noise_level_estimate"] = float(np.median(np.abs(second_diff)) / 0.6745) if second_diff.size else None
        first_count = max(2, q.size // 10)
        quality["low_q_upturn_ratio"] = float(np.median(intensity[:first_count]) / np.median(intensity[first_count : 2 * first_count])) if 2 * first_count <= q.size else None
        last_count = max(2, q.size // 10)
        quality["high_q_to_mid_q_ratio"] = float(np.median(intensity[-last_count:]) / np.median(intensity[q.size // 2 : q.size // 2 + last_count]))
        derivative = np.gradient(log_i, np.log(q))
        signs = np.sign(derivative)
        quality["turning_point_count"] = int(np.sum(np.diff(signs) != 0))
    else:
        quality["noise_level_estimate"] = None
        quality["low_q_upturn_ratio"] = None
        quality["high_q_to_mid_q_ratio"] = None
        quality["turning_point_count"] = 0
    return quality


def _deep_peak_detection(curve: CurveData, q_range: tuple[float, float] | None) -> tuple[list[dict[str, Any]], list[str]]:
    q, intensity = _finite_positive_curve(curve, q_range)
    if q.size < 3:
        return [], ["Too few valid points for peak detection."]
    prominence = float(0.05 * (np.nanmax(intensity) - np.nanmin(intensity)))
    if not np.isfinite(prominence) or prominence <= 0:
        prominence = None
    result = detect_peaks(curve, (float(q.min()), float(q.max())), prominence=prominence)
    peaks = list(result.results.get("peaks", []))
    peaks.sort(key=lambda row: row.get("peak_q") or math.inf)
    first_q = peaks[0]["peak_q"] if peaks else None
    for index, peak in enumerate(peaks):
        peak["peak_order"] = index + 1
        peak["q_ratio_to_first"] = float(peak["peak_q"] / first_q) if first_q else None
        if index > 0:
            peak["delta_q_from_previous"] = float(peak["peak_q"] - peaks[index - 1]["peak_q"])
    return peaks, result.warnings


def run_deep_scan(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    max_candidates: int = 8,
) -> AnalysisResult:
    if q_range is None:
        q_range = (float(np.nanmin(curve.q)), float(np.nanmax(curve.q)))
    quality = curve_quality_metrics(curve, q_range)
    guinier_candidates = scan_guinier_candidates(curve, q_range, max_candidates=max_candidates)
    power_law_candidates = scan_power_law_candidates(curve, q_range, max_candidates=max_candidates)
    peaks, peak_warnings = _deep_peak_detection(curve, q_range)
    invariant = invariant_measured(curve, q_range)

    checks = [
        validity_check("enough_points", quality["positive_log_points"] >= 10, severity="error", message="Need at least 10 positive finite points for reliable deep scan.", value=quality["positive_log_points"], threshold=10),
        validity_check("q_monotonic", quality["q_monotonic"], severity="warning", message="q values should be strictly increasing."),
        validity_check("has_guinier_candidate", bool(guinier_candidates), severity="info", message="No stable automatic Guinier candidate was found."),
        validity_check("has_power_law_candidate", bool(power_law_candidates), severity="info", message="No stable automatic power-law candidate was found."),
        validity_check("non_negative_intensity", quality["negative_intensity_points"] == 0, severity="warning", message="Negative intensity values were found.", value=quality["negative_intensity_points"]),
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
            "Peak d=2*pi/q is a characteristic spacing unless a morphology model is supplied.",
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
        parameters={"max_candidates": max_candidates},
        results=results,
        warnings=warnings,
    )
