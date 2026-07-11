from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.core.data_model import CurveData
from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, power_law_analysis


LOG_WINDOW_SPANS_DECADES = (0.12, 0.20, 0.35, 0.50, 0.75)
LOG_WINDOW_POSITIONS_PER_SPAN = 32
MIN_INTERPRETABLE_LOG_SPAN_DECADES = 0.10
GUINIER_MAX_LOG_CENTER_FRACTION = 0.45


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


def _log_spaced_windows(
    q: np.ndarray,
    *,
    min_points: int,
    max_scanned_windows: int | None,
    max_center_fraction: float | None = None,
) -> tuple[list[tuple[int, int]], bool]:
    """Return multiscale half-open windows distributed uniformly in log(q).

    SAS files are often sampled nearly uniformly in linear q while spanning
    several q decades.  Stepping by row index therefore skips most low-q and
    peak-adjacent structure.  This helper proposes windows by logarithmic q
    span and then maps them back to the original sorted arrays without
    interpolating or changing the measured values.
    """

    if q.size < min_points or min_points <= 1:
        return [], False
    log_q = np.log10(q)
    total_span = float(log_q[-1] - log_q[0])
    if not np.isfinite(total_span) or total_span <= 0.0:
        return [], False

    spans = sorted(
        {
            min(float(span), total_span)
            for span in LOG_WINDOW_SPANS_DECADES
            if float(span) > 0.0
        }
    )
    proposed: set[tuple[int, int]] = set()
    for span in spans:
        if span >= total_span - 1e-12:
            log_starts = np.asarray([log_q[0]], dtype=float)
        else:
            log_starts = np.linspace(
                log_q[0],
                log_q[-1] - span,
                num=LOG_WINDOW_POSITIONS_PER_SPAN,
            )
        for log_start in log_starts:
            start = int(np.searchsorted(log_q, log_start, side="left"))
            stop = int(np.searchsorted(log_q, log_start + span, side="right"))
            stop = min(q.size, max(stop, start + min_points))
            if stop - start < min_points:
                start = max(0, q.size - min_points)
                stop = q.size
            if stop - start < min_points:
                continue
            center = 0.5 * (log_q[start] + log_q[stop - 1])
            center_fraction = float((center - log_q[0]) / total_span)
            if max_center_fraction is not None and center_fraction > max_center_fraction + 1e-12:
                continue
            proposed.add((start, stop))

    windows = sorted(
        proposed,
        key=lambda bounds: (
            0.5 * (log_q[bounds[0]] + log_q[bounds[1] - 1]),
            log_q[bounds[1] - 1] - log_q[bounds[0]],
            bounds,
        ),
    )
    limit = _window_limit(max_scanned_windows)
    if limit is None or len(windows) <= limit:
        return windows, False
    if limit == 0:
        return [], bool(windows)
    selected_indices = np.linspace(0, len(windows) - 1, num=limit).round().astype(int)
    return [windows[int(index)] for index in selected_indices], True


def _log_window_quality(q_segment: np.ndarray, *, min_points: int) -> tuple[float, float, float]:
    """Return log-span, span score, and point-count score for one window."""

    log_span = float(np.log10(q_segment[-1] / q_segment[0]))
    span_score = float(np.clip((log_span - 0.08) / 0.22, 0.0, 1.0))
    point_count_score = float(np.clip(q_segment.size / max(4 * min_points, 1), 0.0, 1.0))
    return log_span, span_score, point_count_score


def _chunked_log_slope_std(q_segment: np.ndarray, intensity_segment: np.ndarray) -> float | None:
    """Estimate slope stability without differentiating point-to-point noise."""

    chunk_count = min(5, q_segment.size // 4)
    if chunk_count < 2:
        return None
    log_q = np.log(q_segment)
    log_i = np.log(intensity_segment)
    slopes: list[float] = []
    for indices in np.array_split(np.arange(q_segment.size), chunk_count):
        if indices.size < 3 or np.ptp(log_q[indices]) <= 0.0:
            continue
        slope, _intercept = np.polyfit(log_q[indices], log_i[indices], 1)
        if np.isfinite(slope):
            slopes.append(float(-slope))
    if len(slopes) < 2:
        return None
    return float(np.std(slopes))


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

    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    windows, limit_reached = _log_spaced_windows(
        q,
        min_points=min_points,
        max_scanned_windows=limit,
        max_center_fraction=GUINIER_MAX_LOG_CENTER_FRACTION,
    )
    scanned_windows = len(windows)
    for start, stop in windows:
        q_segment = q[start:stop]
        q_min = float(q_segment[0])
        q_max = float(q_segment[-1])
        result = guinier_analysis(curve, (q_min, q_max), min_points=min_points)
        rg = result.results.get("Rg")
        r2 = result.results.get("R2")
        qrg_max = result.results.get("qRg_max")
        slope = result.results.get("slope")
        residual_rms = _rms(result.results.get("residuals", []))
        log_span, span_score, point_count_score = _log_window_quality(q_segment, min_points=min_points)
        warnings = list(result.warnings)
        if rg is None or r2 is None:
            score = 0.0
        else:
            r2_score = float(np.clip(float(r2), 0.0, 1.0))
            score = 0.80 * r2_score + 0.10 * span_score + 0.10 * point_count_score
            if qrg_max is not None and float(qrg_max) > 1.3:
                score = min(score, 0.49)
                warnings.append("qRg_max is above 1.3; this window is not fit-ready as a Guinier interval.")
            if slope is not None and slope >= 0:
                score = 0.0
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
                "log_q_span_decades": log_span,
                "log_q_span_score": span_score,
                "point_count_score": point_count_score,
                "window_sampling": "log_q_multiscale",
                "score": max(0.0, min(1.0, score)),
                "warnings": warnings,
            }
        )
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
    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    windows, limit_reached = _log_spaced_windows(
        q,
        min_points=min_points,
        max_scanned_windows=limit,
    )
    scanned_windows = len(windows)
    for start, stop in windows:
        q_segment = q[start:stop]
        segment = intensity[start:stop]
        q_min = float(q_segment[0])
        q_max = float(q_segment[-1])
        result = power_law_analysis(curve, (q_min, q_max), min_points=min_points)
        alpha = result.results.get("alpha")
        r2 = result.results.get("R2")
        local_std = _chunked_log_slope_std(q_segment, segment)
        log_span, span_score, point_count_score = _log_window_quality(q_segment, min_points=min_points)
        stability_score = 0.0 if local_std is None else float(1.0 / (1.0 + max(0.0, local_std)))
        if r2 is None or alpha is None:
            score = 0.0
        else:
            r2_score = float(np.clip(float(r2), 0.0, 1.0))
            score = 0.55 * r2_score + 0.20 * stability_score + 0.15 * span_score + 0.10 * point_count_score
        alpha_value = None if alpha is None else float(alpha)
        alpha_plausibility_score, alpha_score_cap, interpretation, alpha_warnings = _power_law_alpha_assessment(alpha_value)
        warnings = [*result.warnings, *alpha_warnings]
        if log_span < MIN_INTERPRETABLE_LOG_SPAN_DECADES:
            score = min(score, 0.49)
            warnings.append(
                "Power-law window spans less than 0.10 log10(q) decades; it is too narrow for an automatic fit-ready assignment."
            )
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
                "local_alpha_method": "chunked_log_linear",
                "local_alpha_stability_score": stability_score,
                "log_q_span_decades": log_span,
                "log_q_span_score": span_score,
                "point_count_score": point_count_score,
                "window_sampling": "log_q_multiscale",
                "interpretation": interpretation,
                "alpha_plausibility_score": alpha_plausibility_score,
                "alpha_range_warning": bool(alpha_warnings),
                "score": max(0.0, min(1.0, score)),
                "warnings": warnings,
            }
        )
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
    candidates: list[dict[str, Any]] = []
    limit = _window_limit(max_scanned_windows)
    position_range = global_q_range or q_range or (float(q[0]), float(q[-1]))
    high_noise = detect_high_q_noise(curve, q_range, min_points=min_points)
    global_high_q_noise_score = float(high_noise.get("high_q_noise_score", 0.0)) if high_noise is not None else 0.0
    noise_q_range = (
        (float(high_noise["q_min"]), float(high_noise["q_max"]))
        if high_noise is not None
        else None
    )
    windows, limit_reached = _log_spaced_windows(
        q,
        min_points=min_points,
        max_scanned_windows=limit,
    )
    scanned_windows = len(windows)
    for start, stop in windows:
        q_segment = q[start:stop]
        intensity_segment = intensity[start:stop]
        width = q_segment.size
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
        alpha_within_tolerance = False
        if alpha is not None:
            alpha_delta = abs(float(alpha) - alpha_target)
            alpha_within_tolerance = bool(alpha_delta <= alpha_tolerance)
            alpha_score = max(0.0, 1.0 - alpha_delta / max(alpha_tolerance, 1e-12))
        plateau_score = _plateau_score_from_cv(plateau_cv)
        positive_plateau_score = 1.0 if plateau_mean is not None and np.isfinite(plateau_mean) and plateau_mean > 0.0 else 0.0
        log_span, span_score, point_count_score = _log_window_quality(q_segment, min_points=min_points)
        position_score = 0.0 if q_position_fraction is None else min(1.0, max(0.0, (q_position_fraction - 0.50) / 0.50))
        r2_score = max(0.0, min(1.0, float(r2))) if r2 is not None and np.isfinite(r2) else 0.0
        overlaps_noise = bool(
            noise_q_range is not None
            and q_min <= noise_q_range[1]
            and q_max >= noise_q_range[0]
        )
        high_q_noise_score = global_high_q_noise_score if overlaps_noise else 0.0
        score = (
            0.30 * alpha_score
            + 0.25 * plateau_score
            + 0.15 * r2_score
            + 0.15 * position_score
            + 0.05 * point_count_score
            + 0.05 * span_score
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
        if log_span < MIN_INTERPRETABLE_LOG_SPAN_DECADES:
            score = min(score, 0.49)
            warnings.append("Porod window spans less than 0.10 log10(q) decades; it is too narrow for an automatic fit-ready assignment.")
        if high_q_noise_score >= 0.70:
            score = min(score, 0.49)
            warnings.append("This Porod window overlaps the detected high-q noise/background risk region.")
        candidates.append(
            {
                "q_min": q_min,
                "q_max": q_max,
                "fit_points": int(width),
                "alpha": alpha,
                "alpha_within_tolerance": alpha_within_tolerance,
                "R2": r2,
                "q4I_plateau_mean": plateau_mean,
                "q4I_plateau_std": plateau_std,
                "q4I_plateau_cv": plateau_cv,
                "plateau_stability_score": plateau_score,
                "positive_plateau_score": positive_plateau_score,
                "point_count_score": point_count_score,
                "log_q_span_decades": log_span,
                "log_q_span_score": span_score,
                "window_sampling": "log_q_multiscale",
                "q_center_geometric": q_center,
                "q_position_fraction": q_position_fraction,
                "q_position_score": position_score,
                "high_q_noise_score": high_q_noise_score,
                "high_q_noise_overlap": overlaps_noise,
                "score": score,
                "warnings": warnings,
            }
        )
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
    logq = np.log(q)
    logi = np.log(intensity)
    log_span = float(logq[-1] - logq[0])
    first_stop = max(
        min_points,
        int(np.searchsorted(logq, logq[0] + 0.20 * log_span, side="right")),
    )
    second_stop = max(
        first_stop + min_points,
        int(np.searchsorted(logq, logq[0] + 0.40 * log_span, side="right")),
    )
    second_stop = min(q.size, second_stop)
    if first_stop < min_points or second_stop - first_stop < min_points:
        return None
    low_alpha = -np.gradient(logi[:first_stop], logq[:first_stop])
    next_alpha = -np.gradient(logi[first_stop:second_stop], logq[first_stop:second_stop])
    ratio = float(
        np.median(intensity[:first_stop])
        / np.median(intensity[first_stop:second_stop])
    )
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
        "q_max": float(q[first_stop - 1]),
        "n_points": int(first_stop),
        "score": score,
        "low_q_upturn_ratio": ratio,
        "alpha_low_mean": alpha_low_mean,
        "alpha_next_mean": alpha_next_mean,
        "alpha_delta": alpha_delta,
        "comparison_q_range": (float(q[first_stop]), float(q[second_stop - 1])),
        "band_selection": "log_q_fraction_with_minimum_points",
        "suggested_action": "manual_review / avoid_auto_guinier",
        "warnings": ["Low-q upturn is a risk signal; it is not fit-ready by default."],
    }


def detect_high_q_noise(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    min_points: int = 8,
) -> dict[str, Any] | None:
    q_all = np.asarray(curve.q, dtype=float)
    intensity_all = np.asarray(curve.intensity, dtype=float)
    q_min = float(np.nanmin(q_all)) if q_range is None and q_all.size else q_range[0] if q_range else 0.0
    q_max = float(np.nanmax(q_all)) if q_range is None and q_all.size else q_range[1] if q_range else 0.0
    mask = (
        np.isfinite(q_all)
        & np.isfinite(intensity_all)
        & (q_all > 0)
        & (q_all >= q_min)
        & (q_all <= q_max)
    )
    q = q_all[mask]
    intensity = intensity_all[mask]
    if q.size > 1:
        order = np.argsort(q)
        q = q[order]
        intensity = intensity[order]
        unique_q, unique_indices = np.unique(q, return_index=True)
        q = unique_q
        intensity = intensity[unique_indices]
    if q.size < min_points * 2:
        return None
    log_q = np.log(q)
    log_span = float(log_q[-1] - log_q[0])
    high_start = int(np.searchsorted(log_q, log_q[0] + 0.875 * log_span, side="left"))
    mid_start = int(np.searchsorted(log_q, log_q[0] + 0.750 * log_span, side="left"))
    high_start = min(high_start, q.size - min_points)
    mid_start = min(mid_start, max(0, high_start - min_points))
    high_q = q[high_start:]
    high_i = intensity[high_start:]
    mid_i = intensity[mid_start:high_start]
    positive_high = high_i > 0.0
    positive_q = high_q[positive_high]
    positive_i = high_i[positive_high]
    alpha = (
        -np.gradient(np.log(positive_i), np.log(positive_q))
        if positive_q.size >= 3
        else np.asarray([])
    )
    alpha_high_std = float(np.nanstd(alpha)) if alpha.size else None
    q4i = high_q**4 * high_i
    q4_mean = float(np.nanmean(q4i)) if q4i.size else None
    q4_std = float(np.nanstd(q4i)) if q4i.size else None
    q4_cv = float(q4_std / abs(q4_mean)) if q4_mean not in (None, 0.0) else None
    mid_scale = float(np.median(np.abs(mid_i))) if mid_i.size else 0.0
    ratio = float(np.median(np.abs(high_i)) / mid_scale) if mid_scale > 0.0 else None
    nonpositive_fraction = float(np.mean(high_i <= 0.0)) if high_i.size else 0.0
    high_median = float(np.median(high_i)) if high_i.size else 0.0
    high_scale = float(np.median(np.abs(high_i))) if high_i.size else 0.0
    relative_mad = (
        float(np.median(np.abs(high_i - high_median)) / high_scale)
        if high_scale > 0.0
        else None
    )
    cv_score = min(1.0, max(0.0, (q4_cv or 0.0) / 1.0))
    alpha_score = min(1.0, max(0.0, (alpha_high_std or 0.0) / 1.0))
    nonpositive_score = min(1.0, max(0.0, nonpositive_fraction / 0.20))
    dispersion_score = min(1.0, max(0.0, (relative_mad or 0.0) / 0.50))
    score = max(cv_score, alpha_score, nonpositive_score, dispersion_score)
    if score < 0.50:
        return None
    return {
        "q_min": float(high_q[0]),
        "q_max": float(high_q[-1]),
        "n_points": int(high_q.size),
        "score": score,
        "high_q_noise_score": score,
        "alpha_high_std": alpha_high_std,
        "q4I_cv_high": q4_cv,
        "high_q_to_mid_q_ratio": ratio,
        "nonpositive_fraction": nonpositive_fraction,
        "relative_mad": relative_mad,
        "band_selection": "upper_log_q_band",
        "suggested_exclusion_range": (float(high_q[0]), float(high_q[-1])),
        "warnings": ["High-q noise/background risk region is not fit-ready by default."],
    }
