from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from app.core.analysis_schema import EXPORT_TABLE_FIT_CURVES, RESULT_GROUP_SHAPE_FIT, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks
from app.core.shape_models import MODEL_FUNCTIONS, MODEL_SPECS, evaluate_model


def _initial_from_curve(curve: CurveData, spec_name: str) -> list[float]:
    spec = MODEL_SPECS[spec_name]
    values = list(spec.initial_values)
    finite_i = curve.intensity[np.isfinite(curve.intensity)]
    scale_guess = float(np.nanmax(finite_i) - np.nanmin(finite_i)) if finite_i.size else 1.0
    background_guess = float(np.nanmin(finite_i)) if finite_i.size else 0.0
    if "scale" in spec.parameter_names:
        values[spec.parameter_names.index("scale")] = max(scale_guess, 1e-9)
    if "background" in spec.parameter_names:
        values[spec.parameter_names.index("background")] = background_guess
    if "q0" in spec.parameter_names and curve.q.size:
        q_valid = curve.q[np.isfinite(curve.q) & (curve.q > 0)]
        if q_valid.size:
            values[spec.parameter_names.index("q0")] = float(q_valid[np.argmax(curve.intensity[np.isfinite(curve.q) & (curve.q > 0)])])
    return values


def _parameter_dict(names: list[str], values: np.ndarray, errors: np.ndarray | None, units: dict[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for index, name in enumerate(names):
        stderr = None if errors is None or not np.isfinite(errors[index]) else float(errors[index])
        value = float(values[index])
        payload[name] = {
            "value": value,
            "stderr": stderr,
            "ci95": None if stderr is None else [value - 1.96 * stderr, value + 1.96 * stderr],
            "unit": units.get(name, ""),
        }
    return payload


def fit_shape_model(
    curve: CurveData,
    q_range: tuple[float, float],
    model_name: str,
    *,
    initial_parameters: dict[str, float] | None = None,
    fit_background: bool = True,
) -> AnalysisResult:
    if model_name not in MODEL_FUNCTIONS:
        raise ValueError(f"Unsupported shape model: {model_name}")
    spec = MODEL_SPECS[model_name]
    mask = (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & (curve.q >= q_range[0])
        & (curve.q <= q_range[1])
    )
    q = curve.q[mask]
    y = curve.intensity[mask]
    sigma = None
    if curve.error is not None:
        err = curve.error[mask]
        if np.all(np.isfinite(err) & (err > 0)):
            sigma = err

    p0 = _initial_from_curve(curve, model_name)
    for key, value in (initial_parameters or {}).items():
        if key in spec.parameter_names:
            p0[spec.parameter_names.index(key)] = float(value)
    lower = list(spec.lower_bounds)
    upper = list(spec.upper_bounds)
    if not fit_background and "background" in spec.parameter_names:
        idx = spec.parameter_names.index("background")
        p0[idx] = 0.0
        lower[idx] = -1e-300
        upper[idx] = 1e-300

    converged = False
    error_message = None
    popt = np.asarray(p0, dtype=float)
    pcov = np.full((len(p0), len(p0)), np.nan)
    fitted = np.full_like(q, np.nan, dtype=float)
    residuals = np.full_like(q, np.nan, dtype=float)
    enough_points = q.size >= len(p0) + 3
    if enough_points:
        try:
            popt, pcov = curve_fit(
                MODEL_FUNCTIONS[model_name],
                q,
                y,
                p0=p0,
                bounds=(lower, upper),
                sigma=sigma,
                absolute_sigma=sigma is not None,
                maxfev=20000,
            )
            fitted = evaluate_model(model_name, q, list(popt))
            residuals = y - fitted
            converged = True
        except Exception as exc:  # scipy reports many model-specific ValueErrors
            error_message = str(exc)

    rss = float(np.nansum(residuals**2)) if converged else None
    tss = float(np.nansum((y - np.nanmean(y)) ** 2)) if y.size else None
    r2 = None if not converged or not tss or tss == 0 else float(1.0 - rss / tss)
    n = int(q.size)
    k = len(p0)
    aic = None
    bic = None
    reduced_chi_square = None
    if converged and rss is not None and n > k:
        variance = max(rss / n, 1e-300)
        aic = float(n * np.log(variance) + 2 * k)
        bic = float(n * np.log(variance) + k * np.log(n))
        if sigma is not None:
            reduced_chi_square = float(np.sum((residuals / sigma) ** 2) / max(1, n - k))
        else:
            reduced_chi_square = float(rss / max(1, n - k))
    perr = None
    if converged and np.all(np.isfinite(pcov)):
        perr = np.sqrt(np.maximum(np.diag(pcov), 0.0))
    at_bounds = {}
    for index, name in enumerate(spec.parameter_names):
        at_lower = np.isfinite(lower[index]) and abs(popt[index] - lower[index]) <= max(1e-9, abs(lower[index]) * 1e-6)
        at_upper = np.isfinite(upper[index]) and abs(popt[index] - upper[index]) <= max(1e-9, abs(upper[index]) * 1e-6)
        at_bounds[name] = bool(at_lower or at_upper)

    checks = [
        validity_check("enough_points", enough_points, severity="error", message="Model fit needs more data points than fitted parameters.", value=n, threshold=k + 3),
        validity_check("fit_converged", converged, severity="error", message=error_message or "Fit did not converge."),
        validity_check("fit_quality_r2", r2 is not None and r2 >= 0.9, severity="warning", message="Fit R2 is below 0.90.", value=r2, threshold=0.9),
        validity_check("parameters_not_at_bounds", not any(at_bounds.values()), severity="warning", message="One or more fitted parameters is at a bound.", value=at_bounds),
    ]
    label, score = reliability_from_checks(checks, assumptions=spec.assumptions)
    fit_table = [
        {"q": float(qv), "I_observed": float(yv), "I_fit": float(fv), "residual": float(rv)}
        for qv, yv, fv, rv in zip(q, y, fitted, residuals)
    ]
    results = {
        "model_name": model_name,
        "model_description": spec.description,
        "parameters": _parameter_dict(spec.parameter_names, popt, perr, spec.units),
        "parameter_at_bounds": at_bounds,
        "fit_points": n,
        "R2": r2,
        "AIC": aic,
        "BIC": bic,
        "reduced_chi_square": reduced_chi_square,
        "rss": rss,
        "fit_q": q.tolist(),
        "fit_I": fitted.tolist(),
        "residuals": residuals.tolist(),
        "converged": converged,
        "error_message": error_message,
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_SHAPE_FIT,
        reliability_label=label,
        reliability_score=score,
        assumptions=spec.assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Shape-model parameters are conditional on the selected model, q range, background handling, and sample assumptions.",
            "A good residual does not prove uniqueness; compare plausible models and inspect residuals.",
        ],
        export_tables={EXPORT_TABLE_FIT_CURVES: fit_table},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type=f"shape_fit:{model_name}",
        q_range=q_range,
        parameters={"model_name": model_name, "initial_parameters": initial_parameters or {}, "fit_background": fit_background},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )
