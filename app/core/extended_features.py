"""Array-level, descriptive features for one-dimensional SAS curves.

The functions in this module deliberately return numerical descriptors only.
They do not assign a morphology or mechanism to a curve.  Inputs are copied
only when sorting is required and are never changed in place.
"""

from __future__ import annotations

import math
import numbers
from collections.abc import Iterable

import numpy as np
from scipy.signal import find_peaks


class FeatureRows(list[dict]):
    """A list of detected feature rows with machine-readable warnings.

    Keeping the return value list-compatible preserves the simple detector
    interface while allowing callers to inspect why a detector returned no
    rows (for example, when too few valid points were supplied).
    """

    def __init__(self, rows: Iterable[dict] = (), *, warnings: Iterable[str] = ()) -> None:
        super().__init__(rows)
        self.warnings = list(warnings)


def _as_1d_float_arrays(q, intensity) -> tuple[np.ndarray, np.ndarray]:
    """Validate equally shaped one-dimensional array-like inputs."""

    q_array = np.asarray(q, dtype=float)
    intensity_array = np.asarray(intensity, dtype=float)
    if q_array.ndim != 1 or intensity_array.ndim != 1:
        raise ValueError("q and intensity must be one-dimensional arrays.")
    if q_array.shape != intensity_array.shape:
        raise ValueError("q and intensity must have the same shape.")
    return q_array, intensity_array


def _finite_integer_parameter(value, name: str, *, minimum: int) -> int:
    """Validate a count-like public parameter before it reaches slices or SciPy."""

    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite integer.")
    number = float(value)
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"{name} must be a finite integer.")
    result = int(number)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return result


def _finite_nonnegative_parameter(value, name: str) -> float:
    """Validate a finite non-negative numerical threshold."""

    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a finite non-negative number.")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite non-negative number.")
    return number


def _finite_positive_ratio(numerator: float, denominator: float) -> float | None:
    """Return a finite positive quotient without publishing overflowed d values."""

    if denominator <= 0.0:
        return None
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        value = numerator / denominator
    return float(value) if math.isfinite(float(value)) and value > 0.0 else None


def _finite_mean(values: np.ndarray) -> float | None:
    """Return a finite mean without overflowing a sum of finite values."""

    if not values.size or not np.all(np.isfinite(values)):
        return None
    scale = float(np.max(np.abs(values)))
    if not math.isfinite(scale):
        return None
    if scale == 0.0:
        return 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        mean = scale * float(np.mean(values / scale))
    return mean if math.isfinite(mean) else None


def _sorted_valid_arrays(
    q,
    intensity,
    *,
    positive_q: bool = False,
    positive_intensity: bool = False,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return finite, sorted arrays and the number of filtered input rows."""

    q_array, intensity_array = _as_1d_float_arrays(q, intensity)
    mask = np.isfinite(q_array) & np.isfinite(intensity_array)
    if positive_q:
        mask &= q_array > 0.0
    if positive_intensity:
        mask &= intensity_array > 0.0
    filtered_count = int(q_array.size - np.count_nonzero(mask))
    q_valid = q_array[mask]
    intensity_valid = intensity_array[mask]
    if q_valid.size > 1:
        order = np.argsort(q_valid, kind="stable")
        q_valid = q_valid[order]
        intensity_valid = intensity_valid[order]
    return q_valid, intensity_valid, filtered_count


def _finite_group_mean(values: np.ndarray) -> float | None:
    """Return a finite mean without first overflowing a sum of finite values."""

    if not values.size or not np.all(np.isfinite(values)):
        return None
    scale = float(np.max(np.abs(values)))
    if not math.isfinite(scale):
        return None
    if scale == 0.0:
        return 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        mean = scale * float(np.mean(values / scale))
    return mean if math.isfinite(mean) else None


def _collapse_duplicate_q(q: np.ndarray, intensity: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Safely average repeated q rows and drop any non-finite collapsed group."""

    if q.size < 2 or not np.any(np.diff(q) == 0.0):
        return q, intensity, 0, 0
    unique_q, inverse = np.unique(q, return_inverse=True)
    collapsed_intensity = np.empty(unique_q.shape, dtype=float)
    for group_index in range(unique_q.size):
        mean = _finite_group_mean(intensity[inverse == group_index])
        collapsed_intensity[group_index] = np.nan if mean is None else mean
    keep = np.isfinite(unique_q) & np.isfinite(collapsed_intensity)
    rejected_count = int(np.count_nonzero(~keep))
    return (
        unique_q[keep],
        collapsed_intensity[keep],
        int(q.size - unique_q.size),
        rejected_count,
    )


def _safe_trapezoid(y: np.ndarray, q: np.ndarray) -> float | None:
    """Return a finite trapezoid integral, or ``None`` when reduction overflows."""

    if y.size < 2 or q.size < 2:
        return 0.0
    if not (np.all(np.isfinite(y)) and np.all(np.isfinite(q))):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        integral = float(np.trapezoid(y, q))
    return integral if math.isfinite(integral) else None


def _integral_in_interval(q: np.ndarray, y: np.ndarray, lower: float, upper: float) -> float | None:
    """Integrate a sampled curve over a clipped interval using trapezoids."""

    if q.size < 2:
        return 0.0
    start = max(float(q[0]), float(lower))
    end = min(float(q[-1]), float(upper))
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        return 0.0
    inside = (q > start) & (q < end)
    q_interval = np.concatenate(([start], q[inside], [end]))
    y_interval = np.interp(q_interval, q, y)
    return _safe_trapezoid(y_interval, q_interval)


def _contribution_quantile(q: np.ndarray, integrand: np.ndarray, fraction: float) -> tuple[float | None, bool]:
    """Return a q value at a positive trapezoidal invariant contribution quantile."""

    if q.size < 2:
        return None, False
    with np.errstate(over="ignore", invalid="ignore"):
        interval = 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)
    if not np.all(np.isfinite(interval)):
        return None, True
    positive_interval = np.maximum(interval, 0.0)
    with np.errstate(over="ignore", invalid="ignore"):
        cumulative = np.concatenate(([0.0], np.cumsum(positive_interval)))
    total = float(cumulative[-1])
    if total <= 0.0 or not math.isfinite(total):
        return None, not math.isfinite(total)
    quantile = float(np.interp(float(fraction) * total, cumulative, q))
    return (quantile if math.isfinite(quantile) else None), not math.isfinite(quantile)


def detect_crossovers(
    q,
    intensity,
    *,
    min_segment_points: int = 12,
    min_slope_difference: float = 0.2,
) -> FeatureRows:
    """Detect large local changes in the log-log power-law slope.

    Each row describes a numerical slope transition.  It is not evidence of a
    unique structure or scattering mechanism.
    """

    min_segment_points = _finite_integer_parameter(min_segment_points, "min_segment_points", minimum=2)
    min_slope_difference = _finite_nonnegative_parameter(min_slope_difference, "min_slope_difference")

    q_valid, intensity_valid, filtered_count = _sorted_valid_arrays(
        q,
        intensity,
        positive_q=True,
        positive_intensity=True,
    )
    q_valid, intensity_valid, duplicate_count, collapsed_nonfinite_count = _collapse_duplicate_q(q_valid, intensity_valid)
    warnings: list[str] = []
    if filtered_count:
        warnings.append(f"Excluded {filtered_count} non-finite or non-positive q/I(q) rows for log-domain crossover detection.")
    if duplicate_count:
        warnings.append(f"Collapsed {duplicate_count} duplicate q rows by their mean intensity before crossover detection.")
    if collapsed_nonfinite_count:
        warnings.append(f"Excluded {collapsed_nonfinite_count} duplicate-q groups whose collapsed intensity was non-finite.")
    required_points = 2 * min_segment_points + 1
    if q_valid.size < required_points:
        warnings.insert(0, "Crossover detection needs at least " f"{required_points} finite positive q/I(q) points; received {int(q_valid.size)}.")
        return FeatureRows(warnings=warnings)

    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        log_q = np.log(q_valid)
        log_intensity = np.log(intensity_valid)
        local_alpha = -np.gradient(log_intensity, log_q)
        local_curvature = np.gradient(local_alpha, log_q)
    if not (np.all(np.isfinite(local_alpha)) and np.all(np.isfinite(local_curvature))):
        warnings.append("No finite local-slope transition was available after log-domain derivative calculation.")
        return FeatureRows(warnings=warnings)
    score = np.abs(local_curvature)
    candidate_mask = np.zeros(q_valid.size, dtype=bool)
    candidate_mask[min_segment_points : q_valid.size - min_segment_points] = True
    candidate_score = score.copy()
    candidate_score[~candidate_mask] = 0.0
    max_score = float(np.max(candidate_score))
    if not math.isfinite(max_score) or max_score <= 0.0:
        warnings.append("No finite local-slope transition was available for crossover detection.")
        return FeatureRows(warnings=warnings)

    peaks, _ = find_peaks(
        candidate_score,
        prominence=max_score * 0.1,
        distance=max(1, int(min_segment_points) // 2),
    )
    rows: list[dict] = []
    for index in peaks:
        if not candidate_mask[index]:
            continue
        left_alpha = float(np.median(local_alpha[index - min_segment_points : index]))
        right_alpha = float(np.median(local_alpha[index + 1 : index + min_segment_points + 1]))
        slope_difference = abs(right_alpha - left_alpha)
        if not all(math.isfinite(value) for value in (left_alpha, right_alpha, slope_difference)) or slope_difference < min_slope_difference:
            continue
        left_std = float(np.std(local_alpha[index - min_segment_points : index]))
        right_std = float(np.std(local_alpha[index + 1 : index + min_segment_points + 1]))
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            confidence = slope_difference / (slope_difference + left_std + right_std + 0.1)
        crossover_q = float(q_valid[index])
        crossover_d = _finite_positive_ratio(2.0 * math.pi, crossover_q)
        curvature = float(local_curvature[index])
        if not all(math.isfinite(value) for value in (left_std, right_std, confidence, curvature)):
            continue
        if crossover_d is None:
            warnings.append("crossover_d is unavailable because 2π/q overflowed or became non-finite.")
        rows.append(
            {
                "crossover_q": crossover_q,
                "crossover_d": crossover_d,
                "left_alpha": left_alpha,
                "right_alpha": right_alpha,
                "slope_difference": float(slope_difference),
                "confidence": float(np.clip(confidence, 0.0, 1.0)),
                "local_curvature": curvature,
            }
        )
    if not rows:
        warnings.append("No crossover met the requested local slope-difference threshold.")
    return FeatureRows(rows, warnings=warnings)


def extended_integrals(
    q,
    intensity,
    *,
    bands: tuple[float, float] | None = None,
) -> dict:
    """Calculate finite-range weighted integrals and invariant contribution quantiles.

    ``Q_low``, ``Q_mid``, and ``Q_high`` are finite-range integrals of
    ``q² I(q)`` over three q bands.  They should not be treated as extrapolated
    scattering invariants.
    """

    q_valid, intensity_valid, filtered_count = _sorted_valid_arrays(q, intensity, positive_q=False, positive_intensity=False)
    q_valid, intensity_valid, duplicate_count, collapsed_nonfinite_count = _collapse_duplicate_q(q_valid, intensity_valid)
    warnings: list[str] = []
    if filtered_count:
        warnings.append(f"Excluded {filtered_count} non-finite q/I(q) rows before integration.")
    if duplicate_count:
        warnings.append(f"Collapsed {duplicate_count} duplicate q rows by mean intensity before integration.")
    if collapsed_nonfinite_count:
        warnings.append(f"Excluded {collapsed_nonfinite_count} duplicate-q groups whose collapsed intensity was non-finite before integration.")
    if q_valid.size < 2:
        warnings.append("Extended integrals need at least two finite q/I(q) points.")
        return {
            "integral_I": None,
            "integral_qI": None,
            "integral_q2I": None,
            "integral_q4I": None,
            "Q_low": None,
            "Q_mid": None,
            "Q_high": None,
            "q10": None,
            "q50": None,
            "q90": None,
            "q_band_boundaries": None,
            "integration_points": int(q_valid.size),
            "warnings": warnings,
        }

    if bands is None:
        q_min = float(q_valid[0])
        q_max = float(q_valid[-1])
        # Weighted endpoint interpolation avoids overflowing ``q_max - q_min``
        # when both endpoints are finite but have opposite extreme signs.
        first_boundary = (2.0 * q_min / 3.0) + (q_max / 3.0)
        second_boundary = (q_min / 3.0) + (2.0 * q_max / 3.0)
    else:
        if len(bands) != 2:
            raise ValueError("bands must contain exactly two q boundaries.")
        first_boundary, second_boundary = (float(bands[0]), float(bands[1]))
        if not (math.isfinite(first_boundary) and math.isfinite(second_boundary) and first_boundary < second_boundary):
            raise ValueError("bands must be two finite, increasing q boundaries.")

    def _weighted_values(power: int) -> np.ndarray | None:
        with np.errstate(over="ignore", invalid="ignore"):
            values = q_valid**power * intensity_valid
        if not np.all(np.isfinite(values)):
            warnings.append(f"q^{power}I(q) contains non-finite values after multiplication; its weighted integral is unavailable.")
            return None
        return values

    def _safe_integral(values: np.ndarray | None, label: str) -> float | None:
        if values is None:
            return None
        integral = _safe_trapezoid(values, q_valid)
        if integral is None:
            warnings.append(f"{label} is unavailable because finite-range trapezoidal integration overflowed or became non-finite.")
            return None
        return integral

    q_i = _weighted_values(1)
    q2_i = _weighted_values(2)
    q4_i = _weighted_values(4)
    q_min = float(q_valid[0])
    q_max = float(q_valid[-1])
    q_low = _integral_in_interval(q_valid, q2_i, q_min, first_boundary) if q2_i is not None else None
    q_mid = _integral_in_interval(q_valid, q2_i, first_boundary, second_boundary) if q2_i is not None else None
    q_high = _integral_in_interval(q_valid, q2_i, second_boundary, q_max) if q2_i is not None else None
    if q2_i is not None:
        for label, value in (("Q_low", q_low), ("Q_mid", q_mid), ("Q_high", q_high)):
            if value is None:
                warnings.append(f"{label} is unavailable because its finite-range trapezoidal integration overflowed or became non-finite.")
    quantile_q = q_valid[q_valid > 0.0]
    quantile_integrand = None
    if q2_i is not None:
        quantile_integrand = q2_i[q_valid > 0.0]
    q10 = q50 = q90 = None
    quantile_overflow = False
    if quantile_integrand is not None:
        q10, q10_overflow = _contribution_quantile(quantile_q, quantile_integrand, 0.10)
        q50, q50_overflow = _contribution_quantile(quantile_q, quantile_integrand, 0.50)
        q90, q90_overflow = _contribution_quantile(quantile_q, quantile_integrand, 0.90)
        quantile_overflow = q10_overflow or q50_overflow or q90_overflow
    if quantile_overflow:
        warnings.append("q10, q50, and q90 are unavailable because the q²I(q) trapezoidal contribution reduction overflowed or became non-finite.")
    if q10 is None:
        warnings.append("No positive q²I(q) contribution was available for q10, q50, and q90.")

    return {
        "integral_I": _safe_integral(intensity_valid, "integral_I"),
        "integral_qI": _safe_integral(q_i, "integral_qI"),
        "integral_q2I": _safe_integral(q2_i, "integral_q2I"),
        "integral_q4I": _safe_integral(q4_i, "integral_q4I"),
        "Q_low": q_low,
        "Q_mid": q_mid,
        "Q_high": q_high,
        "q10": q10,
        "q50": q50,
        "q90": q90,
        "q_band_boundaries": {"low_mid": first_boundary, "mid_high": second_boundary},
        "integration_points": int(q_valid.size),
        "warnings": warnings,
    }


def detect_shoulders(
    q,
    intensity,
    *,
    min_segment_points: int = 12,
    min_curvature: float = 0.15,
) -> FeatureRows:
    """Detect smooth local curvature extrema in a log-log curve.

    A shoulder is reported as a descriptive curvature feature.  It can arise
    from several experimental or mathematical causes and is not a structural
    assignment.
    """

    min_segment_points = _finite_integer_parameter(min_segment_points, "min_segment_points", minimum=2)
    min_curvature = _finite_nonnegative_parameter(min_curvature, "min_curvature")

    q_valid, intensity_valid, filtered_count = _sorted_valid_arrays(
        q,
        intensity,
        positive_q=True,
        positive_intensity=True,
    )
    q_valid, intensity_valid, duplicate_count, collapsed_nonfinite_count = _collapse_duplicate_q(q_valid, intensity_valid)
    warnings: list[str] = []
    if filtered_count:
        warnings.append(f"Excluded {filtered_count} non-finite or non-positive q/I(q) rows for log-domain shoulder detection.")
    if duplicate_count:
        warnings.append(f"Collapsed {duplicate_count} duplicate q rows by their mean intensity before shoulder detection.")
    if collapsed_nonfinite_count:
        warnings.append(f"Excluded {collapsed_nonfinite_count} duplicate-q groups whose collapsed intensity was non-finite.")
    required_points = 2 * min_segment_points + 1
    if q_valid.size < required_points:
        warnings.insert(0, "Shoulder detection needs at least " f"{required_points} finite positive q/I(q) points; received {int(q_valid.size)}.")
        return FeatureRows(warnings=warnings)

    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        log_q = np.log(q_valid)
        local_alpha = -np.gradient(np.log(intensity_valid), log_q)
        local_curvature = np.gradient(local_alpha, log_q)
    if not (np.all(np.isfinite(local_alpha)) and np.all(np.isfinite(local_curvature))):
        warnings.append("No finite local curvature extremum was available after log-domain derivative calculation.")
        return FeatureRows(warnings=warnings)
    score = np.abs(local_curvature)
    candidate_mask = np.zeros(q_valid.size, dtype=bool)
    candidate_mask[min_segment_points : q_valid.size - min_segment_points] = True
    candidate_score = score.copy()
    candidate_score[~candidate_mask] = 0.0
    max_score = float(np.max(candidate_score))
    if not math.isfinite(max_score) or max_score < min_curvature:
        warnings.append("No local curvature extremum met the requested shoulder threshold.")
        return FeatureRows(warnings=warnings)

    prominence_threshold = max(max_score * 0.1, min_curvature * 0.1)
    min_peak_distance_points = max(1, min_segment_points // 2)
    indices, properties = find_peaks(
        candidate_score,
        prominence=prominence_threshold,
        distance=min_peak_distance_points,
    )
    rows: list[dict] = []
    rejected_nonfinite_prominence = 0
    prominence_values = properties.get("prominences", np.full(indices.size, np.nan))
    for row_index, index in enumerate(indices):
        if not candidate_mask[index] or score[index] < min_curvature:
            continue
        candidate_prominence = float(prominence_values[row_index])
        if not math.isfinite(candidate_prominence):
            rejected_nonfinite_prominence += 1
            continue
        left_alpha = float(np.median(local_alpha[index - min_segment_points : index]))
        right_alpha = float(np.median(local_alpha[index + 1 : index + min_segment_points + 1]))
        local_noise = float(
            np.std(local_alpha[index - min_segment_points : index])
            + np.std(local_alpha[index + 1 : index + min_segment_points + 1])
        )
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            confidence = float(score[index] / (score[index] + local_noise + min_curvature))
        shoulder_q = float(q_valid[index])
        local_alpha_value = float(local_alpha[index])
        curvature = float(local_curvature[index])
        slope_difference = float(abs(right_alpha - left_alpha))
        shoulder_d = _finite_positive_ratio(2.0 * math.pi, shoulder_q)
        if not all(
            math.isfinite(value)
            for value in (local_alpha_value, curvature, left_alpha, right_alpha, local_noise, slope_difference, confidence)
        ):
            rejected_nonfinite_prominence += 1
            continue
        derived_value_unavailable = shoulder_d is None
        rows.append(
            {
                "shoulder_q": shoulder_q,
                "shoulder_d": shoulder_d,
                "local_alpha": local_alpha_value,
                "curvature": curvature,
                "left_alpha": left_alpha,
                "right_alpha": right_alpha,
                "slope_difference": slope_difference,
                "confidence": float(np.clip(confidence, 0.0, 1.0)),
                "prominence": candidate_prominence,
                "candidate_type": "numerical_shoulder_candidate",
                "edge_truncated": False,
                "completeness_status": "derived_value_unavailable" if derived_value_unavailable else "complete",
                "valid": not derived_value_unavailable,
                "validity_reason": "shoulder_d_overflowed_or_unavailable" if derived_value_unavailable else None,
                "provenance": {
                    "signal": "absolute_local_loglog_curvature",
                    "min_segment_points": min_segment_points,
                    "min_curvature": min_curvature,
                    "find_peaks_prominence_threshold": float(prominence_threshold),
                    "min_peak_distance_points": min_peak_distance_points,
                    "candidate_score": float(score[index]),
                    "max_candidate_score": max_score,
                    "duplicate_q_strategy": "mean_collapsed_before_gradient",
                },
            }
        )
    if rejected_nonfinite_prominence:
        warnings.append(f"Rejected {rejected_nonfinite_prominence} shoulder candidates with non-finite prominence.")
    if not rows:
        warnings.append("No shoulder met the requested curvature threshold.")
    return FeatureRows(rows, warnings=warnings)


def analyze_oscillations(
    q,
    intensity,
    *,
    min_points: int = 12,
    prominence: float | None = None,
) -> dict:
    """Describe extrema in the log-intensity residual after a linear log-q trend.

    The returned peaks and troughs are numerical extrema, not assignments of a
    particular particle form factor or interparticle correlation.
    """

    min_points = _finite_integer_parameter(min_points, "min_points", minimum=3)
    q_valid, intensity_valid, filtered_count = _sorted_valid_arrays(
        q,
        intensity,
        positive_q=True,
        positive_intensity=True,
    )
    q_valid, intensity_valid, duplicate_count, collapsed_nonfinite_count = _collapse_duplicate_q(q_valid, intensity_valid)
    warnings: list[str] = []
    if filtered_count:
        warnings.append(f"Excluded {filtered_count} non-finite or non-positive q/I(q) rows for log-domain oscillation analysis.")
    if duplicate_count:
        warnings.append(f"Collapsed {duplicate_count} duplicate q rows by their mean intensity before oscillation analysis.")
    if collapsed_nonfinite_count:
        warnings.append(f"Excluded {collapsed_nonfinite_count} duplicate-q groups whose collapsed intensity was non-finite.")
    if q_valid.size < min_points:
        warnings.append(
            f"Oscillation analysis needs at least {int(min_points)} finite positive q/I(q) points; received {int(q_valid.size)}."
        )
        return {
            "peaks": [],
            "troughs": [],
            "oscillations": [],
            "oscillation_count": 0,
            "mean_peak_spacing": None,
            "mean_log_q_spacing": None,
            "point_count": int(q_valid.size),
            "warnings": warnings,
        }

    try:
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            log_q = np.log(q_valid)
            log_intensity = np.log(intensity_valid)
            trend = np.polyval(np.polyfit(log_q, log_intensity, deg=1), log_q)
            residual = log_intensity - trend
            local_alpha = -np.gradient(log_intensity, log_q)
            local_curvature = np.gradient(local_alpha, log_q)
    except (np.linalg.LinAlgError, ValueError):
        warnings.append("Oscillation analysis is unavailable because the log-domain detrend could not be computed safely.")
        return {
            "peaks": [], "troughs": [], "oscillations": [], "oscillation_count": 0,
            "mean_peak_spacing": None, "mean_log_q_spacing": None, "point_count": int(q_valid.size),
            "warnings": warnings,
        }
    if not all(np.all(np.isfinite(values)) for values in (residual, local_alpha, local_curvature)):
        warnings.append("Oscillation analysis is unavailable because detrended residuals or derivatives became non-finite.")
        return {
            "peaks": [], "troughs": [], "oscillations": [], "oscillation_count": 0,
            "mean_peak_spacing": None, "mean_log_q_spacing": None, "point_count": int(q_valid.size),
            "warnings": warnings,
        }
    residual_span = float(np.ptp(residual))
    if prominence is not None:
        prominence_threshold = _finite_nonnegative_parameter(prominence, "prominence")
    else:
        prominence_threshold = max(1e-10, residual_span * 0.1)
    if not math.isfinite(prominence_threshold):
        warnings.append("Oscillation analysis is unavailable because the data-derived prominence threshold was non-finite.")
        return {
            "peaks": [], "troughs": [], "oscillations": [], "oscillation_count": 0,
            "mean_peak_spacing": None, "mean_log_q_spacing": None, "point_count": int(q_valid.size),
            "warnings": warnings,
        }
    min_peak_distance_points = max(1, min_points // 4)
    peak_indices, peak_properties = find_peaks(
        residual,
        prominence=(prominence_threshold, None),
        distance=min_peak_distance_points,
    )
    trough_indices, trough_properties = find_peaks(
        -residual,
        prominence=(prominence_threshold, None),
        distance=min_peak_distance_points,
    )

    def _rows(indices: np.ndarray, properties: dict, *, kind: str) -> tuple[list[dict], int]:
        values = properties.get("prominences", np.full(indices.size, np.nan))
        left_bases = properties.get("left_bases", np.full(indices.size, -1, dtype=int))
        right_bases = properties.get("right_bases", np.full(indices.size, -1, dtype=int))
        rows: list[dict] = []
        rejected_nonfinite_prominence = 0
        for row_index, index in enumerate(indices):
            candidate_prominence = float(values[row_index])
            if not math.isfinite(candidate_prominence):
                rejected_nonfinite_prominence += 1
                continue
            feature_q = float(q_valid[index])
            residual_value = float(residual[index])
            alpha_value = float(local_alpha[index])
            curvature_value = float(local_curvature[index])
            if not all(math.isfinite(value) for value in (feature_q, residual_value, alpha_value, curvature_value)):
                rejected_nonfinite_prominence += 1
                continue
            left_base_index = int(left_bases[row_index])
            right_base_index = int(right_bases[row_index])
            base_indices_valid = 0 <= left_base_index < q_valid.size and 0 <= right_base_index < q_valid.size
            left_base_q = float(q_valid[left_base_index]) if base_indices_valid else None
            right_base_q = float(q_valid[right_base_index]) if base_indices_valid else None
            left_base_residual = float(residual[left_base_index]) if base_indices_valid else None
            right_base_residual = float(residual[right_base_index]) if base_indices_valid else None
            edge_truncated = bool(
                not base_indices_valid
                or index == 0
                or index == q_valid.size - 1
                or left_base_index == 0
                or right_base_index == q_valid.size - 1
            )
            d_value = _finite_positive_ratio(2.0 * math.pi, feature_q)
            derived_value_unavailable = d_value is None
            if edge_truncated:
                completeness_status = "edge_truncated"
                valid = False
                validity_reason = "prominence_contour_support_touches_selected_q_range_edge"
            elif derived_value_unavailable:
                completeness_status = "derived_value_unavailable"
                valid = False
                validity_reason = "oscillation_d_overflowed_or_unavailable"
            else:
                completeness_status = "complete"
                valid = True
                validity_reason = None
            rows.append(
                {
                    "kind": kind,
                    "q": feature_q,
                    "d": d_value,
                    "residual": residual_value,
                    "prominence": candidate_prominence,
                    "local_alpha": alpha_value,
                    "local_curvature": curvature_value,
                    "candidate_type": f"numerical_oscillation_{kind}_candidate",
                    "edge_truncated": edge_truncated,
                    "completeness_status": completeness_status,
                    "valid": valid,
                    "validity_reason": validity_reason,
                    "provenance": {
                        "signal": "detrended_lnI_residual",
                        "detrend": "least_squares_linear_lnI_vs_lnq",
                        "prominence_threshold": float(prominence_threshold),
                        "min_peak_distance_points": int(min_peak_distance_points),
                        "spacing_strategy": "find_peaks_minimum_index_distance",
                        "baseline_method": "scipy_prominence_contour_on_detrended_residual",
                        "left_base_index": left_base_index if base_indices_valid else None,
                        "right_base_index": right_base_index if base_indices_valid else None,
                        "left_base_q": left_base_q,
                        "right_base_q": right_base_q,
                        "left_base_residual": left_base_residual,
                        "right_base_residual": right_base_residual,
                        "duplicate_q_strategy": "mean_collapsed_before_log_domain_derivatives",
                    },
                }
            )
        return rows, rejected_nonfinite_prominence

    peaks, rejected_peak_prominence = _rows(peak_indices, peak_properties, kind="peak")
    troughs, rejected_trough_prominence = _rows(trough_indices, trough_properties, kind="trough")
    extrema = sorted([*peaks, *troughs], key=lambda row: row["q"])
    peak_q = np.asarray([row["q"] for row in peaks], dtype=float)
    peak_log_q = np.log(peak_q) if peak_q.size else np.array([], dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        mean_peak_spacing = _finite_mean(np.diff(peak_q)) if peak_q.size >= 2 else None
        mean_log_q_spacing = _finite_mean(np.diff(peak_log_q)) if peak_log_q.size >= 2 else None
    if peak_q.size >= 2 and (mean_peak_spacing is None or mean_log_q_spacing is None):
        warnings.append("Oscillation peak spacing is unavailable because its finite-value reduction overflowed or became non-finite.")
    if not peaks and not troughs:
        warnings.append("No residual extrema met the requested oscillation prominence threshold.")
    rejected_prominence = rejected_peak_prominence + rejected_trough_prominence
    if rejected_prominence:
        warnings.append(f"Rejected {rejected_prominence} oscillation candidates with non-finite prominence.")
    return {
        "peaks": peaks,
        "troughs": troughs,
        "oscillations": extrema,
        "oscillation_count": int(min(len(peaks), len(troughs))),
        "mean_peak_spacing": mean_peak_spacing,
        "mean_log_q_spacing": mean_log_q_spacing,
        "point_count": int(q_valid.size),
        "min_peak_distance_points": int(min_peak_distance_points),
        "spacing_strategy": "find_peaks_minimum_index_distance",
        "prominence_threshold": float(prominence_threshold),
        "residual": residual.tolist(),
        "local_alpha": local_alpha.tolist(),
        "local_curvature": local_curvature.tolist(),
        "warnings": warnings,
    }


def normalized_shape_distance(
    q,
    intensity,
    reference_q=None,
    reference_intensity=None,
    *,
    min_points: int = 8,
    grid_points: int | None = None,
) -> dict:
    """Compare two log-domain curve shapes after removing intensity offsets.

    When only three positional arrays are supplied, the third array is treated
    as the reference intensity sampled on the same q grid.  With four arrays,
    the two curves may have different q grids.  The metric is an RMS distance
    between mean-centred log-intensity curves on their shared q range.
    """

    min_points = _finite_integer_parameter(min_points, "min_points", minimum=2)
    if reference_intensity is None:
        if reference_q is None:
            raise ValueError("A reference intensity array is required.")
        reference_intensity = reference_q
        reference_q = q
    q_a, intensity_a, filtered_a = _sorted_valid_arrays(q, intensity, positive_q=True, positive_intensity=True)
    q_b, intensity_b, filtered_b = _sorted_valid_arrays(
        reference_q,
        reference_intensity,
        positive_q=True,
        positive_intensity=True,
    )
    q_a, intensity_a, duplicate_a, collapsed_nonfinite_a = _collapse_duplicate_q(q_a, intensity_a)
    q_b, intensity_b, duplicate_b, collapsed_nonfinite_b = _collapse_duplicate_q(q_b, intensity_b)
    warnings: list[str] = []
    if filtered_a or filtered_b:
        warnings.append(
            "Excluded "
            f"{filtered_a + filtered_b} non-finite or non-positive q/I(q) rows for log-domain shape comparison."
        )
    if duplicate_a or duplicate_b:
        warnings.append(
            "Collapsed "
            f"{duplicate_a + duplicate_b} duplicate q rows by their mean intensity before shape comparison."
        )
    if collapsed_nonfinite_a or collapsed_nonfinite_b:
        warnings.append(
            "Excluded "
            f"{collapsed_nonfinite_a + collapsed_nonfinite_b} duplicate-q groups whose collapsed intensity was non-finite before shape comparison."
        )
    if q_a.size < min_points or q_b.size < min_points:
        warnings.append(
            f"Normalized shape distance needs at least {int(min_points)} valid points in each curve."
        )
        return {
            "normalized_shape_distance": None,
            "distance": None,
            "valid": False,
            "comparison_points": 0,
            "overlap_q_range": None,
            "normalization": "mean_centered_log_intensity_rms",
            "normalization_scale": None,
            "warnings": warnings,
        }

    overlap_min = max(float(q_a[0]), float(q_b[0]))
    overlap_max = min(float(q_a[-1]), float(q_b[-1]))
    if overlap_max <= overlap_min:
        warnings.append("The two curves have no overlapping positive q range for shape comparison.")
        return {
            "normalized_shape_distance": None,
            "distance": None,
            "valid": False,
            "comparison_points": 0,
            "overlap_q_range": None,
            "normalization": "mean_centered_log_intensity_rms",
            "normalization_scale": None,
            "warnings": warnings,
        }

    default_grid_points = min(300, max(min_points, min(q_a.size, q_b.size)))
    comparison_points = _finite_integer_parameter(grid_points, "grid_points", minimum=min_points) if grid_points is not None else int(default_grid_points)
    if comparison_points < min_points:
        raise ValueError("grid_points must be at least min_points when supplied.")
    common_q = np.geomspace(overlap_min, overlap_max, comparison_points)
    log_common_q = np.log(common_q)
    log_a = np.interp(log_common_q, np.log(q_a), np.log(intensity_a))
    log_b = np.interp(log_common_q, np.log(q_b), np.log(intensity_b))
    normalized_a = log_a - float(np.mean(log_a))
    normalized_b = log_b - float(np.mean(log_b))
    normalization_scale = float(
        np.sqrt(0.5 * (np.mean(normalized_a**2) + np.mean(normalized_b**2)))
    )
    scale_tolerance = 1e-12 * max(1.0, float(np.max(np.abs(log_a))), float(np.max(np.abs(log_b))))
    if not math.isfinite(normalization_scale) or normalization_scale <= scale_tolerance:
        warnings.append("Normalized shape distance is unavailable because the mean-centred log-intensity normalization scale is zero or non-finite.")
        return {
            "normalized_shape_distance": None,
            "distance": None,
            "valid": False,
            "comparison_points": comparison_points,
            "overlap_q_range": (overlap_min, overlap_max),
            "normalization": "mean_centered_log_intensity_rms",
            "normalization_scale": None,
            "warnings": warnings,
        }
    distance = float(np.sqrt(np.mean((normalized_a - normalized_b) ** 2)) / normalization_scale)
    return {
        "normalized_shape_distance": distance,
        "distance": distance,
        "valid": True,
        "comparison_points": comparison_points,
        "overlap_q_range": (overlap_min, overlap_max),
        "normalization": "mean_centered_log_intensity_rms",
        "normalization_scale": normalization_scale,
        "warnings": warnings,
    }
