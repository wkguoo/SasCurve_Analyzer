from __future__ import annotations

import math

import numpy as np
from scipy.signal import find_peaks, peak_widths

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import AnalysisResult, CurveData
from app.core.fit_diagnostics import build_residual_rows, fit_diagnostics, parameter_records
from app.core.fitting import linear_fit
from app.core.method_warnings import guinier_warnings, invariant_warnings, porod_plateau_warnings, power_law_warnings, warning_to_dict, warning_to_text
from app.core.uncertainty import log_intensity_sigma


def _range_mask(curve: CurveData, q_range: tuple[float, float]) -> np.ndarray:
    q_min, q_max = q_range
    if q_min > q_max:
        raise ValueError("q_min must be less than or equal to q_max.")
    return np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q >= q_min) & (curve.q <= q_max)


def _valid_log_mask(curve: CurveData, q_range: tuple[float, float], *, require_q_positive: bool = True) -> tuple[np.ndarray, list[str]]:
    mask = _range_mask(curve, q_range)
    warnings: list[str] = []
    invalid_i = mask & (curve.intensity <= 0)
    if np.any(invalid_i):
        warnings.append(f"Excluded {int(np.sum(invalid_i))} points with I(q) <= 0.")
    mask &= curve.intensity > 0
    if require_q_positive:
        invalid_q = mask & (curve.q <= 0)
        if np.any(invalid_q):
            warnings.append(f"Excluded {int(np.sum(invalid_q))} points with q <= 0.")
        mask &= curve.q > 0
    return mask, warnings


def _create_result_with_method_warnings(
    *,
    curve: CurveData,
    analysis_type: str,
    q_range: tuple[float, float],
    parameters: dict | None = None,
    results: dict | None = None,
    warnings: list[str] | None = None,
    method_warnings=None,
) -> AnalysisResult:
    structured = [warning_to_dict(warning) for warning in method_warnings or []]
    text_warnings = list(warnings or [])
    text_warnings.extend(warning_to_text(warning) for warning in method_warnings or [])
    return AnalysisResult.create(
        curve=curve,
        analysis_type=analysis_type,
        q_range=q_range,
        parameters=parameters,
        results=results,
        warnings=text_warnings,
        structured_warnings=structured,
    )


def _native_float(value) -> float | None:
    """Return a finite built-in float, or ``None`` for an unavailable scalar."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _native_int(value) -> int | None:
    number = _native_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _safe_exp(value) -> float | None:
    number = _native_float(value)
    if number is None:
        return None
    try:
        return _native_float(math.exp(number))
    except OverflowError:
        return None


def _finite_porod_statistics(values: np.ndarray) -> dict:
    """Return finite q⁴I statistics, withholding unsafe floating-point reductions."""

    empty = {
        "mean": None,
        "std": None,
        "cv": None,
        "min": None,
        "max": None,
        "median": None,
        "range": None,
        "reduction_reason": None,
    }
    if not values.size:
        return empty
    if not np.all(np.isfinite(values)):
        return {**empty, "reduction_reason": "non_finite_input_values"}

    minimum = _native_float(np.min(values))
    maximum = _native_float(np.max(values))
    median = _native_float(np.median(values))
    scale = _native_float(np.max(np.abs(values)))
    if scale is None:
        return {**empty, "min": minimum, "max": maximum, "median": median, "reduction_reason": "non_finite_scaling_value"}
    if scale > math.sqrt(np.finfo(float).max):
        return {
            **empty,
            "min": minimum,
            "max": maximum,
            "median": median,
            "reduction_reason": "finite_values_exceed_safe_statistical_reduction_range",
        }
    if scale == 0.0:
        return {"mean": 0.0, "std": 0.0, "cv": None, "min": minimum, "max": maximum, "median": median, "range": 0.0, "reduction_reason": None}

    with np.errstate(over="ignore", invalid="ignore"):
        scaled = values / scale
        mean = _native_float(scale * np.mean(scaled))
        std = _native_float(scale * np.std(scaled))
        value_range = _native_float(maximum - minimum) if minimum is not None and maximum is not None else None
    if mean is None or std is None or value_range is None:
        return {
            **empty,
            "min": minimum,
            "max": maximum,
            "median": median,
            "reduction_reason": "statistical_reduction_overflowed_or_became_non_finite",
        }
    cv = _native_float(std / abs(mean)) if mean != 0.0 else None
    reason = None if mean == 0.0 or cv is not None else "relative_variation_overflowed_or_became_non_finite"
    return {
        "mean": mean,
        "std": std,
        "cv": cv,
        "min": minimum,
        "max": maximum,
        "median": median,
        "range": value_range,
        "reduction_reason": reason,
    }


def _safe_group_mean(values: np.ndarray) -> float | None:
    """Average finite repeated values without overflowing an intermediate sum."""

    if not values.size or not np.all(np.isfinite(values)):
        return None
    scale = _native_float(np.max(np.abs(values)))
    if scale is None:
        return None
    if scale == 0.0:
        return 0.0
    with np.errstate(over="ignore", invalid="ignore"):
        mean = scale * np.mean(values / scale)
    return _native_float(mean)


def _safe_trapezoid(values: np.ndarray, coordinates: np.ndarray) -> float | None:
    """Return a finite trapezoid reduction, withholding overflowed areas."""

    if values.size < 2 or coordinates.size < 2:
        return 0.0
    if not (np.all(np.isfinite(values)) and np.all(np.isfinite(coordinates))):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        integral = np.trapezoid(values, coordinates)
    return _native_float(integral)


def _safe_positive_ratio(numerator: float, denominator: float) -> float | None:
    """Return a finite positive quotient, or ``None`` for an unsafe derivative."""

    if denominator <= 0.0:
        return None
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        quotient = numerator / denominator
    value = _native_float(quotient)
    return value if value is not None and value > 0.0 else None


def _selected_error_array(curve: CurveData) -> tuple[np.ndarray | None, str | None]:
    """Return an error array only when it aligns with the curve point rows."""

    if curve.error is None:
        return None, "error_not_provided"
    try:
        error = np.asarray(curve.error, dtype=float)
    except (TypeError, ValueError):
        return None, "error_not_numeric"
    if error.shape != curve.q.shape:
        return None, "error_length_mismatch"
    return error, None


def _excluded_row(
    *,
    original_index: int,
    q: float | None,
    intensity: float | None,
    error: float | None,
    reasons: list[str],
) -> dict:
    """Build a JSON-safe record for one raw point excluded from a log fit."""

    return {
        "original_index": int(original_index),
        "q": q,
        "intensity": intensity,
        "error": error,
        "reason": "; ".join(reasons),
        "reasons": list(reasons),
        "included_in_fit": False,
    }


def _prepare_log_fit_selection(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    require_q_positive: bool = True,
    use_error_for_weighting: bool = True,
) -> tuple[dict, list[str]]:
    """Select a log-domain fit interval without silently dropping raw rows.

    Error values are treated differently from ``q`` and ``I`` domains.  For a
    linear fit, a missing or partly invalid error column disables weighting for
    the whole fit, preserving all otherwise valid q/I points for an unweighted
    fit.  For a derivative-only method, callers can set
    ``use_error_for_weighting=False`` so the audit records that errors are not
    used and no fictitious OLS/weighting message is emitted.
    """

    q_min, q_max = (_native_float(q_range[0]), _native_float(q_range[1]))
    if q_min is None or q_max is None:
        raise ValueError("q_range values must be finite.")
    if q_min > q_max:
        raise ValueError("q_min must be less than or equal to q_max.")

    q_values = np.asarray(curve.q, dtype=float)
    intensity_values = np.asarray(curve.intensity, dtype=float)
    if q_values.shape != intensity_values.shape:
        raise ValueError("curve.q and curve.intensity must have matching shapes.")
    error_values, error_issue = _selected_error_array(curve)

    selected_indices: list[int] = []
    selected_q: list[float] = []
    selected_intensity: list[float] = []
    selected_error: list[float | None] = []
    excluded_rows: list[dict] = []
    warnings: list[str] = []
    non_positive_i_count = 0
    non_positive_q_count = 0
    non_finite_q_count = 0
    non_finite_i_count = 0
    outside_range_count = 0

    for index in range(q_values.size):
        q_value = _native_float(q_values[index])
        intensity_value = _native_float(intensity_values[index])
        error_value = None if error_values is None else _native_float(error_values[index])
        reasons: list[str] = []
        if q_value is None:
            reasons.append("non_finite_q")
            non_finite_q_count += 1
        else:
            if q_value < q_min or q_value > q_max:
                reasons.append("outside_selected_q_range")
                outside_range_count += 1
            if require_q_positive and q_value <= 0.0:
                reasons.append("non_positive_q")
                non_positive_q_count += 1
        if intensity_value is None:
            reasons.append("non_finite_intensity")
            non_finite_i_count += 1
        elif intensity_value <= 0.0:
            reasons.append("non_positive_intensity")
            non_positive_i_count += 1

        if reasons:
            excluded_rows.append(
                _excluded_row(
                    original_index=index,
                    q=q_value,
                    intensity=intensity_value,
                    error=error_value,
                    reasons=reasons,
                )
            )
            continue

        selected_indices.append(index)
        selected_q.append(q_value)
        selected_intensity.append(intensity_value)
        selected_error.append(error_value)

    if non_positive_i_count:
        warnings.append(f"Excluded {non_positive_i_count} points with I(q) <= 0.")
    if non_positive_q_count:
        warnings.append(f"Excluded {non_positive_q_count} points with q <= 0.")
    if non_finite_q_count:
        warnings.append(f"Excluded {non_finite_q_count} points with non-finite q.")
    if non_finite_i_count:
        warnings.append(f"Excluded {non_finite_i_count} points with non-finite I(q).")
    if outside_range_count:
        warnings.append(f"Excluded {outside_range_count} points outside the selected q range.")

    q = np.asarray(selected_q, dtype=float)
    intensity = np.asarray(selected_intensity, dtype=float)
    indices = np.asarray(selected_indices, dtype=int)
    errors = None if error_values is None else np.asarray(selected_error, dtype=float)
    transformed_sigma = None
    weighted_fit = False
    error_audit = {
        "error_column_provided": curve.error is not None,
        "error_column_status": error_issue or "available",
        "error_column_length_matched": error_issue != "error_length_mismatch",
        "strategy": "fit_weighting" if use_error_for_weighting else "not_used_for_local_derivative",
        "propagation": "sigma_lnI = error / I" if use_error_for_weighting else None,
        "eligible_qI_points": int(indices.size),
        "valid_transformed_sigma_points": 0 if use_error_for_weighting else None,
        "invalid_transformed_sigma_points": 0 if use_error_for_weighting else None,
        "invalid_transformed_sigma_original_indices": [],
        "weighting_policy": (
            "weighted_only_when_all_selected_log_domain_errors_are_positive_and_finite"
            if use_error_for_weighting
            else "not_applicable_for_local_derivative"
        ),
        "weighting_decision": "unweighted" if use_error_for_weighting else "not_applicable",
    }
    if not use_error_for_weighting:
        error_audit["fit_performed"] = None
    elif error_values is None:
        if error_issue == "error_not_provided":
            warnings.append("No error column found; ordinary least squares was used.")
        else:
            warnings.append(f"Error column could not be used ({error_issue}); ordinary least squares was used.")
    elif indices.size:
        propagated = log_intensity_sigma(intensity, errors)
        valid_sigma = np.isfinite(propagated) & (propagated > 0.0)
        invalid_indices = indices[~valid_sigma]
        error_audit.update(
            {
                "valid_transformed_sigma_points": int(np.count_nonzero(valid_sigma)),
                "invalid_transformed_sigma_points": int(np.count_nonzero(~valid_sigma)),
                "invalid_transformed_sigma_original_indices": [int(index) for index in invalid_indices],
            }
        )
        if np.all(valid_sigma):
            transformed_sigma = propagated
            weighted_fit = True
            error_audit["weighting_decision"] = "weighted_all_selected_errors_valid"
        else:
            error_audit["weighting_decision"] = "unweighted_partial_or_invalid_transformed_sigma"
            warnings.append(
                "Error column is incomplete or invalid after log transformation; ordinary least squares was used for all log-valid points.")
    elif error_values is not None:
        error_audit["weighting_decision"] = "unweighted_no_log_valid_points"

    return {
        "indices": indices,
        "q": q,
        "intensity": intensity,
        "error": errors,
        "sigma": transformed_sigma,
        "weighted_fit": weighted_fit,
        "excluded_rows": excluded_rows,
        "error_audit": error_audit,
        "q_range": (q_min, q_max),
    }, warnings


def _linear_fit_with_uncertainty(x: np.ndarray, y: np.ndarray, sigma: np.ndarray | None) -> dict | None:
    """Fit a two-parameter line and retain finite covariance-derived errors."""

    if x.size < 2 or np.unique(x).size < 2:
        return None
    try:
        fit = linear_fit(x, y, sigma=sigma)
    except (ValueError, np.linalg.LinAlgError):
        return None

    covariance: list[list[float | None]] | None = None
    slope_stderr = None
    intercept_stderr = None
    if x.size > 2:
        try:
            if sigma is None:
                _coefficients, covariance_array = np.polyfit(x, y, 1, cov=True)
            else:
                _coefficients, covariance_array = np.polyfit(x, y, 1, w=1.0 / sigma, cov="unscaled")
            diagonal = np.sqrt(np.diag(covariance_array))
            slope_stderr = _native_float(diagonal[0])
            intercept_stderr = _native_float(diagonal[1])
            covariance = [[_native_float(value) for value in row] for row in covariance_array]
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            covariance = None
    return {
        "slope": _native_float(fit["slope"]),
        "intercept": _native_float(fit["intercept"]),
        "fitted": np.asarray(fit["fitted"], dtype=float),
        "slope_stderr": slope_stderr,
        "intercept_stderr": intercept_stderr,
        "covariance": covariance,
    }


def _fit_not_performed_rows(
    *,
    indices: np.ndarray,
    q: np.ndarray,
    intensity: np.ndarray,
    error: np.ndarray | None,
) -> list[dict]:
    """Preserve eligible raw rows when a requested line cannot be fit."""

    rows: list[dict] = []
    for position in range(indices.size):
        rows.append(
            {
                "original_index": int(indices[position]),
                "q": _native_float(q[position]),
                "intensity": _native_float(intensity[position]),
                "error": None if error is None else _native_float(error[position]),
                "reason": "fit_not_performed",
                "included_in_fit": False,
            }
        )
    return rows


def _enrich_residual_rows(
    *,
    indices: np.ndarray,
    q: np.ndarray,
    intensity: np.ndarray,
    error: np.ndarray | None,
    observed: np.ndarray,
    fitted: np.ndarray,
    sigma: np.ndarray | None,
    transformed_x: np.ndarray,
    coordinate: str,
) -> list[dict]:
    """Attach raw-row provenance to residual records for actual fit points only."""

    rows = build_residual_rows(q, observed, fitted, sigma=sigma)
    for position, row in enumerate(rows):
        row.update(
            {
                "original_index": int(indices[position]),
                "intensity": _native_float(intensity[position]),
                "error": None if error is None else _native_float(error[position]),
                "transformed_x": _native_float(transformed_x[position]),
                "fit_coordinate": coordinate,
            }
        )
    return rows


def _finalize_result_warnings(result: AnalysisResult) -> AnalysisResult:
    """Expose the complete warning list inside the traceable result payload."""

    result.results["warnings"] = list(result.warnings)
    result.results["warning"] = list(result.warnings)
    return result


def _guinier_slope_unit(q_unit: str) -> str:
    replacements = {"A^-1": "A^2", "Å^-1": "Å^2", "nm^-1": "nm^2"}
    return replacements.get(q_unit, f"({q_unit})^-2")


def guinier_analysis(curve: CurveData, q_range: tuple[float, float], *, min_points: int = 5) -> AnalysisResult:
    """Fit ``ln I(q) = ln I(0) - Rg²q² / 3`` with full audit provenance."""

    selection, warnings = _prepare_log_fit_selection(curve, q_range, require_q_positive=True)
    q = selection["q"]
    intensity = selection["intensity"]
    indices = selection["indices"]
    errors = selection["error"]
    sigma = selection["sigma"]
    n = int(q.size)
    if n < min_points:
        warnings.append(f"Too few points for Guinier analysis: {n} < {min_points}.")

    x = q**2
    y = np.log(intensity) if n else np.array([], dtype=float)
    fit = _linear_fit_with_uncertainty(x, y, sigma) if n >= 2 else None
    actual_fit_points = n if fit is not None else 0
    fit_not_performed_rows = [] if fit is not None else _fit_not_performed_rows(
        indices=indices,
        q=q,
        intensity=intensity,
        error=errors,
    )
    if fit is None:
        selection["weighted_fit"] = False
        selection["error_audit"]["pre_fit_weighting_decision"] = selection["error_audit"]["weighting_decision"]
        selection["error_audit"]["weighting_decision"] = "no_fit_performed"
        selection["error_audit"]["fit_performed"] = False
    else:
        selection["error_audit"]["fit_performed"] = True
    if n >= 2 and fit is None:
        warnings.append("Guinier line could not be determined because selected q² values are not sufficiently distinct.")

    fit_quality = fit_diagnostics(
        y if fit is not None else np.array([], dtype=float),
        fit["fitted"] if fit is not None else np.array([], dtype=float),
        parameter_count=2,
        sigma=sigma if fit is not None else None,
        sigma_is_absolute=True,
    )
    fit_quality.update(
        {
            "fit_coordinate": "ln(I) versus q^2",
            "transformed_sigma_definition": "sigma_lnI = error / I",
            "weighting_policy": selection["error_audit"]["weighting_policy"],
        }
    )
    slope = None if fit is None else fit["slope"]
    intercept = None if fit is None else fit["intercept"]
    rg = None
    rg_stderr = None
    rg_reason = "fit_not_available"
    if slope is not None and slope < 0.0:
        rg = _native_float(math.sqrt(-3.0 * slope))
        if rg is not None and fit["slope_stderr"] is not None and rg > 0.0:
            rg_stderr = _native_float(abs(3.0 * fit["slope_stderr"] / (2.0 * rg)))
        rg_reason = None
    elif slope is not None:
        rg_reason = "Guinier slope is non-negative; Rg is not physically valid for this interval."
        warnings.append(rg_reason)

    i0 = _safe_exp(intercept)
    i0_stderr = None
    if i0 is not None and fit is not None and fit["intercept_stderr"] is not None:
        i0_stderr = _native_float(abs(i0 * fit["intercept_stderr"]))
    q_start = _native_float(np.min(q)) if n else None
    q_end = _native_float(np.max(q)) if n else None
    qmin_rg = _native_float(q_start * rg) if q_start is not None and rg is not None else None
    qmax_rg = _native_float(q_end * rg) if q_end is not None and rg is not None else None
    if qmax_rg is not None and qmax_rg > 1.3:
        warnings.append("Guinier interval may be too high because qRg_max > 1.3.")

    residual_rows = []
    if fit is not None:
        residual_rows = _enrich_residual_rows(
            indices=indices,
            q=q,
            intensity=intensity,
            error=errors,
            observed=y,
            fitted=fit["fitted"],
            sigma=sigma,
            transformed_x=x,
            coordinate="ln(I) versus q^2",
        )
    parameter_rows = parameter_records(
        ["Rg", "I0", "slope", "intercept"],
        [rg, i0, slope, intercept],
        units=[curve.q_unit.replace("^-1", ""), curve.intensity_unit, _guinier_slope_unit(curve.q_unit), "dimensionless"],
        stderr=[rg_stderr, i0_stderr, None if fit is None else fit["slope_stderr"], None if fit is None else fit["intercept_stderr"]],
    )
    fit_valid = fit is not None
    if not fit_valid:
        status = "invalid"
        validity_reason = "fewer_than_two_distinct_log_domain_fit_points"
    elif rg is None:
        status = "invalid"
        validity_reason = rg_reason
    elif n < min_points:
        status = "assumption_dependent"
        validity_reason = "fewer_than_requested_minimum_points"
    else:
        status = "valid"
        validity_reason = None
    results = {
        "Rg": rg,
        "I0": i0,
        "lnI0": intercept,
        "slope": slope,
        "intercept": intercept,
        "R2": fit_quality["R2"],
        "adjusted_R2": fit_quality["adjusted_R2"],
        "reduced_chi_square": fit_quality["reduced_chi_square"],
        "q_start": q_start,
        "q_end": q_end,
        "q_min": selection["q_range"][0],
        "q_max": selection["q_range"][1],
        "qRg_min": qmin_rg,
        "qRg_max": qmax_rg,
        "qminRg": qmin_rg,
        "qmaxRg": qmax_rg,
        "fit_points": n,
        "fit_points_semantics": "legacy_eligible_log_domain_points",
        "eligible_points": n,
        "actual_fit_points": actual_fit_points,
        "excluded_points": int(len(selection["excluded_rows"])),
        "weighted_fit": bool(fit is not None and selection["weighted_fit"]),
        "parameter_records": parameter_rows,
        "uncertainty": {
            "Rg": rg_stderr,
            "I0": i0_stderr,
            "slope": None if fit is None else fit["slope_stderr"],
            "intercept": None if fit is None else fit["intercept_stderr"],
            "covariance": None if fit is None else fit["covariance"],
        },
        "fit_quality": fit_quality,
        "residual_rows": residual_rows,
        "fit_not_performed_rows": fit_not_performed_rows,
        "excluded_rows": selection["excluded_rows"],
        "error_audit": selection["error_audit"],
        "residuals": [row["residual"] for row in residual_rows],
        "standardized_residuals": [row["standardized_residual"] for row in residual_rows],
        "validity": {
            "status": status,
            "fit_valid": fit_valid,
            "minimum_points_met": bool(n >= min_points),
            "eligible_points": n,
            "actual_fit_points": actual_fit_points,
            "Rg_valid": rg is not None,
            "Rg_reason": rg_reason,
            "reason": validity_reason,
        },
        "assumptions": [
            "The selected interval is evaluated in ln(I) versus q² coordinates.",
            "A linear Guinier result is descriptive and must be checked with qRg limits and residuals.",
        ],
    }
    method_warnings = guinier_warnings(
        qrg_max=qmax_rg,
        fit_points=n,
        slope=slope,
        r_squared=fit_quality["R2"],
        q_range_width=selection["q_range"][1] - selection["q_range"][0],
    )
    return _finalize_result_warnings(
        _create_result_with_method_warnings(
            curve=curve,
            analysis_type="guinier",
            q_range=q_range,
            parameters={"min_points": min_points},
            results=results,
            warnings=warnings,
            method_warnings=method_warnings,
        )
    )


def power_law_analysis(curve: CurveData, q_range: tuple[float, float], *, min_points: int = 5) -> AnalysisResult:
    """Fit ``ln I(q) = ln(A) - alpha ln(q)`` with complete diagnostics."""

    selection, warnings = _prepare_log_fit_selection(curve, q_range, require_q_positive=True)
    q = selection["q"]
    intensity = selection["intensity"]
    indices = selection["indices"]
    errors = selection["error"]
    sigma = selection["sigma"]
    n = int(q.size)
    if n < min_points:
        warnings.append(f"Too few points for power-law analysis: {n} < {min_points}.")

    x = np.log(q) if n else np.array([], dtype=float)
    y = np.log(intensity) if n else np.array([], dtype=float)
    fit = _linear_fit_with_uncertainty(x, y, sigma) if n >= 2 else None
    actual_fit_points = n if fit is not None else 0
    fit_not_performed_rows = [] if fit is not None else _fit_not_performed_rows(
        indices=indices,
        q=q,
        intensity=intensity,
        error=errors,
    )
    if fit is None:
        selection["weighted_fit"] = False
        selection["error_audit"]["pre_fit_weighting_decision"] = selection["error_audit"]["weighting_decision"]
        selection["error_audit"]["weighting_decision"] = "no_fit_performed"
        selection["error_audit"]["fit_performed"] = False
    else:
        selection["error_audit"]["fit_performed"] = True
    if n >= 2 and fit is None:
        warnings.append("Power-law line could not be determined because selected ln(q) values are not sufficiently distinct.")

    fit_quality = fit_diagnostics(
        y if fit is not None else np.array([], dtype=float),
        fit["fitted"] if fit is not None else np.array([], dtype=float),
        parameter_count=2,
        sigma=sigma if fit is not None else None,
        sigma_is_absolute=True,
    )
    fit_quality.update(
        {
            "fit_coordinate": "ln(I) versus ln(q)",
            "transformed_sigma_definition": "sigma_lnI = error / I",
            "weighting_policy": selection["error_audit"]["weighting_policy"],
        }
    )
    slope = None if fit is None else fit["slope"]
    intercept = None if fit is None else fit["intercept"]
    alpha = None if slope is None else _native_float(-slope)
    prefactor = _safe_exp(intercept)
    alpha_stderr = None if fit is None else fit["slope_stderr"]
    prefactor_stderr = None
    if prefactor is not None and fit is not None and fit["intercept_stderr"] is not None:
        prefactor_stderr = _native_float(abs(prefactor * fit["intercept_stderr"]))
    q_start = _native_float(np.min(q)) if n else None
    q_end = _native_float(np.max(q)) if n else None

    residual_rows = []
    if fit is not None:
        residual_rows = _enrich_residual_rows(
            indices=indices,
            q=q,
            intensity=intensity,
            error=errors,
            observed=y,
            fitted=fit["fitted"],
            sigma=sigma,
            transformed_x=x,
            coordinate="ln(I) versus ln(q)",
        )
    parameter_rows = parameter_records(
        ["alpha", "prefactor", "slope", "intercept"],
        [alpha, prefactor, slope, intercept],
        units=["dimensionless", f"{curve.intensity_unit}*({curve.q_unit})^alpha", "dimensionless", "dimensionless"],
        stderr=[alpha_stderr, prefactor_stderr, None if fit is None else fit["slope_stderr"], None if fit is None else fit["intercept_stderr"]],
    )
    if fit is None:
        status = "invalid"
        validity_reason = "fewer_than_two_distinct_log_domain_fit_points"
    elif n < min_points:
        status = "assumption_dependent"
        validity_reason = "fewer_than_requested_minimum_points"
    else:
        status = "valid"
        validity_reason = None

    results = {
        "alpha": alpha,
        "prefactor": prefactor,
        "slope": slope,
        "intercept": intercept,
        "R2": fit_quality["R2"],
        "adjusted_R2": fit_quality["adjusted_R2"],
        "reduced_chi_square": fit_quality["reduced_chi_square"],
        "q_range": selection["q_range"],
        "q_start": q_start,
        "q_end": q_end,
        "fit_points": n,
        "fit_points_semantics": "legacy_eligible_log_domain_points",
        "eligible_points": n,
        "actual_fit_points": actual_fit_points,
        "excluded_points": int(len(selection["excluded_rows"])),
        "weighted_fit": bool(fit is not None and selection["weighted_fit"]),
        "parameter_records": parameter_rows,
        "uncertainty": {
            "alpha": alpha_stderr,
            "prefactor": prefactor_stderr,
            "slope": None if fit is None else fit["slope_stderr"],
            "intercept": None if fit is None else fit["intercept_stderr"],
            "covariance": None if fit is None else fit["covariance"],
        },
        "fit_quality": fit_quality,
        "residual_rows": residual_rows,
        "fit_not_performed_rows": fit_not_performed_rows,
        "excluded_rows": selection["excluded_rows"],
        "error_audit": selection["error_audit"],
        "residuals": [row["residual"] for row in residual_rows],
        "standardized_residuals": [row["standardized_residual"] for row in residual_rows],
        "validity": {
            "status": status,
            "fit_valid": fit is not None,
            "minimum_points_met": bool(n >= min_points),
            "eligible_points": n,
            "actual_fit_points": actual_fit_points,
            "reason": validity_reason,
        },
        "assumptions": [
            "The selected interval is evaluated in ln(I) versus ln(q) coordinates.",
            "The fitted exponent is descriptive and is not a unique material-mechanism assignment.",
        ],
    }
    if alpha is not None and abs(alpha - 4.0) <= 0.3:
        warnings.append("alpha is close to 4; this may be Porod-like behavior, but it is not a unique structural conclusion.")
    elif alpha is not None and 1.0 < alpha < 3.0:
        warnings.append("alpha is between 1 and 3; it may relate to mass-fractal or multiscale structure, but material context and q range are required.")
    elif alpha is not None and 3.0 < alpha < 4.0:
        warnings.append("alpha is between 3 and 4; it may relate to surface-fractal or rough-interface behavior, but this is not unique.")
    method_warnings = power_law_warnings(alpha=alpha, fit_points=n)
    return _finalize_result_warnings(
        _create_result_with_method_warnings(
            curve=curve,
            analysis_type="power_law",
            q_range=q_range,
            parameters={"min_points": min_points},
            results=results,
            warnings=warnings,
            method_warnings=method_warnings,
        )
    )


def local_slope(curve: CurveData, q_range: tuple[float, float], *, window_length: int = 5, std_threshold: float = 0.15) -> AnalysisResult:
    """Calculate descriptive local log-log slopes and stable-window candidates."""

    if window_length <= 0 or window_length % 2 == 0:
        raise ValueError("window_length must be a positive odd integer.")
    threshold = _native_float(std_threshold)
    if threshold is None or threshold < 0.0:
        raise ValueError("std_threshold must be a finite non-negative number.")

    selection, warnings = _prepare_log_fit_selection(
        curve,
        q_range,
        require_q_positive=True,
        use_error_for_weighting=False,
    )
    q = selection["q"]
    intensity = selection["intensity"]
    indices = selection["indices"]
    errors = selection["error"]
    if q.size:
        if errors is None:
            q, intensity, sorted_indices = sort_arrays_by_q(q, intensity, indices)
            indices = np.asarray(sorted_indices, dtype=int)
        else:
            q, intensity, sorted_errors, sorted_indices = sort_arrays_by_q(q, intensity, errors, indices)
            errors = np.asarray(sorted_errors, dtype=float)
            indices = np.asarray(sorted_indices, dtype=int)
        unique_q, unique_positions = np.unique(q, return_index=True)
        if unique_q.size != q.size:
            retained = set(int(position) for position in unique_positions)
            duplicate_count = 0
            for position in range(q.size):
                if position in retained:
                    continue
                duplicate_count += 1
                selection["excluded_rows"].append(
                    _excluded_row(
                        original_index=int(indices[position]),
                        q=_native_float(q[position]),
                        intensity=_native_float(intensity[position]),
                        error=None if errors is None else _native_float(errors[position]),
                        reasons=["duplicate_q"],
                    )
                )
            warnings.append(f"Excluded {duplicate_count} duplicate q points before local-slope calculation.")
            q = q[unique_positions]
            intensity = intensity[unique_positions]
            indices = indices[unique_positions]
            if errors is not None:
                errors = errors[unique_positions]
    if q.size <= window_length:
        warnings.append("window_length must be smaller than the number of valid points.")

    alpha_array = -np.gradient(np.log(intensity), np.log(q)) if q.size >= 2 else np.full(q.shape, np.nan, dtype=float)
    point_rows: list[dict] = []
    for position in range(q.size):
        alpha_value = _native_float(alpha_array[position])
        valid = alpha_value is not None
        point_rows.append(
            {
                "original_index": int(indices[position]),
                "q": _native_float(q[position]),
                "intensity": _native_float(intensity[position]),
                "error": None if errors is None else _native_float(errors[position]),
                "alpha": alpha_value,
                "valid": valid,
                "reason": None if valid else "insufficient_neighbors" if q.size < 2 else "non_finite_local_slope",
            }
        )

    plateaus: list[dict] = []
    if alpha_array.size >= window_length and window_length > 1:
        for start in range(0, alpha_array.size - window_length + 1):
            segment = alpha_array[start : start + window_length]
            if not np.all(np.isfinite(segment)):
                continue
            alpha_std = _native_float(np.std(segment))
            if alpha_std is None or alpha_std > threshold:
                continue
            stability_score = 1.0 if threshold == 0.0 else max(0.0, min(1.0, 1.0 - alpha_std / threshold))
            plateaus.append(
                {
                    "plateau_id": int(len(plateaus) + 1),
                    "q_start": _native_float(q[start]),
                    "q_end": _native_float(q[start + window_length - 1]),
                    "alpha_mean": _native_float(np.mean(segment)),
                    "alpha_std": alpha_std,
                    "point_count": int(window_length),
                    "stability_score": _native_float(stability_score),
                }
            )

    valid_alpha = np.asarray([row["alpha"] for row in point_rows if row["valid"]], dtype=float)
    if q.size < 2:
        validity_status = "invalid"
        validity_reason = "insufficient_neighbors"
    elif valid_alpha.size == 0:
        validity_status = "invalid"
        validity_reason = "no_finite_local_slope"
    elif q.size <= window_length:
        validity_status = "assumption_dependent"
        validity_reason = "window_not_smaller_than_selected_point_count"
    else:
        validity_status = "valid"
        validity_reason = None
    results = {
        "q_mid": [row["q"] for row in point_rows],
        "alpha": [row["alpha"] for row in point_rows],
        "point_rows": point_rows,
        "plateaus": plateaus,
        "plateau_candidate_ranges": [(row["q_start"], row["q_end"]) for row in plateaus],
        "alpha_mean": _native_float(np.mean(valid_alpha)) if valid_alpha.size else None,
        "alpha_std": _native_float(np.std(valid_alpha)) if valid_alpha.size else None,
        "q_start": _native_float(np.min(q)) if q.size else None,
        "q_end": _native_float(np.max(q)) if q.size else None,
        "valid_points": int(valid_alpha.size),
        "excluded_points": int(len(selection["excluded_rows"])),
        "excluded_rows": selection["excluded_rows"],
        "error_audit": selection["error_audit"],
        "validity": {
            "status": validity_status,
            "valid_point_count": int(valid_alpha.size),
            "minimum_neighbors_available": bool(q.size >= 2),
            "window_length": int(window_length),
            "std_threshold": threshold,
            "reason": validity_reason,
        },
        "assumptions": [
            "alpha(q) = -d ln(I) / d ln(q) is a descriptive local derivative.",
            "Local-slope plateaus do not by themselves establish a material mechanism.",
        ],
    }
    return _finalize_result_warnings(
        AnalysisResult.create(
            curve=curve,
            analysis_type="local_slope",
            q_range=q_range,
            parameters={"window_length": int(window_length), "std_threshold": threshold},
            results=results,
            warnings=warnings,
        )
    )


def invariant_measured(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    order = np.argsort(curve.q[mask])
    q = curve.q[mask][order]
    intensity = curve.intensity[mask][order]
    warnings: list[str] = []
    integrand = q**2 * intensity
    q_measured = float(np.trapezoid(integrand, q)) if q.size >= 2 else float("nan")
    negative_intensity_points = int(np.sum(intensity < 0))
    negative_contribution_area = 0.0
    positive_contribution_area = 0.0
    if q.size >= 2:
        interval_contributions = 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)
        negative_contribution_area = float(np.sum(interval_contributions[interval_contributions < 0.0]))
        positive_contribution_area = float(np.sum(interval_contributions[interval_contributions > 0.0]))
    negative_fraction = (
        abs(negative_contribution_area) / positive_contribution_area
        if positive_contribution_area > 0.0 and negative_contribution_area < 0.0
        else 0.0
    )
    if negative_intensity_points:
        warnings.append(
            f"Negative intensity affected the measured invariant: {negative_intensity_points} points had I(q) < 0; "
            "do not interpret this finite-range value as a volume fraction without reviewing background subtraction."
        )
    results = {
        "Q_measured": q_measured,
        "q_min": q_range[0],
        "q_max": q_range[1],
        "integration_points": int(q.size),
        "negative_intensity_points": negative_intensity_points,
        "negative_contribution_area": negative_contribution_area,
        "negative_contribution_fraction": negative_fraction,
    }
    return _create_result_with_method_warnings(curve=curve, analysis_type="invariant_measured", q_range=q_range, parameters={"extrapolation": "disabled"}, results=results, warnings=warnings, method_warnings=invariant_warnings())


def _positive_interval_contributions(q: np.ndarray, integrand: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if q.size < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    interval_q = 0.5 * (q[:-1] + q[1:])
    interval_q_value = 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)
    return interval_q, np.maximum(interval_q_value, 0.0)


def _contribution_quantile(q: np.ndarray, contributions: np.ndarray, cumulative: np.ndarray, fraction: float) -> float | None:
    total = float(cumulative[-1]) if cumulative.size else 0.0
    if total <= 0.0:
        return None
    target = fraction * total
    index = int(np.searchsorted(cumulative, target, side="left"))
    if index <= 0:
        return float(q[0])
    if index >= cumulative.size:
        return float(q[-1])
    previous = float(cumulative[index - 1])
    segment = float(contributions[index - 1])
    if segment <= 0.0:
        return float(q[index])
    position = (target - previous) / segment
    return float(q[index - 1] + position * (q[index] - q[index - 1]))


def information_budget(curve: CurveData, q_range: tuple[float, float], *, q_bands: tuple[float, float] | None = None) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    invalid_q = mask & (curve.q <= 0)
    warnings: list[str] = []
    if np.any(invalid_q):
        warnings.append(f"Excluded {int(np.sum(invalid_q))} points with q <= 0.")
    mask &= curve.q > 0
    order = np.argsort(curve.q[mask])
    q = curve.q[mask][order]
    intensity = curve.intensity[mask][order]

    integrand = q**2 * intensity
    q3i = q**3 * intensity
    q_measured = float(np.trapezoid(integrand, q)) if q.size >= 2 else float("nan")
    cumulative_q = np.concatenate(([0.0], np.cumsum(0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)))) if q.size >= 2 else np.array([], dtype=float)
    interval_q, positive_contributions = _positive_interval_contributions(q, integrand)
    positive_cumulative = np.concatenate(([0.0], np.cumsum(positive_contributions))) if q.size >= 2 else np.array([], dtype=float)
    positive_total = float(positive_cumulative[-1]) if positive_cumulative.size else 0.0

    if q.size < 2:
        warnings.append("Information budget needs at least two valid q > 0 points.")
    if positive_total <= 0.0 and q.size >= 2:
        warnings.append("No positive invariant contribution was available for quantile and fraction metrics.")

    quantiles = {
        "q_Q10": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.10),
        "q_Q50": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.50),
        "q_Q90": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.90),
    }
    d_q50 = float(2.0 * math.pi / quantiles["q_Q50"]) if quantiles["q_Q50"] not in (None, 0.0) else None

    probabilities = positive_contributions / positive_total if positive_total > 0.0 else np.array([], dtype=float)
    if probabilities.size > 1:
        nonzero = probabilities[probabilities > 0.0]
        entropy = float(-np.sum(nonzero * np.log(nonzero)) / math.log(probabilities.size))
    else:
        entropy = 0.0 if probabilities.size == 1 else None

    if q_bands is None and q.size:
        log_min = float(np.log(q[0]))
        log_max = float(np.log(q[-1]))
        low_mid = float(np.exp(log_min + (log_max - log_min) / 3.0))
        mid_high = float(np.exp(log_min + 2.0 * (log_max - log_min) / 3.0))
    elif q_bands is not None:
        low_mid, mid_high = q_bands
    else:
        low_mid, mid_high = (None, None)

    fractions = {"low": None, "mid": None, "high": None}
    if positive_total > 0.0 and low_mid is not None and mid_high is not None:
        low = float(np.sum(positive_contributions[interval_q < low_mid]))
        mid = float(np.sum(positive_contributions[(interval_q >= low_mid) & (interval_q < mid_high)]))
        high = float(np.sum(positive_contributions[interval_q >= mid_high]))
        fractions = {"low": low / positive_total, "mid": mid / positive_total, "high": high / positive_total}

    if q.size:
        peak_index = int(np.nanargmax(q3i))
        q3i_peak_q = float(q[peak_index])
        q3i_peak_d = float(2.0 * math.pi / q3i_peak_q) if q3i_peak_q > 0 else None
    else:
        q3i_peak_q = None
        q3i_peak_d = None

    results = {
        "q": q.tolist(),
        "lnq": np.log(q).tolist() if q.size else [],
        "q3I": q3i.tolist(),
        "Q_cumulative": cumulative_q.tolist(),
        "Q_measured": q_measured,
        "Q_positive_total": positive_total,
        "q3I_peak_q": q3i_peak_q,
        "q3I_peak_d": q3i_peak_d,
        **quantiles,
        "d_Q50": d_q50,
        "Q_entropy": entropy,
        "Q_low_mid_high_fraction": fractions,
        "Q_low_fraction": fractions["low"],
        "Q_mid_fraction": fractions["mid"],
        "Q_high_fraction": fractions["high"],
        "q_band_boundaries": {"low_mid": low_mid, "mid_high": mid_high},
        "d_observable_min": float(2.0 * math.pi / q[-1]) if q.size else None,
        "d_observable_max": float(2.0 * math.pi / q[0]) if q.size else None,
        "integration_points": int(q.size),
    }
    return _create_result_with_method_warnings(
        curve=curve,
        analysis_type="information_budget",
        q_range=q_range,
        parameters={"q_bands": q_bands},
        results=results,
        warnings=warnings,
        method_warnings=invariant_warnings(),
    )


def kratky_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    """Report a Kratky maximum and width only when both identify the same peak."""

    mask = _range_mask(curve, q_range)
    invalid_q = mask & (curve.q <= 0.0)
    mask &= curve.q > 0.0
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if q.size > 1:
        order = np.argsort(q, kind="stable")
        q = q[order]
        intensity = intensity[order]
    with np.errstate(over="ignore", invalid="ignore"):
        y = q**2 * intensity
    finite_y = np.isfinite(y)
    excluded_y = int(q.size - np.count_nonzero(finite_y))
    q = q[finite_y]
    y = y[finite_y]
    warnings: list[str] = []
    if np.any(invalid_q):
        warnings.append(f"Excluded {int(np.sum(invalid_q))} selected points with q <= 0 from Kratky peak metrics.")
    if excluded_y:
        warnings.append(f"Excluded {excluded_y} selected points with non-finite q²I(q) from Kratky peak metrics.")

    duplicate_count = 0
    if q.size > 1:
        unique_q, inverse = np.unique(q, return_inverse=True)
        if unique_q.size != q.size:
            duplicate_count = int(q.size - unique_q.size)
            collapsed_y = np.empty(unique_q.shape, dtype=float)
            for group_index in range(unique_q.size):
                value = _safe_group_mean(y[inverse == group_index])
                collapsed_y[group_index] = np.nan if value is None else value
            keep = np.isfinite(unique_q) & np.isfinite(collapsed_y)
            rejected_count = int(np.count_nonzero(~keep))
            y = collapsed_y[keep]
            q = unique_q[keep]
            warnings.append(f"Collapsed {duplicate_count} duplicate q rows by mean q2I(q) before Kratky peak metrics.")
            if rejected_count:
                warnings.append(f"Excluded {rejected_count} duplicate-q groups whose collapsed q2I(q) was non-finite before Kratky peak metrics.")

    results = {
        "q_K": None,
        "q2I_max": None,
        "d_K": None,
        "FWHM": None,
        "HWHM": None,
        "area": None,
        "peak_area": None,
        "raw_area_within_fwhm": None,
        "peak_prominence": None,
        "peak_completeness_status": "insufficient_points",
        "peak_complete": False,
        "edge_truncated": False,
        "peak_point_count": int(q.size),
        "duplicate_q_collapsed_count": duplicate_count,
        "width_peak_q": None,
        "width_peak_index": None,
        "width_peak_matches_q_K": False,
        "enriched_peak_identity": "no_width_peak_available",
        "interpretation_limit": "A Kratky maximum or width is a finite-range numerical descriptor, not proof of a unique particle compactness or conformation.",
    }
    if not q.size:
        warnings.append("Kratky peak metrics need at least one finite q > 0 point.")
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)

    maximum_index = int(np.argmax(y))
    q_k = _native_float(q[maximum_index])
    q2i_max = _native_float(y[maximum_index])
    d_k = _safe_positive_ratio(2.0 * math.pi, q_k) if q_k is not None else None
    results.update(
        {
            "q_K": q_k,
            "q2I_max": q2i_max,
            "d_K": d_k,
        }
    )
    if d_k is None:
        warnings.append("Kratky d_K is unavailable because 2π/q_K overflowed or became non-finite.")
    if q.size < 3:
        warnings.append("Kratky FWHM and area need at least three finite q > 0 points.")
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)

    peaks, properties = find_peaks(y, prominence=(None, None))
    matching_peak_positions = np.where(peaks == maximum_index)[0]
    if not matching_peak_positions.size:
        if maximum_index == 0:
            status = "left_truncated"
        elif maximum_index == q.size - 1:
            status = "right_truncated"
        else:
            status = "no_internal_peak"
        results.update(
            {
                "peak_completeness_status": status,
                "edge_truncated": status.endswith("truncated"),
                "enriched_peak_identity": "no_internal_peak_matches_q_K",
            }
        )
        warnings.append(
            "Kratky FWHM and area are unavailable because no internal width peak matches the legacy q_K maximum "
            f"({status})."
        )
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)

    peak_index = maximum_index
    peak_position = int(matching_peak_positions[0])
    widths = peak_widths(y, np.asarray([peak_index]), rel_height=0.5)
    left_ip = _native_float(widths[2][0])
    right_ip = _native_float(widths[3][0])
    if left_ip is None or right_ip is None:
        status = "derived_values_unavailable"
    elif left_ip <= 0.0:
        status = "left_truncated"
    elif right_ip >= float(q.size - 1):
        status = "right_truncated"
    else:
        status = "complete"
    prominence_values = properties.get("prominences", np.array([np.nan]))
    prominence = _native_float(prominence_values[peak_position])
    results.update(
        {
            "peak_prominence": prominence,
            "peak_completeness_status": status,
            "peak_complete": status == "complete",
            "edge_truncated": status != "complete",
            "width_peak_q": q_k,
            "width_peak_index": int(peak_index),
            "width_peak_matches_q_K": True,
            "enriched_peak_identity": "width_peak_matches_q_K",
        }
    )
    if status != "complete":
        warnings.append(f"Kratky FWHM and area are unavailable because the internal peak is {status} in the selected q range.")
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)

    positions = np.arange(q.size, dtype=float)
    left_q = _native_float(np.interp(left_ip, positions, q))
    right_q = _native_float(np.interp(right_ip, positions, q))
    fwhm = _native_float(right_q - left_q) if left_q is not None and right_q is not None else None
    left_y = _native_float(np.interp(left_ip, positions, y))
    right_y = _native_float(np.interp(right_ip, positions, y))
    if fwhm is None or fwhm <= 0.0 or left_y is None or right_y is None:
        results.update(
            {
                "peak_completeness_status": "derived_values_unavailable",
                "peak_complete": False,
                "edge_truncated": False,
                "left_q": left_q,
                "right_q": right_q,
            }
        )
        warnings.append("Kratky FWHM and area are unavailable because a derived width or boundary scalar overflowed or became non-finite.")
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)
    inside = (q > left_q) & (q < right_q)
    area_q = np.concatenate(([left_q], q[inside], [right_q]))
    area_y = np.concatenate(([left_y], y[inside], [right_y]))
    baseline = np.interp(area_q, [left_q, right_q], [left_y, right_y])
    area = _safe_trapezoid(area_y - baseline, area_q)
    raw_area = _safe_trapezoid(area_y, area_q)
    hwhm = _native_float(fwhm / 2.0)
    if area is None or raw_area is None or hwhm is None:
        results.update(
            {
                "peak_completeness_status": "derived_values_unavailable",
                "peak_complete": False,
                "edge_truncated": False,
                "left_q": left_q,
                "right_q": right_q,
            }
        )
        warnings.append("Kratky FWHM or area is unavailable because a finite-range derived calculation overflowed or became non-finite.")
        return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)
    results.update(
        {
            "FWHM": fwhm,
            "HWHM": hwhm,
            "area": area,
            "peak_area": area,
            "raw_area_within_fwhm": raw_area,
            "left_q": left_q,
            "right_q": right_q,
        }
    )
    return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=warnings)


def porod_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if q.size > 1:
        order = np.argsort(q, kind="stable")
        q = q[order]
        intensity = intensity[order]
    with np.errstate(over="ignore", invalid="ignore"):
        y = q**4 * intensity
    finite_y = np.isfinite(y)
    q_finite = q[finite_y]
    y_finite = y[finite_y]
    statistics = _finite_porod_statistics(y_finite)
    mean = statistics["mean"]
    std = statistics["std"]
    cv = statistics["cv"]
    warnings: list[str] = []
    excluded = int(q.size - q_finite.size)
    if excluded:
        warnings.append(f"Excluded {excluded} selected points because q⁴I(q) was not finite after multiplication.")
    if statistics["reduction_reason"] is not None:
        warnings.append(
            "q⁴I(q) plateau statistics are unavailable because finite-value reduction would overflow or become non-finite: "
            f"{statistics['reduction_reason']}."
        )
    results = {
        "q4I_plateau_mean": mean,
        "q4I_plateau_std": std,
        "q4I_plateau_cv": cv,
        "q4I_plateau_min": statistics["min"],
        "q4I_plateau_max": statistics["max"],
        "q4I_plateau_median": statistics["median"],
        "q4I_plateau_range": statistics["range"],
        "q4I_plateau_q_min": float(q_finite[0]) if q_finite.size else None,
        "q4I_plateau_q_max": float(q_finite[-1]) if q_finite.size else None,
        "q4I_finite_points": int(q_finite.size),
        "q4I_excluded_nonfinite_count": excluded,
        "noise_score": cv,
        "q4I_noise_score": cv,
        "points": int(q.size),
    }
    return _create_result_with_method_warnings(
        curve=curve,
        analysis_type="porod_metrics",
        q_range=q_range,
        results=results,
        warnings=warnings,
        method_warnings=porod_plateau_warnings(y_finite if statistics["reduction_reason"] is None else np.array([], dtype=float)),
    )

