"""Traceable complete fitting for the registered SAS shape models.

The numerical result is conditional on the selected model, q range, background
handling, and initial-value strategy.  It is deliberately reported as a model
fit, not as proof of a unique sample morphology.
"""

from __future__ import annotations

import warnings as python_warnings
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit

from app.core.analysis_schema import EXPORT_TABLE_FIT_CURVES, RESULT_GROUP_SHAPE_FIT, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.fit_diagnostics import build_residual_rows, covariance_to_correlation, fit_diagnostics, parameter_records
from app.core.model_parameters import DERIVED_PARAMETER_BUILDERS, derived_model_parameters
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks
from app.core.shape_models import MODEL_FUNCTIONS, MODEL_SPECS, evaluate_model


JITTERED_MULTISTART_COUNT = 2
# Preserve the legacy default optimizer budget for complete single and batch
# fits. A batch result must have the same retry/selection semantics as the
# standalone complete result; performance shortcuts are not enabled by default.
MAX_FUNCTION_EVALUATIONS = 20000
IDENTIFIABILITY_WEAK_CORRELATION = 0.95
IDENTIFIABILITY_NON_IDENTIFIABLE_CORRELATION = 0.995
IDENTIFIABILITY_WEAK_CONDITION_NUMBER = 1e8
IDENTIFIABILITY_NON_IDENTIFIABLE_CONDITION_NUMBER = 1e12


def _finite_float(value: Any) -> float | None:
    """Return a finite native float or ``None`` without leaking NaN/inf."""

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if np.isfinite(numeric) else None


def _safe_float_list(values: Sequence[Any] | np.ndarray) -> list[float | None]:
    return [_finite_float(value) for value in values]


def _length_unit_from_q_unit(q_unit: str) -> str:
    cleaned = str(q_unit).strip()
    if cleaned == "A^-1":
        return "A"
    if cleaned == "nm^-1":
        return "nm"
    if cleaned.endswith("^-1") and len(cleaned) > 3:
        return cleaned[:-3]
    return f"1/({cleaned or 'q'})"


def _parameter_units_for_curve(units: Mapping[str, str], curve: CurveData) -> dict[str, str]:
    length_unit = _length_unit_from_q_unit(curve.q_unit)
    resolved: dict[str, str] = {}
    for name, unit in units.items():
        if unit == "1/q":
            resolved[name] = length_unit
        elif unit == "q":
            resolved[name] = str(curve.q_unit)
        else:
            resolved[name] = str(unit)
    return resolved


def _initial_from_curve(curve: CurveData, spec_name: str) -> list[float]:
    """Build a finite scale/background-aware default without changing ``curve``."""

    spec = MODEL_SPECS[spec_name]
    values = [float(value) for value in spec.initial_values]
    q_values = np.asarray(curve.q, dtype=float)
    intensity_values = np.asarray(curve.intensity, dtype=float)
    finite_pair = np.isfinite(q_values) & np.isfinite(intensity_values)
    finite_i = intensity_values[finite_pair]
    if finite_i.size:
        scale_guess = _finite_float(np.max(finite_i) - np.min(finite_i))
        background_guess = _finite_float(np.min(finite_i))
        if "scale" in spec.parameter_names and scale_guess is not None:
            values[spec.parameter_names.index("scale")] = max(scale_guess, 1e-9)
        if "background" in spec.parameter_names and background_guess is not None:
            values[spec.parameter_names.index("background")] = background_guess
    if "q0" in spec.parameter_names:
        q_valid = q_values[finite_pair & (q_values > 0.0)]
        i_valid = intensity_values[finite_pair & (q_values > 0.0)]
        if q_valid.size:
            max_index = int(np.argmax(i_valid))
            q0_guess = _finite_float(q_valid[max_index])
            if q0_guess is not None:
                values[spec.parameter_names.index("q0")] = q0_guess
    return values


def _mapping_values(mapping: Mapping[str, Any] | None, names: Sequence[str]) -> dict[str, float]:
    """Accept simple values or parameter-record values, ignoring unknown keys."""

    resolved: dict[str, float] = {}
    if not isinstance(mapping, Mapping):
        return resolved
    for name in names:
        value: Any = mapping.get(name)
        if isinstance(value, Mapping):
            value = value.get("value")
        numeric = _finite_float(value)
        if numeric is not None:
            resolved[name] = numeric
    return resolved


def _inside_bounds(values: Sequence[float], lower: Sequence[float], upper: Sequence[float]) -> np.ndarray:
    """Clip an initial vector just inside finite bounds for SciPy safely."""

    output = np.asarray(values, dtype=float).copy()
    for index in range(output.size):
        low = float(lower[index])
        high = float(upper[index])
        value = output[index]
        if not np.isfinite(value):
            if np.isfinite(low) and np.isfinite(high):
                value = (low + high) / 2.0
            elif np.isfinite(low):
                value = low + max(1.0, abs(low)) * 1e-3
            elif np.isfinite(high):
                value = high - max(1.0, abs(high)) * 1e-3
            else:
                value = 0.0
        if np.isfinite(low) and np.isfinite(high) and high > low:
            midpoint = low + (high - low) / 2.0
            margin = min((high - low) / 4.0, max(abs(high - low) * 1e-8, 1e-300))
            if value <= low or value >= high:
                value = midpoint if high - low <= 2.0 * margin else min(max(value, low + margin), high - margin)
        elif np.isfinite(low) and value <= low:
            value = low + max(abs(low) * 1e-8, 1e-12)
        elif np.isfinite(high) and value >= high:
            value = high - max(abs(high) * 1e-8, 1e-12)
        output[index] = value
    return output


def _apply_parameter_overrides(
    base: Sequence[float],
    names: Sequence[str],
    overrides: Mapping[str, Any] | None,
    lower: Sequence[float],
    upper: Sequence[float],
) -> np.ndarray:
    values = np.asarray(base, dtype=float).copy()
    for name, numeric in _mapping_values(overrides, names).items():
        values[list(names).index(name)] = numeric
    return _inside_bounds(values, lower, upper)


def _deterministic_jittered_vectors(
    base: np.ndarray,
    lower: Sequence[float],
    upper: Sequence[float],
    *,
    model_name: str,
) -> list[np.ndarray]:
    """Return deterministic, bounded multi-starts without random global state."""

    seed = 20260711 + sum((index + 1) * ord(char) for index, char in enumerate(model_name))
    generator = np.random.default_rng(seed)
    vectors: list[np.ndarray] = []
    for _ in range(JITTERED_MULTISTART_COUNT):
        candidate = np.asarray(base, dtype=float).copy()
        for index, value in enumerate(candidate):
            low = float(lower[index])
            high = float(upper[index])
            if np.isfinite(low) and np.isfinite(high):
                span = high - low
                if span > 0.0 and np.isfinite(span):
                    candidate[index] = value + generator.normal(0.0, 0.12) * span
            elif np.isfinite(low) and low >= 0.0:
                candidate[index] = max(1e-300, value) * float(np.exp(generator.normal(0.0, 0.25)))
            else:
                candidate[index] = value + generator.normal(0.0, 0.20) * max(1.0, abs(value))
        vectors.append(_inside_bounds(candidate, lower, upper))
    return vectors


def _select_curve_data(curve: CurveData, q_range: tuple[float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, np.ndarray, list[dict[str, Any]], list[str]]:
    """Select fit-ready rows and retain reasons for all excluded inputs."""

    q_values = np.asarray(curve.q, dtype=float)
    intensity_values = np.asarray(curve.intensity, dtype=float)
    if q_values.ndim != 1 or intensity_values.ndim != 1 or q_values.size != intensity_values.size:
        raise ValueError("curve q and intensity must be one-dimensional arrays of equal length")
    q_low = _finite_float(q_range[0])
    q_high = _finite_float(q_range[1])
    if q_low is None or q_high is None:
        raise ValueError("q_range must contain finite bounds")

    mask = (
        np.isfinite(q_values)
        & np.isfinite(intensity_values)
        & (q_values > 0.0)
        & (q_values >= q_low)
        & (q_values <= q_high)
    )
    selected_indices = np.flatnonzero(mask)
    excluded_rows: list[dict[str, Any]] = []
    error_values: np.ndarray | None = None
    error_aligned = False
    if curve.error is not None:
        candidate_error = np.asarray(curve.error, dtype=float)
        if candidate_error.ndim == 1 and candidate_error.size == q_values.size:
            error_values = candidate_error
            error_aligned = True

    for index in np.flatnonzero(~mask):
        reasons: list[str] = []
        if not np.isfinite(q_values[index]):
            reasons.append("non_finite_q")
        elif q_values[index] <= 0.0:
            reasons.append("non_positive_q")
        elif q_values[index] < q_low or q_values[index] > q_high:
            reasons.append("outside_q_range")
        if not np.isfinite(intensity_values[index]):
            reasons.append("non_finite_intensity")
        excluded_rows.append(
            {
                "original_index": int(index),
                "q": _finite_float(q_values[index]),
                "intensity": _finite_float(intensity_values[index]),
                "error": None if error_values is None else _finite_float(error_values[index]),
                "reason": "; ".join(reasons) or "not_selected",
            }
        )

    sigma: np.ndarray | None = None
    warnings: list[str] = []
    if curve.error is not None:
        if not error_aligned:
            warnings.append("Invalid error values were found; unweighted curve_fit was used.")
        else:
            selected_error = error_values[mask]
            if np.all(np.isfinite(selected_error) & (selected_error > 0.0)):
                sigma = selected_error.copy()
            else:
                warnings.append("Invalid error values were found; unweighted curve_fit was used.")
    return q_values[mask].copy(), intensity_values[mask].copy(), sigma, selected_indices, excluded_rows, warnings


def _attempt_record(
    *,
    source: str,
    names: Sequence[str],
    initial: np.ndarray,
    status: str,
    error: str | None,
    fit_quality: Mapping[str, Any] | None = None,
    optimizer_warnings: Sequence[str] | None = None,
) -> dict[str, Any]:
    vector = {name: _finite_float(initial[index]) for index, name in enumerate(names)}
    return {
        "source": source,
        "status": status,
        "error": error,
        "initial_vector": vector,
        "fit_quality": dict(fit_quality or {}),
        "optimizer_warnings": [str(message) for message in (optimizer_warnings or [])],
    }


def _run_attempt(
    *,
    model_name: str,
    names: Sequence[str],
    q: np.ndarray,
    observed: np.ndarray,
    sigma: np.ndarray | None,
    lower: Sequence[float],
    upper: Sequence[float],
    initial: np.ndarray,
    source: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Run exactly one optimizer start and return an export-safe audit record."""

    try:
        with python_warnings.catch_warnings(record=True) as caught:
            python_warnings.simplefilter("always", OptimizeWarning)
            optimized, covariance = curve_fit(
                MODEL_FUNCTIONS[model_name],
                q,
                observed,
                p0=initial,
                bounds=(lower, upper),
                sigma=sigma,
                absolute_sigma=sigma is not None,
                maxfev=MAX_FUNCTION_EVALUATIONS,
            )
        fitted = np.asarray(evaluate_model(model_name, q, list(optimized)), dtype=float)
        if fitted.shape != observed.shape or not np.all(np.isfinite(fitted)):
            raise ValueError("model evaluation produced non-finite fitted values")
        with np.errstate(over="ignore", invalid="ignore"):
            residual = observed - fitted
        if not np.all(np.isfinite(residual)):
            raise ValueError("model evaluation produced non-finite residuals")
        quality = fit_diagnostics(
            observed,
            fitted,
            parameter_count=len(names),
            sigma=sigma,
            sigma_is_absolute=True,
        )
        warning_messages = [str(item.message) for item in caught]
        record = _attempt_record(
            source=source,
            names=names,
            initial=initial,
            status="success",
            error=None,
            fit_quality=quality,
            optimizer_warnings=warning_messages,
        )
        return record, {"parameters": np.asarray(optimized, dtype=float), "covariance": np.asarray(covariance, dtype=float), "fitted": fitted, "quality": quality}
    except Exception as exc:  # SciPy may raise model-specific numerical errors.
        error = f"{type(exc).__name__}: {exc}"
        return _attempt_record(source=source, names=names, initial=initial, status="failed", error=error), None


def _aicc_sort_key(candidate: dict[str, Any], attempt_index: int) -> tuple[float, int]:
    """Order finite AICc candidates without introducing an RMSE tie-breaker."""

    aicc = _finite_float(candidate["quality"].get("AICc"))
    if aicc is None:
        raise ValueError("AICc selection requires a finite AICc")
    return aicc, attempt_index


def _rmse_sort_key(candidate: dict[str, Any], attempt_index: int) -> tuple[int, float, int]:
    """Order RMSE only when every valid candidate lacks finite AICc."""

    rmse = _finite_float(candidate["quality"].get("rmse"))
    return (0 if rmse is not None else 1, rmse if rmse is not None else float("inf"), attempt_index)


def _safe_covariance(covariance: np.ndarray | None, parameter_count: int) -> tuple[list[list[float | None]], str | None, np.ndarray | None]:
    if covariance is None:
        return [[None for _ in range(parameter_count)] for _ in range(parameter_count)], "optimizer_covariance_not_available", None
    matrix = np.asarray(covariance, dtype=float)
    if matrix.shape != (parameter_count, parameter_count):
        return [[None for _ in range(parameter_count)] for _ in range(parameter_count)], "optimizer_covariance_shape_mismatch", None
    serializable = [[_finite_float(matrix[row, column]) for column in range(parameter_count)] for row in range(parameter_count)]
    if not np.all(np.isfinite(matrix)):
        return serializable, "optimizer_covariance_contains_non_finite_values", matrix
    if not np.allclose(matrix, matrix.T, rtol=1e-10, atol=1e-12):
        return serializable, "optimizer_covariance_not_symmetric", matrix
    return serializable, None, matrix


def _covariance_details(
    covariance: np.ndarray | None,
    parameter_count: int,
) -> tuple[list[list[float | None]], str | None, list[list[float | None]], str | None, float | None, str | None, float | None, str | None, list[float | None]]:
    serializable_covariance, covariance_reason, matrix = _safe_covariance(covariance, parameter_count)
    correlations: list[list[float | None]] = [[None for _ in range(parameter_count)] for _ in range(parameter_count)]
    correlation_reason: str | None = covariance_reason
    condition_number: float | None = None
    condition_reason: str | None = covariance_reason
    max_abs_correlation: float | None = None
    max_correlation_reason: str | None = covariance_reason
    stderr: list[float | None] = [None for _ in range(parameter_count)]

    if matrix is None or not np.all(np.isfinite(matrix)):
        return (
            serializable_covariance,
            covariance_reason,
            correlations,
            correlation_reason,
            condition_number,
            condition_reason,
            max_abs_correlation,
            max_correlation_reason,
            stderr,
        )

    for index, variance in enumerate(np.diag(matrix)):
        if variance < 0.0:
            covariance_reason = covariance_reason or "optimizer_covariance_has_negative_variance"
            continue
        with np.errstate(over="ignore", invalid="ignore"):
            stderr[index] = _finite_float(np.sqrt(variance))

    try:
        correlations = covariance_to_correlation(matrix)
        correlation_reason = None
    except ValueError as exc:
        correlation_reason = f"covariance_correlation_unavailable:{exc}"

    try:
        condition_number = _finite_float(np.linalg.cond(matrix))
        if condition_number is None:
            condition_reason = "non_finite_covariance_condition_number"
        else:
            condition_reason = None
    except np.linalg.LinAlgError as exc:
        condition_reason = f"covariance_condition_number_unavailable:{exc}"

    coefficients = [
        abs(float(value))
        for row_index, row in enumerate(correlations)
        for column_index, value in enumerate(row)
        if row_index != column_index and value is not None and np.isfinite(value)
    ]
    if coefficients:
        max_abs_correlation = float(max(coefficients))
        max_correlation_reason = None
    else:
        max_correlation_reason = correlation_reason or "no_finite_off_diagonal_parameter_correlation"

    return (
        serializable_covariance,
        covariance_reason,
        correlations,
        correlation_reason,
        condition_number,
        condition_reason,
        max_abs_correlation,
        max_correlation_reason,
        stderr,
    )


def _identifiability(
    *,
    converged: bool,
    parameter_at_bounds: Mapping[str, bool],
    covariance_reason: str | None,
    correlation_reason: str | None,
    condition_number: float | None,
    max_abs_correlation: float | None,
) -> tuple[str, str | None]:
    """Classify identifiability independently from optimizer convergence.

    ``weak`` starts at |rho| >= 0.95 or cond(cov) >= 1e8.  ``non_identifiable``
    starts at |rho| >= 0.995, cond(cov) >= 1e12, or unavailable covariance
    information.  Bound hits are weak evidence even when covariance is finite.
    """

    if not converged:
        return "non_identifiable", "fit_not_converged"
    if covariance_reason is not None or correlation_reason is not None:
        return "non_identifiable", covariance_reason or correlation_reason
    if condition_number is None:
        return "non_identifiable", "covariance_condition_number_not_available"
    if max_abs_correlation is None:
        return "non_identifiable", "parameter_correlation_not_available"
    if (
        condition_number >= IDENTIFIABILITY_NON_IDENTIFIABLE_CONDITION_NUMBER
        or max_abs_correlation >= IDENTIFIABILITY_NON_IDENTIFIABLE_CORRELATION
    ):
        return "non_identifiable", "near_singular_parameter_covariance"
    if (
        condition_number >= IDENTIFIABILITY_WEAK_CONDITION_NUMBER
        or max_abs_correlation >= IDENTIFIABILITY_WEAK_CORRELATION
        or any(parameter_at_bounds.values())
    ):
        return "weak", "strong_parameter_correlation_or_ill_conditioning"
    return "strong", None


def _legacy_parameter_dict(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Keep the legacy named-parameter result while complete rows are added."""

    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        low = row.get("ci95_low")
        high = row.get("ci95_high")
        result[str(row["name"])] = {
            "value": row.get("value"),
            "stderr": row.get("stderr"),
            "ci95": None if low is None or high is None else [low, high],
            "unit": row.get("unit", ""),
        }
    return result


def _parameter_rows(
    *,
    names: Sequence[str],
    values: Sequence[Any],
    units: Mapping[str, str],
    initial: Sequence[Any],
    lower: Sequence[float],
    upper: Sequence[float],
    stderr: Sequence[Any],
    converged: bool,
    covariance_reason: str | None,
) -> list[dict[str, Any]]:
    rows = parameter_records(
        list(names),
        list(values),
        units=units,
        initial=list(initial),
        bounds=(list(lower), list(upper)),
        stderr=list(stderr),
    )
    for row in rows:
        row["reason"] = None if row["value"] is not None else ("fit_not_converged" if not converged else "non_finite_fitted_parameter")
        row["uncertainty_reason"] = None if row["stderr"] is not None else (covariance_reason or "uncertainty_not_available")
    return rows


def _residual_rows_with_indices(
    indices: np.ndarray,
    q: np.ndarray,
    observed: np.ndarray,
    fitted: np.ndarray,
    sigma: np.ndarray | None,
) -> list[dict[str, Any]]:
    rows = build_residual_rows(q, observed, fitted, sigma=sigma)
    for index, row in zip(indices, rows):
        row["original_index"] = int(index)
    return rows


def _fit_table(residual_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "q": row.get("q"),
            "I_observed": row.get("observed"),
            "I_fit": row.get("fitted"),
            "residual": row.get("residual"),
        }
        for row in residual_rows
    ]


def _base_result(
    *,
    curve: CurveData,
    q_range: tuple[float, float],
    model_name: str,
    initial_parameters: Mapping[str, Any] | None,
    fit_background: bool,
    results: dict[str, Any],
    checks: list[dict[str, Any]],
    warnings: list[str],
) -> AnalysisResult:
    spec = MODEL_SPECS.get(model_name)
    assumptions = [] if spec is None else spec.assumptions
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    merged = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_SHAPE_FIT,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Shape-model parameters are conditional on the selected model, q range, background handling, and sample assumptions.",
            "A good residual does not prove uniqueness; compare plausible models and inspect residuals.",
            "Derived geometric quantities are conditional on the same model and are not unique morphology proof.",
        ],
        export_tables=results.get("export_tables", {}),
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type=f"shape_fit:{model_name}",
        q_range=q_range,
        parameters={"model_name": model_name, "initial_parameters": dict(initial_parameters or {}), "fit_background": bool(fit_background)},
        results=merged,
        warnings=[*warnings, *warning_messages_from_checks(checks)],
    )


def fit_shape_model_complete(
    curve: CurveData,
    q_range: tuple[float, float],
    model_name: str,
    *,
    initial_parameters: Mapping[str, Any] | None = None,
    fit_background: bool = True,
    warm_start: Mapping[str, Any] | None = None,
    batch_median_parameters: Mapping[str, Any] | None = None,
) -> AnalysisResult:
    """Fit one shape model with diagnostics, retries, and derived quantities.

    Attempts are evaluated in this fixed order: a supplied warm start, a
    supplied batch-median start, curve-aware defaults, then two deterministic
    jittered default starts. The valid attempt with the smallest finite AICc is
    selected; only when every AICc is unavailable does RMSE provide the
    documented fallback. This is the same contract used by batch fitting.
    """

    if model_name not in MODEL_FUNCTIONS or model_name not in MODEL_SPECS:
        raise ValueError(f"Unsupported shape model: {model_name}")
    spec = MODEL_SPECS[model_name]
    q, observed, sigma, original_indices, excluded_rows, warnings = _select_curve_data(curve, q_range)
    names = spec.parameter_names
    lower = [float(value) for value in spec.lower_bounds]
    upper = [float(value) for value in spec.upper_bounds]
    defaults = _inside_bounds(_initial_from_curve(curve, model_name), lower, upper)
    if not fit_background and "background" in names:
        background_index = names.index("background")
        defaults[background_index] = 0.0
        lower[background_index] = -1e-300
        upper[background_index] = 1e-300
        defaults = _inside_bounds(defaults, lower, upper)

    attempt_vectors: list[tuple[str, np.ndarray]] = []
    combined_warm: dict[str, Any] = {}
    if isinstance(initial_parameters, Mapping):
        combined_warm.update(initial_parameters)
    if isinstance(warm_start, Mapping):
        combined_warm.update(warm_start)
    if combined_warm:
        attempt_vectors.append(("warm_start", _apply_parameter_overrides(defaults, names, combined_warm, lower, upper)))
    if isinstance(batch_median_parameters, Mapping) and batch_median_parameters:
        attempt_vectors.append(
            ("batch_median", _apply_parameter_overrides(defaults, names, batch_median_parameters, lower, upper))
        )
    attempt_vectors.append(("defaults", defaults.copy()))
    attempt_vectors.extend(
        (f"jittered_multistart_{index + 1}", vector)
        for index, vector in enumerate(_deterministic_jittered_vectors(defaults, lower, upper, model_name=model_name))
    )

    enough_points = q.size >= len(names) + 3
    attempts: list[dict[str, Any]] = []
    successful: list[tuple[int, dict[str, Any]]] = []
    if not enough_points:
        for source, initial in attempt_vectors:
            attempts.append(
                _attempt_record(
                    source=source,
                    names=names,
                    initial=initial,
                    status="not_attempted",
                    error="insufficient_selected_points",
                )
            )
    else:
        for source, initial in attempt_vectors:
            record, candidate = _run_attempt(
                model_name=model_name,
                names=names,
                q=q,
                observed=observed,
                sigma=sigma,
                lower=lower,
                upper=upper,
                initial=initial,
                source=source,
            )
            attempts.append(record)
            if candidate is not None:
                successful.append((len(attempts) - 1, candidate))

    selected_attempt_index: int | None = None
    selected: dict[str, Any] | None = None
    if successful:
        finite_aicc_attempts = [
            item for item in successful if _finite_float(item[1]["quality"].get("AICc")) is not None
        ]
        if finite_aicc_attempts:
            selected_attempt_index, selected = min(
                finite_aicc_attempts,
                key=lambda item: _aicc_sort_key(item[1], item[0]),
            )
        else:
            selected_attempt_index, selected = min(
                successful,
                key=lambda item: _rmse_sort_key(item[1], item[0]),
            )
        attempts[selected_attempt_index]["selected"] = True
        for index, attempt in enumerate(attempts):
            if index != selected_attempt_index:
                attempt["selected"] = False
    else:
        for attempt in attempts:
            attempt["selected"] = False

    converged = selected is not None
    if selected is None:
        fitted = np.full(q.shape, np.nan, dtype=float)
        fit_quality = fit_diagnostics(np.array([], dtype=float), np.array([], dtype=float), parameter_count=len(names))
        fitted_values: list[Any] = [None for _ in names]
        covariance = None
        error_message = (
            "insufficient_selected_points"
            if not enough_points
            else next((attempt["error"] for attempt in attempts if attempt.get("error")), "all_fit_attempts_failed")
        )
    else:
        fitted = selected["fitted"]
        fit_quality = selected["quality"]
        fitted_values = selected["parameters"].tolist()
        covariance = selected["covariance"]
        error_message = None

    (
        covariance_rows,
        covariance_reason,
        correlation_rows,
        correlation_reason,
        condition_number,
        condition_reason,
        max_abs_correlation,
        max_correlation_reason,
        stderr,
    ) = _covariance_details(covariance, len(names))
    units = _parameter_units_for_curve(spec.units, curve)
    parameter_rows = _parameter_rows(
        names=names,
        values=fitted_values,
        units=units,
        initial=defaults,
        lower=lower,
        upper=upper,
        stderr=stderr,
        converged=converged,
        covariance_reason=covariance_reason,
    )
    legacy_parameters = _legacy_parameter_dict(parameter_rows)
    parameter_at_bounds = {row["name"]: bool(row["bound_hit"]) for row in parameter_rows}
    identifiability_status, identifiability_reason = _identifiability(
        converged=converged,
        parameter_at_bounds=parameter_at_bounds,
        covariance_reason=covariance_reason,
        correlation_reason=correlation_reason,
        condition_number=condition_number,
        max_abs_correlation=max_abs_correlation,
    )
    residual_rows = _residual_rows_with_indices(original_indices, q, observed, fitted, sigma)
    derived = derived_model_parameters(model_name, legacy_parameters, curve.q_unit)
    fit_table = _fit_table(residual_rows)

    r2 = fit_quality.get("R2")
    checks = [
        validity_check(
            "enough_points",
            enough_points,
            severity="error",
            message="Model fit needs more data points than fitted parameters.",
            value=int(q.size),
            threshold=len(names) + 3,
        ),
        validity_check("fit_converged", converged, severity="error", message=error_message or "Fit did not converge."),
        validity_check(
            "fit_quality_r2",
            r2 is not None and r2 >= 0.9,
            severity="warning",
            message="Fit R2 is below 0.90.",
            value=r2,
            threshold=0.9,
        ),
        validity_check(
            "parameters_not_at_bounds",
            not any(parameter_at_bounds.values()),
            severity="warning",
            message="One or more fitted parameters is at a bound.",
            value=parameter_at_bounds,
        ),
        validity_check(
            "identifiability",
            identifiability_status != "non_identifiable",
            severity="error" if identifiability_status == "non_identifiable" else "warning",
            message=identifiability_reason or "Parameter covariance is identifiable within configured thresholds.",
            value=identifiability_status,
            threshold={
                "weak_abs_correlation": IDENTIFIABILITY_WEAK_CORRELATION,
                "non_identifiable_abs_correlation": IDENTIFIABILITY_NON_IDENTIFIABLE_CORRELATION,
                "weak_condition_number": IDENTIFIABILITY_WEAK_CONDITION_NUMBER,
                "non_identifiable_condition_number": IDENTIFIABILITY_NON_IDENTIFIABLE_CONDITION_NUMBER,
            },
        ),
    ]
    results = {
        "model_name": model_name,
        "model_description": spec.description,
        "parameters": legacy_parameters,
        "parameter_records": parameter_rows,
        "parameter_at_bounds": parameter_at_bounds,
        "fit_points": int(q.size),
        "excluded_points": int(len(excluded_rows)),
        "excluded_rows": excluded_rows,
        "R2": fit_quality.get("R2"),
        "AIC": fit_quality.get("AIC"),
        "AICc": fit_quality.get("AICc"),
        "BIC": fit_quality.get("BIC"),
        "reduced_chi_square": fit_quality.get("reduced_chi_square"),
        "rss": fit_quality.get("rss"),
        "fit_quality": fit_quality,
        "covariance": covariance_rows,
        "covariance_reason": covariance_reason,
        "parameter_correlation": correlation_rows,
        "parameter_correlation_reason": correlation_reason,
        "covariance_condition_number": condition_number,
        "covariance_condition_number_reason": condition_reason,
        "max_abs_parameter_correlation": max_abs_correlation,
        "max_abs_parameter_correlation_reason": max_correlation_reason,
        "identifiability_status": identifiability_status,
        "identifiability_reason": identifiability_reason,
        "identifiability_thresholds": {
            "weak_abs_correlation": IDENTIFIABILITY_WEAK_CORRELATION,
            "non_identifiable_abs_correlation": IDENTIFIABILITY_NON_IDENTIFIABLE_CORRELATION,
            "weak_condition_number": IDENTIFIABILITY_WEAK_CONDITION_NUMBER,
            "non_identifiable_condition_number": IDENTIFIABILITY_NON_IDENTIFIABLE_CONDITION_NUMBER,
        },
        "fit_q": _safe_float_list(q),
        "fit_I": _safe_float_list(fitted),
        "residuals": [row["residual"] for row in residual_rows],
        "residual_rows": residual_rows,
        "derived_parameters": derived,
        "attempts": attempts,
        "selected_attempt_index": selected_attempt_index,
        "converged": converged,
        "error_message": error_message,
        "error_audit": {
            "weighted_fit": sigma is not None,
            "weighting_policy": "all_selected_positive_finite_errors_required",
            "sigma_is_absolute": True if sigma is not None else None,
            "max_function_evaluations_per_attempt": MAX_FUNCTION_EVALUATIONS,
            "attempt_selection_policy": "all_candidates_minimum_AICc_then_RMSE",
        },
        "export_tables": {
            EXPORT_TABLE_FIT_CURVES: fit_table,
            "residual_rows": residual_rows,
            "parameter_records": parameter_rows,
            "fit_attempts": attempts,
            "derived_parameters": [dict(name=name, **record) for name, record in derived.items()],
        },
    }
    return _base_result(
        curve=curve,
        q_range=q_range,
        model_name=model_name,
        initial_parameters=initial_parameters,
        fit_background=fit_background,
        results=results,
        checks=checks,
        warnings=warnings,
    )


def _failed_model_result(
    curve: CurveData,
    q_range: tuple[float, float],
    model_name: str,
    error: Exception | str,
    *,
    initial_parameters: Mapping[str, Any] | None = None,
    fit_background: bool = True,
) -> AnalysisResult:
    """Build a schema-complete failed result so batch fitting can continue."""

    spec = MODEL_SPECS.get(model_name)
    names = [] if spec is None else spec.parameter_names
    lower = [] if spec is None else spec.lower_bounds
    upper = [] if spec is None else spec.upper_bounds
    units = {} if spec is None else _parameter_units_for_curve(spec.units, curve)
    reason = str(error)
    rows = _parameter_rows(
        names=names,
        values=[None for _ in names],
        units=units,
        initial=[None for _ in names],
        lower=lower,
        upper=upper,
        stderr=[None for _ in names],
        converged=False,
        covariance_reason="batch_model_failure",
    )
    quality = fit_diagnostics(np.array([], dtype=float), np.array([], dtype=float), parameter_count=len(names))
    attempts = [
        {
            "source": "batch_isolation",
            "status": "failed",
            "error": reason,
            "initial_vector": {name: None for name in names},
            "fit_quality": {},
            "optimizer_warnings": [],
            "selected": False,
        }
    ]
    checks = [
        validity_check("fit_converged", False, severity="error", message=reason),
        validity_check("identifiability", False, severity="error", message="fit_not_converged"),
    ]
    results = {
        "model_name": model_name,
        "model_description": None if spec is None else spec.description,
        "parameters": _legacy_parameter_dict(rows),
        "parameter_records": rows,
        "parameter_at_bounds": {name: False for name in names},
        "fit_points": 0,
        "excluded_points": 0,
        "excluded_rows": [],
        "R2": None,
        "AIC": None,
        "AICc": None,
        "BIC": None,
        "reduced_chi_square": None,
        "rss": None,
        "fit_quality": quality,
        "covariance": [[None for _ in names] for _ in names],
        "covariance_reason": "batch_model_failure",
        "parameter_correlation": [[None for _ in names] for _ in names],
        "parameter_correlation_reason": "batch_model_failure",
        "covariance_condition_number": None,
        "covariance_condition_number_reason": "batch_model_failure",
        "max_abs_parameter_correlation": None,
        "max_abs_parameter_correlation_reason": "batch_model_failure",
        "identifiability_status": "non_identifiable",
        "identifiability_reason": "fit_not_converged",
        "identifiability_thresholds": {
            "weak_abs_correlation": IDENTIFIABILITY_WEAK_CORRELATION,
            "non_identifiable_abs_correlation": IDENTIFIABILITY_NON_IDENTIFIABLE_CORRELATION,
            "weak_condition_number": IDENTIFIABILITY_WEAK_CONDITION_NUMBER,
            "non_identifiable_condition_number": IDENTIFIABILITY_NON_IDENTIFIABLE_CONDITION_NUMBER,
        },
        "fit_q": [],
        "fit_I": [],
        "residuals": [],
        "residual_rows": [],
        "derived_parameters": {} if spec is None else derived_model_parameters(model_name, _legacy_parameter_dict(rows), curve.q_unit),
        "attempts": attempts,
        "selected_attempt_index": None,
        "converged": False,
        "error_message": reason,
        "error_audit": {"weighted_fit": False, "weighting_policy": "not_run", "sigma_is_absolute": None},
        "export_tables": {
            EXPORT_TABLE_FIT_CURVES: [],
            "residual_rows": [],
            "parameter_records": rows,
            "fit_attempts": attempts,
            "derived_parameters": [],
        },
    }
    return _base_result(
        curve=curve,
        q_range=q_range,
        model_name=model_name,
        initial_parameters=initial_parameters,
        fit_background=fit_background,
        results=results,
        checks=checks,
        warnings=[f"Model-specific failure was isolated: {reason}"],
    )


def _model_specific_parameters(source: Mapping[str, Any] | None, model_name: str) -> Mapping[str, Any] | None:
    """Accept either one model mapping or a model-name-to-mapping batch mapping."""

    if not isinstance(source, Mapping):
        return None
    nested = source.get(model_name)
    if isinstance(nested, Mapping):
        return nested
    return source


def fit_all_allowed_models(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    allowed_models: Sequence[str] | None = None,
    initial_parameters_by_model: Mapping[str, Any] | None = None,
    warm_starts: Mapping[str, Any] | None = None,
    batch_median_parameters: Mapping[str, Any] | None = None,
    fit_background: bool = True,
) -> dict[str, AnalysisResult]:
    """Fit every requested registered model, isolating failures per model.

    The default request contains all ten names in :data:`MODEL_SPECS`.  One
    failed optimizer cannot stop later models from returning their own complete
    ``AnalysisResult`` records. Every model uses the same complete retry order,
    optimizer budget, and AICc/RMSE selection contract as
    :func:`fit_shape_model_complete`.
    """

    names = list(MODEL_SPECS) if allowed_models is None else [str(name) for name in allowed_models]
    results: dict[str, AnalysisResult] = {}
    for model_name in names:
        try:
            results[model_name] = fit_shape_model_complete(
                curve,
                q_range,
                model_name,
                initial_parameters=_model_specific_parameters(initial_parameters_by_model, model_name),
                warm_start=_model_specific_parameters(warm_starts, model_name),
                batch_median_parameters=_model_specific_parameters(batch_median_parameters, model_name),
                fit_background=fit_background,
            )
        except Exception as exc:  # Preserve all later model attempts in batch mode.
            results[model_name] = _failed_model_result(
                curve,
                q_range,
                model_name,
                exc,
                initial_parameters=_model_specific_parameters(initial_parameters_by_model, model_name),
                fit_background=fit_background,
            )
    return results


def fit_shape_model(
    curve: CurveData,
    q_range: tuple[float, float],
    model_name: str,
    *,
    initial_parameters: Mapping[str, Any] | None = None,
    fit_background: bool = True,
) -> AnalysisResult:
    """Backward-compatible entry point delegated to the complete fit path."""

    return fit_shape_model_complete(
        curve,
        q_range,
        model_name,
        initial_parameters=initial_parameters,
        fit_background=fit_background,
    )


__all__ = [
    "DERIVED_PARAMETER_BUILDERS",
    "derived_model_parameters",
    "fit_all_allowed_models",
    "fit_shape_model",
    "fit_shape_model_complete",
]
