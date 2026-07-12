from __future__ import annotations

import math

import numpy as np
from scipy.signal import find_peaks, peak_prominences, peak_widths

from app.core.data_model import AnalysisResult, CurveData
from app.core.method_warnings import peak_warnings, warning_to_dict, warning_to_text


def _finite_float(value) -> float | None:
    """Return a finite built-in float or ``None`` for an unavailable scalar."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _safe_group_mean(values: np.ndarray) -> float | None:
    """Average finite duplicate values without overflowing their intermediate sum."""

    if not values.size or not np.all(np.isfinite(values)):
        return None
    scale = _finite_float(np.max(np.abs(values)))
    if scale is None:
        return None
    if scale == 0.0:
        return 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        mean = scale * float(np.mean(values / scale))
    return _finite_float(mean)


def _safe_trapezoid(values: np.ndarray, coordinates: np.ndarray) -> float | None:
    """Integrate only when the trapezoidal reduction remains finite."""

    if values.size < 2 or coordinates.size < 2:
        return 0.0
    if not (np.all(np.isfinite(values)) and np.all(np.isfinite(coordinates))):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        integral = np.trapezoid(values, coordinates)
    return _finite_float(integral)


def _safe_positive_ratio(numerator: float, denominator: float) -> float | None:
    """Return a finite positive ratio, withholding overflowed derived values."""

    if denominator <= 0.0:
        return None
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        ratio = numerator / denominator
    value = _finite_float(ratio)
    return value if value is not None and value > 0.0 else None


def detect_peaks(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    prominence: float | None = None,
    noise_score_threshold: float = 3.0,
) -> AnalysisResult:
    """Detect peaks with a trend-residual candidate gate and raw-data metrics.

    Automatic discovery uses positive ``ln(I)`` residuals after a linear
    ``ln(I)``-versus-``ln(q)`` trend. Widths, areas, and intensities are still
    calculated from the unsmoothed raw points. A peak candidate is not a
    reportable scattering feature unless its geometry, baseline area, and
    robust noise-separation score pass separate checks.
    """

    if prominence is not None:
        prominence_value = _finite_float(prominence)
        if prominence_value is None or prominence_value < 0.0:
            raise ValueError("prominence must be a finite non-negative number when supplied.")
        prominence = prominence_value
    q_min, q_max = q_range
    mask = np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q >= q_min) & (curve.q <= q_max)
    q = np.asarray(curve.q[mask], dtype=float)
    intensity = np.asarray(curve.intensity[mask], dtype=float)
    error = None
    if curve.error is not None and curve.error.shape == curve.q.shape:
        error = np.asarray(curve.error[mask], dtype=float)
    warnings: list[str] = []
    if q.size > 1:
        order = np.argsort(q, kind="stable")
        q = q[order]
        intensity = intensity[order]
        if error is not None:
            error = error[order]
        unique_q, inverse = np.unique(q, return_inverse=True)
        if unique_q.size != q.size:
            collapsed_intensity = np.empty(unique_q.shape, dtype=float)
            for group_index in range(unique_q.size):
                value = _safe_group_mean(intensity[inverse == group_index])
                collapsed_intensity[group_index] = np.nan if value is None else value
            if error is not None:
                collapsed_error = np.full(unique_q.shape, np.nan, dtype=float)
                for group_index in range(unique_q.size):
                    values = error[inverse == group_index]
                    finite_values = values[np.isfinite(values)]
                    if finite_values.size:
                        value = _safe_group_mean(finite_values)
                        collapsed_error[group_index] = np.nan if value is None else value
            keep = np.isfinite(unique_q) & np.isfinite(collapsed_intensity)
            rejected_count = int(np.count_nonzero(~keep))
            intensity = collapsed_intensity[keep]
            if error is not None:
                error = collapsed_error[keep]
            warnings.append(f"Collapsed {int(q.size - unique_q.size)} duplicate q rows by mean intensity before peak detection.")
            if rejected_count:
                warnings.append(f"Excluded {rejected_count} duplicate-q groups whose collapsed intensity was non-finite before peak detection.")
            q = unique_q[keep]

    noise_threshold = _finite_float(noise_score_threshold)
    if noise_threshold is None or noise_threshold <= 0.0:
        raise ValueError("noise_score_threshold must be finite and positive.")

    detection_mode = "raw_intensity"
    robust_noise_scale = None
    residual_by_index = np.full(q.size, np.nan, dtype=float)
    if q.size >= 7:
        positive_indices = np.flatnonzero(intensity > 0.0)
        if positive_indices.size >= 7:
            with np.errstate(divide="ignore", invalid="ignore"):
                log_q = np.log(q[positive_indices])
                log_intensity = np.log(intensity[positive_indices])
            if np.all(np.isfinite(log_q)) and np.all(np.isfinite(log_intensity)):
                try:
                    trend = np.polyval(np.polyfit(log_q, log_intensity, deg=1), log_q)
                    residual = log_intensity - trend
                except (np.linalg.LinAlgError, ValueError):
                    residual = np.full(log_intensity.shape, np.nan, dtype=float)
                if np.all(np.isfinite(residual)):
                    robust_noise_scale = _finite_float(
                        1.4826 * np.median(np.abs(residual - np.median(residual)))
                    )
                    if robust_noise_scale is not None:
                        residual_by_index[positive_indices] = residual

    if prominence is None:
        if robust_noise_scale is None:
            raw_peaks, raw_properties = find_peaks(intensity, prominence=(None, None))
            if raw_peaks.size <= 3:
                peaks, properties = raw_peaks, raw_properties
                detection_mode = "raw_intensity_small_candidate_fallback"
            else:
                peaks, properties = np.asarray([], dtype=int), {}
            warnings.append(
                "Automatic peak discovery could not estimate a robust log-domain noise scale; "
                f"raw fallback retained only when it produced at most three candidates (found {raw_peaks.size})."
            )
        else:
            detection_mode = "log_intensity_trend_residual"
            positive_indices = np.flatnonzero(np.isfinite(residual_by_index))
            residual = residual_by_index[positive_indices]
            residual_prominence = max(0.05, noise_threshold * robust_noise_scale)
            min_distance = max(3, int(q.size // 25))
            residual_peaks, _ = find_peaks(
                residual,
                prominence=(residual_prominence, None),
                distance=min_distance,
            )
            peaks = positive_indices[residual_peaks]
            if peaks.size:
                raw_prominence, raw_left, raw_right = peak_prominences(intensity, peaks)
                properties = {
                    "prominences": raw_prominence,
                    "left_bases": raw_left,
                    "right_bases": raw_right,
                }
            else:
                raw_peaks, raw_properties = find_peaks(intensity, prominence=(None, None))
                if raw_peaks.size <= 3:
                    peaks, properties = raw_peaks, raw_properties
                    detection_mode = "raw_intensity_small_candidate_fallback"
                else:
                    properties = {}
            warnings.append(
                "Automatic peak discovery used log-intensity trend residuals; "
                f"robust noise scale={robust_noise_scale:.6g}, threshold={residual_prominence:.6g}, "
                f"minimum distance={min_distance} points."
            )
    else:
        # Explicit prominence is a user/test-controlled raw-intensity request.
        peaks, properties = find_peaks(intensity, prominence=(prominence, None))
    peak_results: list[dict] = []
    if peaks.size:
        widths = peak_widths(intensity, peaks, rel_height=0.5)
        sample_positions = np.arange(q.size, dtype=float)
        for i, peak_index in enumerate(peaks):
            peak_q = _finite_float(q[peak_index])
            peak_intensity = _finite_float(intensity[peak_index])
            if peak_q is None or peak_intensity is None:
                warnings.append("Skipped a peak candidate with a non-finite q or intensity scalar.")
                continue
            peak_prominence = _finite_float(properties.get("prominences", np.full(peaks.size, np.nan))[i])
            robust_noise_score = None
            if robust_noise_scale is not None and robust_noise_scale > 0.0 and np.isfinite(residual_by_index[peak_index]):
                robust_noise_score = _finite_float(abs(residual_by_index[peak_index]) / robust_noise_scale)
            peak_snr = None
            peak_snr_unavailable_reason = None
            if peak_prominence is None:
                peak_snr_unavailable_reason = "Peak prominence is unavailable."
            elif error is None:
                peak_snr_unavailable_reason = "No valid error column."
            else:
                peak_error = _finite_float(error[peak_index])
                if peak_error is None or peak_error <= 0.0:
                    peak_snr_unavailable_reason = "Peak error value is not finite and positive."
                else:
                    peak_snr = _safe_positive_ratio(peak_prominence, peak_error)
                    if peak_snr is None:
                        peak_snr_unavailable_reason = "Peak SNR overflowed or became non-finite."

            left_ip = _finite_float(widths[2][i])
            right_ip = _finite_float(widths[3][i])
            left_base_index = int(properties.get("left_bases", np.full(peaks.size, peak_index))[i])
            right_base_index = int(properties.get("right_bases", np.full(peaks.size, peak_index))[i])
            left_base_q = _finite_float(q[left_base_index])
            right_base_q = _finite_float(q[right_base_index])
            left_base_i = _finite_float(intensity[left_base_index])
            right_base_i = _finite_float(intensity[right_base_index])
            baseline_edge_limited = bool(left_base_index == 0 or right_base_index == q.size - 1)
            half_height_at_edge = bool(
                left_ip is None
                or right_ip is None
                or left_ip <= 0.0
                or right_ip >= float(q.size - 1)
            )
            left_support_truncated = False
            right_support_truncated = False
            if left_base_index == 0 and right_base_index == q.size - 1:
                left_support_truncated = True
                right_support_truncated = True
            elif left_base_index == 0 and right_base_i is not None:
                half_level = _finite_float(right_base_i + 0.5 * (peak_intensity - right_base_i))
                left_support_truncated = half_level is None or not bool(np.any(intensity[: peak_index + 1] <= half_level))
            elif right_base_index == q.size - 1 and left_base_i is not None:
                half_level = _finite_float(left_base_i + 0.5 * (peak_intensity - left_base_i))
                right_support_truncated = half_level is None or not bool(np.any(intensity[peak_index:] <= half_level))
            edge_truncation = bool(half_height_at_edge or left_support_truncated or right_support_truncated)
            crossings_available = bool(
                left_ip is not None
                and right_ip is not None
                and right_ip > left_ip
                and not edge_truncation
            )

            baseline = None
            net_height = None
            full_baseline_corrected_area = None
            if None not in (left_base_q, right_base_q, left_base_i, right_base_i) and right_base_q > left_base_q:
                baseline = _finite_float(np.interp(peak_q, [left_base_q, right_base_q], [left_base_i, right_base_i]))
                if baseline is not None:
                    net_height = _finite_float(peak_intensity - baseline)
                base_inside = (q > left_base_q) & (q < right_base_q)
                base_area_q = np.concatenate(([left_base_q], q[base_inside], [right_base_q]))
                base_area_i = np.concatenate(([left_base_i], intensity[base_inside], [right_base_i]))
                base_line_i = np.interp(base_area_q, [left_base_q, right_base_q], [left_base_i, right_base_i])
                full_baseline_corrected_area = _safe_trapezoid(base_area_i - base_line_i, base_area_q)

            fwhm = hwhm = left_hwhm = right_hwhm = asymmetry = None
            raw_area = baseline_corrected_area = peak_area = correlation_length = None
            left_q = right_q = None
            if crossings_available:
                left_q = _finite_float(np.interp(left_ip, sample_positions, q))
                right_q = _finite_float(np.interp(right_ip, sample_positions, q))
                if left_q is not None and right_q is not None and right_q > left_q:
                    fwhm = _finite_float(right_q - left_q)
                if fwhm is not None and fwhm > 0.0:
                    hwhm = _finite_float(fwhm / 2.0)
                    left_hwhm = _finite_float(peak_q - left_q) if peak_q >= left_q else None
                    right_hwhm = _finite_float(right_q - peak_q) if right_q >= peak_q else None
                    if left_hwhm is not None and left_hwhm > 0.0 and right_hwhm is not None:
                        asymmetry = _safe_positive_ratio(right_hwhm, left_hwhm)
                    left_i = _finite_float(np.interp(left_ip, sample_positions, intensity))
                    right_i = _finite_float(np.interp(right_ip, sample_positions, intensity))
                    if left_i is not None and right_i is not None:
                        inside = (q > left_q) & (q < right_q)
                        area_q = np.concatenate(([left_q], q[inside], [right_q]))
                        area_i = np.concatenate(([left_i], intensity[inside], [right_i]))
                        raw_area = _safe_trapezoid(area_i, area_q)
                        baseline_i = np.interp(area_q, [left_q, right_q], [left_i, right_i])
                        baseline_corrected_area = _safe_trapezoid(area_i - baseline_i, area_q)
                    correlation_length = _safe_positive_ratio(2.0 * math.pi, fwhm)
            if (
                not baseline_edge_limited
                and baseline is not None
                and net_height is not None
                and net_height > 0.0
            ):
                peak_area = full_baseline_corrected_area
            d_spacing = _safe_positive_ratio(2.0 * math.pi, peak_q)

            validity_reasons: list[str] = []
            if edge_truncation:
                validity_reasons.append("peak_or_half_height_crossing_is_truncated_by_selected_q_range")
            if baseline_edge_limited:
                validity_reasons.append("prominence_contour_baseline_touches_selected_q_range_edge")
            if fwhm is None:
                validity_reasons.append("two_sided_fwhm_unavailable")
            if baseline is None or net_height is None or net_height <= 0.0:
                validity_reasons.append("baseline_or_net_height_unavailable")
            if peak_area is None or not math.isfinite(float(peak_area)) or peak_area <= 0.0:
                validity_reasons.append("baseline_corrected_area_nonpositive_or_unavailable")
            if crossings_available and raw_area is None:
                validity_reasons.append("raw_area_within_fwhm_overflowed_or_unavailable")
            if crossings_available and baseline_corrected_area is None:
                validity_reasons.append("baseline_corrected_area_within_fwhm_overflowed_or_unavailable")
            if not baseline_edge_limited and baseline is not None and net_height is not None and net_height > 0.0 and peak_area is None:
                validity_reasons.append("full_baseline_corrected_area_overflowed_or_unavailable")
            if fwhm is not None and correlation_length is None:
                validity_reasons.append("correlation_length_overflowed_or_unavailable")
            if d_spacing is None:
                validity_reasons.append("d_spacing_overflowed_or_unavailable")
            validity = "valid" if not validity_reasons else "limited" if edge_truncation or baseline_edge_limited else "invalid"
            validity_reason = "; ".join(validity_reasons) if validity_reasons else None
            if any("overflow" in reason for reason in validity_reasons):
                warnings.append(f"Peak at q={peak_q:g} has derived scalar(s) unavailable because a finite-range calculation overflowed or became non-finite.")
            peak_results.append(
                {
                    "peak_q": peak_q,
                    "peak_I": peak_intensity,
                    "peak_index": int(peak_index),
                    "FWHM": fwhm,
                    "left_q": left_q,
                    "right_q": right_q,
                    "peak_prominence": peak_prominence,
                    "peak_snr": peak_snr,
                    "peak_snr_unavailable_reason": peak_snr_unavailable_reason,
                    "peak_area": raw_area,
                    "raw_area_within_fwhm": raw_area,
                    "baseline_corrected_peak_area": baseline_corrected_area,
                    "baseline": baseline,
                    "net_height": net_height,
                    "area": peak_area,
                    "HWHM": hwhm,
                    "left_HWHM": left_hwhm,
                    "right_HWHM": right_hwhm,
                    "asymmetry": asymmetry,
                    "prominence": peak_prominence,
                    "SNR": peak_snr,
                    "robust_noise_score": robust_noise_score,
                    "noise_score_method": "median_absolute_deviation_of_log_intensity_trend_residual" if robust_noise_scale is not None else None,
                    "confirmation_status": "candidate",
                    "correlation_length": correlation_length,
                    "edge_truncation": edge_truncation,
                    "edge_truncated": edge_truncation,
                    "baseline_edge_limited": baseline_edge_limited,
                    "baseline_method": "scipy_prominence_contour",
                    "baseline_provenance": {
                        "method": "scipy_prominence_contour",
                        "left_base_index": left_base_index,
                        "right_base_index": right_base_index,
                        "left_base_q": left_base_q,
                        "right_base_q": right_base_q,
                        "interpretation": "Numerical prominence-contour baseline; not a fitted physical background.",
                    },
                    "validity": validity,
                    "valid": validity == "valid",
                    "is_valid": validity == "valid",
                    "validity_reason": validity_reason,
                    "validity_reasons": validity_reasons,
                    "d": d_spacing,
                }
            )
    else:
        warnings.append("No peak was detected in the selected q range.")

    confirmed_count = 0
    noise_scores: list[float] = []
    for row in peak_results:
        score = _finite_float(row.get("robust_noise_score"))
        if score is not None:
            noise_scores.append(score)
        reasons = []
        if row.get("valid") is not True:
            reasons.append("peak_geometry_or_baseline_invalid")
        if row.get("area") is None or _finite_float(row.get("area")) is None or float(row.get("area")) <= 0.0:
            reasons.append("baseline_corrected_area_nonpositive_or_unavailable")
        if score is None:
            reasons.append("robust_noise_score_unavailable")
        elif score < noise_threshold:
            reasons.append("robust_noise_score_below_confirmation_threshold")
        if row.get("SNR") is not None and _finite_float(row.get("SNR")) is not None and float(row["SNR"]) < noise_threshold:
            reasons.append("error_column_snr_below_confirmation_threshold")
        if not reasons:
            row["confirmation_status"] = "confirmed_candidate"
            confirmed_count += 1
        else:
            row["confirmation_status"] = "unconfirmed_candidate"
            row["confirmation_reasons"] = reasons

    method_warnings = peak_warnings()
    detection_status = (
        "not_detected"
        if not peak_results
        else "detected"
        if confirmed_count > 0
        else "tentative"
    )
    detection_reason_codes = []
    if peak_results:
        detection_reason_codes.append("peak_candidates_found")
    if confirmed_count:
        detection_reason_codes.append("peak_confirmation_passed")
    else:
        detection_reason_codes.append("peak_confirmation_not_passed")
    if any(_finite_float(row.get("area")) is not None and float(row["area"]) <= 0.0 for row in peak_results):
        detection_reason_codes.append("peak_area_nonpositive")
    if robust_noise_scale is None:
        detection_reason_codes.append("robust_noise_score_unavailable")
    return AnalysisResult.create(
        curve=curve,
        analysis_type="peak_detection",
        q_range=q_range,
        parameters={"signal": "I(q)", "prominence": prominence},
        results={
            "peaks": peak_results,
            "peak_count": len(peak_results),
            "candidate_count": len(peak_results),
            "confirmed_peak_count": confirmed_count,
            "noise_separation_score": _finite_float(np.median(noise_scores)) if noise_scores else None,
            "detection_status": detection_status,
            "detection_reason_codes": detection_reason_codes,
            "detection_mode": detection_mode,
            "robust_noise_scale": robust_noise_scale,
            "noise_score_threshold": noise_threshold,
        },
        warnings=[*warnings, *(warning_to_text(warning) for warning in method_warnings)],
        structured_warnings=[warning_to_dict(warning) for warning in method_warnings],
    )

