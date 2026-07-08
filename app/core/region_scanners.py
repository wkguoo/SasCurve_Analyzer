from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.core.data_model import CurveData
from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, power_law_analysis


def finite_positive_curve(curve: CurveData, q_range: tuple[float, float] | None = None) -> tuple[np.ndarray, np.ndarray]:
    q_min = float(np.nanmin(curve.q)) if q_range is None and curve.q.size else q_range[0] if q_range else 0.0
    q_max = float(np.nanmax(curve.q)) if q_range is None and curve.q.size else q_range[1] if q_range else 0.0
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
        unique_q, unique_indices = np.unique(q, return_index=True)
        if unique_q.size != q.size:
            q = unique_q
            intensity = intensity[unique_indices]
    return q, intensity


def _rms(values: list[float] | np.ndarray) -> float | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    return float(np.sqrt(np.mean(arr**2)))


def _window_limit(max_scanned_windows: int | None) -> int | None:
    if max_scanned_windows is None:
        return None
    return max(0, int(max_scanned_windows))


def _finalize_window_limit_fields(
    candidates: list[dict[str, Any]],
    *,
    scanned_windows: int,
    max_scanned_windows: int | None,
    max_scanned_windows_reached: bool,
) -> None:
    for row in candidates:
        row["scanned_windows"] = int(scanned_windows)
        row["max_scanned_windows"] = max_scanned_windows
        row["max_scanned_windows_reached"] = bool(max_scanned_windows_reached)
        if max_scanned_windows_reached:
            row.setdefault("warnings", []).append(
                f"Stopped sliding-window scan after max_scanned_windows={max_scanned_windows}; review q range or increase the limit if needed."
            )


def _log_q_position_fraction(q_center: float, q_range: tuple[float, float] | None) -> float | None:
    if q_range is None:
        return None
    q_min, q_max = sorted((float(q_range[0]), float(q_range[1])))
    if q_center <= 0 or q_min <= 0 or q_max <= 0 or math.isclose(q_min, q_max):
        return None
    value = (math.log(q_center) - math.log(q_min)) / (math.log(q_max) - math.log(q_min))
    return float(max(0.0, min(1.0, value)))


def _power_law_alpha_assessment(alpha: float | None) -> tuple[float, float | None, str, list[str]]:
    if alpha is None or not np.isfinite(alpha):
        return 0.0, 0.49, "not_interpretable", ["Power-law alpha is not finite; this interval is not fit-ready."]
    value = float(alpha)
    warnings: list[str] = []
    cap: float | None = None
    if value < 0.0:
        cap = 0.49
        warnings.append("Power-law alpha is negative and outside the usual empirical SAS range; treat this interval as descriptive only.")
        interpretation = "out_of_range_empirical_slope"
    elif value <= 6.0:
        interpretation = "empirical_power_law"
    elif value <= 8.0:
        cap = 0.69
        warnings.append("Power-law alpha is above 6 and outside the usual empirical SAS range; require manual review.")
        interpretation = "out_of_range_empirical_slope"
    else:
        cap = 0.49
        warnings.append("Power-law alpha is above 8 and outside the usual empirical SAS range; do not treat this as a fit-ready SAS region.")
        interpretation = "out_of_range_empirical_slope"

    if cap is None:
        if abs(value - 4.0) <= 0.3:
            interpretation = "porod_like"
        elif 1.0 < value < 3.0:
            interpretation = "mass_fractal_candidate"
        elif 3.0 < value < 4.0:
            interpretation = "surface_fractal_candidate"
    plausibility_score = 1.0 if cap is None else cap
    return plausibility_score, cap, interpretation, warnings


def scan_guinier_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 5,
    max_candidates: int = 8,
    max_scanned_windows: int = 200,
) -> list[dict[str, Any]]:
    q, _ = finite_positive_curve(curve, q_range)
    if q.size < min_points:
        return []

    low_limit = max(min_points, min(q.size, max(12, q.size // 3)))
    window_sizes = sorted({min_points, min(max(min_points + 2, q.size // 12), low_limit), min(max(min_points + 4, q.size // 6), low_limit)})
    step = max(1, low_limit // 12)
    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    scanned_windows = 0
    limit_reached = False
    for width in window_sizes:
        if width < min_points or width > low_limit:
            continue
        for start in range(0, low_limit - width + 1, step):
            if limit is not None and scanned_windows >= limit:
                limit_reached = True
                break
            scanned_windows += 1
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
                    "slope": slope,
                    "intercept": result.results.get("intercept"),
                    "qRg_min": result.results.get("qRg_min"),
                    "qRg_max": qrg_max,
                    "R2": r2,
                    "reduced_chi_square": result.results.get("reduced_chi_square"),
                    "residual_rms": residual_rms,
                    "score": score,
                    "warnings": result.warnings,
                }
            )
        if limit_reached:
            break
    _finalize_window_limit_fields(
        candidates,
        scanned_windows=scanned_windows,
        max_scanned_windows=limit,
        max_scanned_windows_reached=limit_reached,
    )
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:max_candidates]


def scan_power_law_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 6,
    max_candidates: int = 10,
    max_scanned_windows: int = 200,
) -> list[dict[str, Any]]:
    q, intensity = finite_positive_curve(curve, q_range)
    if q.size < min_points:
        return []
    window_sizes = sorted({min_points, min(max(min_points + 2, q.size // 8), q.size), min(max(min_points + 4, q.size // 4), q.size)})
    step = max(1, q.size // 24)
    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    scanned_windows = 0
    limit_reached = False
    for width in window_sizes:
        if width < min_points or width > q.size:
            continue
        for start in range(0, q.size - width + 1, step):
            if limit is not None and scanned_windows >= limit:
                limit_reached = True
                break
            scanned_windows += 1
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
            alpha_value = None if alpha is None else float(alpha)
            alpha_plausibility_score, alpha_score_cap, interpretation, alpha_warnings = _power_law_alpha_assessment(alpha_value)
            if alpha_score_cap is not None:
                score = min(score, alpha_score_cap)
            candidates.append(
                {
                    "q_min": q_min,
                    "q_max": q_max,
                    "fit_points": result.results.get("fit_points"),
                    "alpha": alpha,
                    "slope": result.results.get("slope"),
                    "intercept": result.results.get("intercept"),
                    "prefactor": result.results.get("prefactor"),
                    "R2": r2,
                    "local_alpha_std": local_std,
                    "interpretation": interpretation,
                    "alpha_plausibility_score": alpha_plausibility_score,
                    "alpha_range_warning": bool(alpha_warnings),
                    "score": score,
                    "warnings": [*result.warnings, *alpha_warnings],
                }
            )
        if limit_reached:
            break
    _finalize_window_limit_fields(
        candidates,
        scanned_windows=scanned_windows,
        max_scanned_windows=limit,
        max_scanned_windows_reached=limit_reached,
    )
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:max_candidates]


def curve_quality_metrics(curve: CurveData, q_range: tuple[float, float] | None = None) -> dict[str, Any]:
    q_all = curve.q
    i_all = curve.intensity
    q, intensity = finite_positive_curve(curve, q_range)
    finite_i = i_all[np.isfinite(i_all)]
    finite_q = q_all[np.isfinite(q_all)]
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
        "q_monotonic": bool(finite_q.size < 2 or np.all(np.diff(finite_q) > 0)),
        "duplicate_q_points": int(finite_q.size - np.unique(finite_q).size) if finite_q.size else 0,
        "has_error_column": curve.error is not None,
    }
    if q.size >= 2:
        quality["dynamic_range"] = float(np.nanmax(intensity) / np.nanmin(intensity)) if np.nanmin(intensity) > 0 else None
        quality["integrated_intensity"] = float(np.trapezoid(intensity, q))
        quality["finite_invariant"] = float(np.trapezoid(q**2 * intensity, q))
        quality["q_range_decades"] = float(np.log10(np.nanmax(q) / np.nanmin(q))) if np.nanmin(q) > 0 else None
    else:
        quality["dynamic_range"] = None
        quality["integrated_intensity"] = None
        quality["finite_invariant"] = None
        quality["q_range_decades"] = None
    if q.size >= 7:
        log_i = np.log(intensity)
        second_diff = np.diff(log_i, n=2)
        quality["noise_level_estimate"] = float(np.median(np.abs(second_diff)) / 0.6745) if second_diff.size else None
        first_count = max(2, q.size // 10)
        quality["low_q_upturn_ratio"] = float(np.median(intensity[:first_count]) / np.median(intensity[first_count : 2 * first_count])) if 2 * first_count <= q.size else None
        last_count = max(2, q.size // 10)
        mid_start = max(0, q.size // 2)
        quality["high_q_to_mid_q_ratio"] = float(np.median(intensity[-last_count:]) / np.median(intensity[mid_start : mid_start + last_count]))
        derivative = np.gradient(log_i, np.log(q))
        signs = np.sign(derivative)
        quality["turning_point_count"] = int(np.sum(np.diff(signs) != 0))
    else:
        quality["noise_level_estimate"] = None
        quality["low_q_upturn_ratio"] = None
        quality["high_q_to_mid_q_ratio"] = None
        quality["turning_point_count"] = 0
    return quality


def deep_peak_detection(curve: CurveData, q_range: tuple[float, float] | None) -> tuple[list[dict[str, Any]], list[str]]:
    q, intensity = finite_positive_curve(curve, q_range)
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
        peak_index = int(peak.get("peak_index", 0))
        if 0 <= peak_index < intensity.size:
            local_left = max(0, peak_index - 5)
            local_right = min(intensity.size, peak_index + 6)
            local_values = np.delete(intensity[local_left:local_right], peak_index - local_left)
            local_baseline = float(np.nanmedian(local_values)) if local_values.size else None
            peak["peak_local_baseline"] = local_baseline
            peak["peak_local_contrast"] = (
                float(peak["peak_I"] / local_baseline)
                if local_baseline is not None and np.isfinite(local_baseline) and local_baseline > 0
                else None
            )
        else:
            peak.setdefault("warnings", []).append("Peak index is outside the temporary sorted q array.")
            peak["peak_local_baseline"] = None
            peak["peak_local_contrast"] = None
        if index > 0:
            peak["delta_q_from_previous"] = float(peak["peak_q"] - peaks[index - 1]["peak_q"])
        if peak.get("left_q") is not None and peak.get("right_q") is not None and peak["left_q"] < peak["right_q"]:
            peak["q_start"] = float(peak["left_q"])
            peak["q_end"] = float(peak["right_q"])
            peak["q_boundary_source"] = "fwhm"
        else:
            peak_index = int(peak.get("peak_index", 0))
            if 0 < peak_index < q.size - 1:
                peak["q_start"] = float(q[peak_index - 1])
                peak["q_end"] = float(q[peak_index + 1])
                peak["q_boundary_source"] = "neighbor_points"
            else:
                left = max(0, peak_index - 1)
                right = min(q.size - 1, peak_index + 1)
                peak["q_start"] = float(q[left])
                peak["q_end"] = float(q[right])
                peak["q_boundary_source"] = "fallback_window"
                peak.setdefault("warnings", []).append("Peak is too close to data boundary.")
    return peaks, result.warnings


def _plateau_score_from_cv(cv: float | None) -> float:
    if cv is None or not np.isfinite(cv):
        return 0.0
    if cv <= 0.20:
        return 1.0
    if cv <= 0.35:
        return 0.75
    if cv <= 0.50:
        return 0.50
    return 0.0


def scan_porod_candidates(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 8,
    max_candidates: int = 8,
    max_scanned_windows: int = 200,
    alpha_target: float = 4.0,
    alpha_tolerance: float = 0.4,
    global_q_range: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    q, intensity = finite_positive_curve(curve, q_range)
    if q.size < min_points:
        return []
    window_sizes = sorted({min_points, min(max(min_points + 2, q.size // 8), q.size), min(max(min_points + 4, q.size // 4), q.size)})
    step = max(1, q.size // 24)
    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    scanned_windows = 0
    limit_reached = False
    position_range = global_q_range or q_range or (float(q[0]), float(q[-1]))
    high_noise = detect_high_q_noise(curve, q_range, min_points=min_points)
    high_q_noise_score = float(high_noise.get("high_q_noise_score", 0.0)) if high_noise is not None else 0.0
    for width in window_sizes:
        if width < min_points or width > q.size:
            continue
        for start in range(0, q.size - width + 1, step):
            if limit is not None and scanned_windows >= limit:
                limit_reached = True
                break
            scanned_windows += 1
            q_segment = q[start : start + width]
            intensity_segment = intensity[start : start + width]
            q_min = float(q_segment[0])
            q_max = float(q_segment[-1])
            q_center = float(math.sqrt(q_min * q_max)) if q_min > 0 and q_max > 0 else float(np.nanmean(q_segment))
            power = power_law_analysis(curve, (q_min, q_max), min_points=min_points)
            alpha = power.results.get("alpha")
            r2 = power.results.get("R2")
            q4i = q_segment**4 * intensity_segment
            plateau_mean = float(np.nanmean(q4i)) if q4i.size else None
            plateau_std = float(np.nanstd(q4i)) if q4i.size else None
            plateau_cv = float(plateau_std / abs(plateau_mean)) if plateau_mean not in (None, 0.0) else None
            q_position_fraction = _log_q_position_fraction(q_center, position_range)
            alpha_score = 0.0
            if alpha is not None:
                alpha_score = max(0.0, 1.0 - abs(float(alpha) - alpha_target) / max(alpha_tolerance, 1e-12))
            plateau_score = _plateau_score_from_cv(plateau_cv)
            positive_plateau_score = 1.0 if plateau_mean is not None and np.isfinite(plateau_mean) and plateau_mean > 0.0 else 0.0
            point_count_score = min(1.0, width / max(2 * min_points, 1))
            position_score = 0.0 if q_position_fraction is None else min(1.0, max(0.0, (q_position_fraction - 0.50) / 0.50))
            r2_score = max(0.0, min(1.0, float(r2))) if r2 is not None and np.isfinite(r2) else 0.0
            score = (
                0.30 * alpha_score
                + 0.25 * plateau_score
                + 0.15 * r2_score
                + 0.15 * position_score
                + 0.10 * point_count_score
                + 0.05 * positive_plateau_score
                - 0.25 * high_q_noise_score
            )
            score = max(0.0, min(1.0, score))
            warnings: list[str] = list(power.warnings)
            if q_position_fraction is None or q_position_fraction < 0.65:
                score = min(score, 0.69)
                warnings.append("Porod-like candidate is not in the high-q part of the selected curve; avoid high-confidence Porod assignment.")
            if positive_plateau_score <= 0.0:
                score = min(score, 0.49)
                warnings.append("q4I plateau mean is not positive; Porod plateau is not physically interpretable.")
            if plateau_cv is not None and plateau_cv > 0.50:
                score = min(score, 0.49)
                warnings.append("q4I plateau coefficient of variation is above 0.50; Porod plateau stability score is 0.")
            if high_q_noise_score >= 0.70:
                score = min(score, 0.49)
                warnings.append("High-q noise/background score is high; Porod candidate is not fit-ready by default.")
            candidates.append(
                {
                    "q_min": q_min,
                    "q_max": q_max,
                    "fit_points": int(width),
                    "alpha": alpha,
                    "R2": r2,
                    "q4I_plateau_mean": plateau_mean,
                    "q4I_plateau_std": plateau_std,
                    "q4I_plateau_cv": plateau_cv,
                    "plateau_stability_score": plateau_score,
                    "positive_plateau_score": positive_plateau_score,
                    "point_count_score": point_count_score,
                    "q_center_geometric": q_center,
                    "q_position_fraction": q_position_fraction,
                    "q_position_score": position_score,
                    "high_q_noise_score": high_q_noise_score,
                    "score": score,
                    "warnings": warnings,
                }
            )
        if limit_reached:
            break
    _finalize_window_limit_fields(
        candidates,
        scanned_windows=scanned_windows,
        max_scanned_windows=limit,
        max_scanned_windows_reached=limit_reached,
    )
    candidates.sort(key=lambda row: row["score"], reverse=True)
    return candidates[:max_candidates]


def detect_low_q_upturn(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 8,
    ratio_threshold: float = 1.25,
    alpha_delta_threshold: float = 0.45,
) -> dict[str, Any] | None:
    q, intensity = finite_positive_curve(curve, q_range)
    if q.size < min_points * 2:
        return None
    segment = max(min_points, q.size // 8)
    segment = min(segment, q.size // 3)
    logq = np.log(q)
    logi = np.log(intensity)
    alpha = -np.gradient(logi, logq)
    low_alpha = alpha[:segment]
    next_alpha = alpha[segment : 2 * segment]
    ratio = float(np.median(intensity[:segment]) / np.median(intensity[segment : 2 * segment]))
    alpha_low_mean = float(np.nanmean(low_alpha)) if low_alpha.size else None
    alpha_next_mean = float(np.nanmean(next_alpha)) if next_alpha.size else None
    alpha_delta = None if alpha_low_mean is None or alpha_next_mean is None else float(alpha_low_mean - alpha_next_mean)
    score = 0.0
    if alpha_delta is not None:
        ratio_score = min(1.0, max(0.0, (ratio - ratio_threshold) / ratio_threshold))
        alpha_score = min(1.0, max(0.0, alpha_delta / max(alpha_delta_threshold * 2.0, 1e-12)))
        score = max(0.0, min(1.0, 0.45 + 0.25 * ratio_score + 0.30 * alpha_score))
    if ratio <= ratio_threshold or alpha_delta is None or alpha_delta <= alpha_delta_threshold:
        return None
    return {
        "q_min": float(q[0]),
        "q_max": float(q[segment - 1]),
        "n_points": int(segment),
        "score": score,
        "low_q_upturn_ratio": ratio,
        "alpha_low_mean": alpha_low_mean,
        "alpha_next_mean": alpha_next_mean,
        "alpha_delta": alpha_delta,
        "suggested_action": "manual_review / avoid_auto_guinier",
        "warnings": ["Low-q upturn is a risk signal; it is not fit-ready by default."],
    }


def detect_high_q_noise(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 8,
) -> dict[str, Any] | None:
    q, intensity = finite_positive_curve(curve, q_range)
    if q.size < min_points * 2:
        return None
    segment = max(min_points, q.size // 6)
    segment = min(segment, q.size // 2)
    high_q = q[-segment:]
    high_i = intensity[-segment:]
    mid_start = max(0, q.size // 2 - segment // 2)
    mid_i = intensity[mid_start : mid_start + segment]
    alpha = -np.gradient(np.log(high_i), np.log(high_q)) if high_q.size >= 3 else np.asarray([])
    alpha_high_std = float(np.nanstd(alpha)) if alpha.size else None
    q4i = high_q**4 * high_i
    q4_mean = float(np.nanmean(q4i)) if q4i.size else None
    q4_std = float(np.nanstd(q4i)) if q4i.size else None
    q4_cv = float(q4_std / abs(q4_mean)) if q4_mean not in (None, 0.0) else None
    ratio = float(np.median(high_i) / np.median(mid_i)) if mid_i.size and np.median(mid_i) != 0 else None
    cv_score = min(1.0, max(0.0, (q4_cv or 0.0) / 1.0))
    alpha_score = min(1.0, max(0.0, (alpha_high_std or 0.0) / 1.0))
    score = max(cv_score, alpha_score)
    if score < 0.50:
        return None
    return {
        "q_min": float(high_q[0]),
        "q_max": float(high_q[-1]),
        "n_points": int(segment),
        "score": score,
        "high_q_noise_score": score,
        "alpha_high_std": alpha_high_std,
        "q4I_cv_high": q4_cv,
        "high_q_to_mid_q_ratio": ratio,
        "suggested_exclusion_range": (float(high_q[0]), float(high_q[-1])),
        "warnings": ["High-q noise/background risk region is not fit-ready by default."],
    }
