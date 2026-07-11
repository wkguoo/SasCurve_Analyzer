"""Production dispatch from the batch registry to read-only SAS analyses.

The runner is intentionally a small boundary between the authoritative method
registry and the existing numerical functions.  It never changes ``CurveData``
or source files.  Every scheduled method produces an ``AnalysisEnvelope`` with
all registered metric names present, including explicit null values when a
quantity is not available for that curve.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from app.core.analysis_schema import RELIABILITY_ASSUMPTION_DEPENDENT, RELIABILITY_INVALID
from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig, ParameterValue
from app.core.correlation import compute_correlation_function
from app.core.data_model import AnalysisResult, CurveData
from app.core.derived_data import build_curve_derived_table
from app.core.extended_features import analyze_oscillations, detect_crossovers, detect_shoulders, extended_integrals
from app.core.feature_extraction import detect_peaks
from app.core.invariant_analysis import invariant_with_extrapolation
from app.core.lamellar_analysis import lamellar_analysis
from app.core.metric_registry import METHOD_REGISTRY, applicable_method_ids
from app.core.model_fitting import fit_all_allowed_models
from app.core.model_free import guinier_analysis, kratky_metrics, local_slope, porod_metrics, power_law_analysis
from app.core.porod_analysis import porod_deep_analysis
from app.core.pr_analysis import compute_pr
from app.core.region_scanners import curve_quality_metrics


Handler = Callable[[CurveData, tuple[float, float], AutoBatchConfig], AnalysisResult | list[AnalysisResult]]


class BatchConfigurationError(RuntimeError):
    """Raised before a batch starts when its registry dispatch is incomplete."""


def _finite_float(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _native(value: Any) -> Any:
    """Return recursive Python-native values without exporting NaN or infinity."""

    if isinstance(value, np.ndarray):
        return [_native(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_native(item) for item in value]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    return value


def _normalized_q_range(value: object) -> tuple[float, float] | None:
    if not isinstance(value, tuple) or len(value) != 2:
        return None
    q_low = _finite_float(value[0])
    q_high = _finite_float(value[1])
    if q_low is None or q_high is None or q_low >= q_high:
        return None
    return q_low, q_high


def _status_from_text(value: Any, *, default: AnalysisStatus) -> AnalysisStatus:
    if isinstance(value, AnalysisStatus):
        return value
    if isinstance(value, str):
        aliases = {
            "available": AnalysisStatus.SUCCESS,
            "success": AnalysisStatus.SUCCESS,
            "assumption_dependent": AnalysisStatus.ASSUMPTION_DEPENDENT,
            "not_applicable": AnalysisStatus.NOT_APPLICABLE,
            "not_requested": AnalysisStatus.NOT_APPLICABLE,
            "missing_prerequisite": AnalysisStatus.MISSING_PREREQUISITE,
            "invalid_value": AnalysisStatus.INVALID,
            "invalid": AnalysisStatus.INVALID,
            "fit_failed": AnalysisStatus.FIT_FAILED,
            "cancelled": AnalysisStatus.CANCELLED,
        }
        return aliases.get(value, default)
    return default


def _metric_reason(results: Mapping[str, Any], metric_name: str, default: str) -> str:
    reason = results.get(f"{metric_name}_invalid_reason")
    if reason is None:
        reason = results.get(f"{metric_name}_reason")
    if reason is None:
        reason = default
    return str(reason)


def _shape_metric_values(result: AnalysisResult) -> dict[str, Any]:
    """Flatten the complete-fit summary into the registry's batch fields."""

    records = result.results.get("parameter_records")
    rows = [row for row in records if isinstance(row, Mapping)] if isinstance(records, Sequence) else []
    parameter_values = {str(row.get("name")): _native(row.get("value")) for row in rows if row.get("name") is not None}
    parameter_stderr = {str(row.get("name")): _native(row.get("stderr")) for row in rows if row.get("name") is not None}
    parameter_ci_low = {str(row.get("name")): _native(row.get("ci95_low")) for row in rows if row.get("name") is not None}
    parameter_ci_high = {str(row.get("name")): _native(row.get("ci95_high")) for row in rows if row.get("name") is not None}
    parameter_bounds = {str(row.get("name")): bool(row.get("bound_hit")) for row in rows if row.get("name") is not None}
    return {
        "model_name": result.results.get("model_name") or result.parameters.get("model_name"),
        "parameter_name": list(parameter_values),
        "parameter_value": parameter_values,
        "stderr": parameter_stderr,
        "ci95_low": parameter_ci_low,
        "ci95_high": parameter_ci_high,
        "bound_hit": parameter_bounds,
        "AICc": result.results.get("AICc"),
        "BIC": result.results.get("BIC"),
        "rank": result.results.get("rank"),
    }


def _metric_value(result: AnalysisResult, method_id: str, metric_name: str) -> Any:
    if method_id == "shape_models":
        return _shape_metric_values(result).get(metric_name)
    if metric_name in result.results:
        return result.results[metric_name]
    if metric_name in result.parameters:
        return result.parameters[metric_name]
    return None


def _parameter_values(result: AnalysisResult, method_id: str) -> list[ParameterValue]:
    values: list[ParameterValue] = []
    for metric in METHOD_REGISTRY[method_id].metrics:
        raw_value = _native(_metric_value(result, method_id, metric.name))
        default_status = AnalysisStatus.SUCCESS if raw_value is not None else AnalysisStatus.MISSING_PREREQUISITE
        result_status = result.results.get(f"{metric.name}_status")
        status = _status_from_text(result_status, default=default_status)
        reason = None
        if raw_value is None:
            reason = _metric_reason(
                result.results,
                metric.name,
                f"{metric.name} was not available from this registered analysis result.",
            )
        values.append(
            ParameterValue(
                name=metric.name,
                value=raw_value,
                unit=metric.unit_role,
                status=status,
                invalid_reason=reason,
            )
        )
    return values


def _tables(result: AnalysisResult) -> dict[str, list[dict[str, Any]]]:
    raw_tables = result.results.get("export_tables", {})
    if not isinstance(raw_tables, Mapping):
        return {}
    output: dict[str, list[dict[str, Any]]] = {}
    for name, rows in raw_tables.items():
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            continue
        output[str(name)] = [
            _native(row) if isinstance(row, Mapping) else {"value": _native(row)}
            for row in rows
        ]
    return output


def _result_status(result: AnalysisResult) -> AnalysisStatus:
    results = result.results
    if results.get("converged") is False:
        return AnalysisStatus.FIT_FAILED
    status = _status_from_text(results.get("analysis_status"), default=AnalysisStatus.SUCCESS)
    if status is not AnalysisStatus.SUCCESS:
        return status
    label = results.get("reliability_label")
    if label == RELIABILITY_ASSUMPTION_DEPENDENT or label == "assumption_dependent":
        return AnalysisStatus.ASSUMPTION_DEPENDENT
    if label == RELIABILITY_INVALID or label == "invalid":
        return AnalysisStatus.INVALID
    return AnalysisStatus.SUCCESS


def _reliability(result: AnalysisResult, status: AnalysisStatus) -> tuple[str, float]:
    default_label = (
        RELIABILITY_INVALID
        if status in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID}
        else "medium"
    )
    label = str(result.results.get("reliability_label", default_label))
    if status in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID} and label not in {
        RELIABILITY_INVALID,
        "invalid",
    }:
        label = RELIABILITY_INVALID
    score = _finite_float(result.results.get("reliability_score"))
    return label, 0.0 if score is None else max(0.0, min(1.0, score))


def _fit_quality_for_envelope(result: AnalysisResult) -> dict[str, Any]:
    raw = result.results.get("fit_quality", {})
    quality = _native(raw) if isinstance(raw, Mapping) else {}
    if not isinstance(quality, dict):
        quality = {}
    for name in ("AICc", "BIC", "R2"):
        if name not in quality and name in result.results:
            quality[name] = _native(result.results.get(name))
    if "converged" in result.results:
        quality["converged"] = bool(result.results["converged"])
    if "uncertainty_score" not in quality:
        records = result.results.get("parameter_records", [])
        relative_errors: list[float] = []
        if isinstance(records, Sequence):
            for row in records:
                if not isinstance(row, Mapping):
                    continue
                value = _finite_float(row.get("value"))
                stderr = _finite_float(row.get("stderr"))
                if value is not None and value != 0.0 and stderr is not None and stderr >= 0.0:
                    relative_errors.append(abs(stderr / value))
        if relative_errors:
            quality["uncertainty_score"] = float(np.median(relative_errors))
    return quality


def _envelope_invalid_reason(result: AnalysisResult, status: AnalysisStatus, score: float) -> str | None:
    if status not in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID}:
        return None
    if result.results.get("error_message"):
        return str(result.results.get("error_message"))
    if status is AnalysisStatus.FIT_FAILED:
        return "Fit did not converge or failed numerical checks."
    return f"reliability_label is invalid (score={score:.3f})."


def _envelope_from_result(curve: CurveData, method_id: str, result: AnalysisResult) -> AnalysisEnvelope:
    status = _result_status(result)
    label, score = _reliability(result, status)
    model_name = _shape_metric_values(result).get("model_name") if method_id == "shape_models" else None
    suffix = "" if model_name in (None, "") else f":{model_name}"
    warnings = [str(item) for item in result.warnings]
    result_warnings = result.results.get("warnings")
    if isinstance(result_warnings, Sequence) and not isinstance(result_warnings, (str, bytes)):
        warnings.extend(str(item) for item in result_warnings)
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}{suffix}",
        analysis_type=method_id,
        status=status,
        q_range=_normalized_q_range(result.q_range),
        parameters=_parameter_values(result, method_id),
        fit_quality=_fit_quality_for_envelope(result),
        tables=_tables(result),
        validity_checks=_native(result.results.get("validity_checks", [])) if isinstance(result.results.get("validity_checks"), list) else [],
        reliability_label=label,
        reliability_score=score,
        assumptions=[str(item) for item in result.results.get("assumptions", [])] if isinstance(result.results.get("assumptions"), list) else [],
        warnings=warnings,
        invalid_reason=_envelope_invalid_reason(result, status, score),
    )


def _blank_envelope(
    curve: CurveData,
    method_id: str,
    q_range: tuple[float, float] | None,
    *,
    status: AnalysisStatus,
    reason: str,
) -> AnalysisEnvelope:
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}",
        analysis_type=method_id,
        status=status,
        q_range=q_range,
        parameters=[
            ParameterValue(name=metric.name, value=None, unit=metric.unit_role, status=status, invalid_reason=reason)
            for metric in METHOD_REGISTRY[method_id].metrics
        ],
        reliability_label="invalid" if status in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID} else "low",
        reliability_score=0.0,
        warnings=[reason],
        invalid_reason=reason,
    )


def _result_with_values(
    curve: CurveData,
    analysis_type: str,
    q_range: tuple[float, float],
    values: Mapping[str, Any],
    *,
    warnings: Sequence[str] = (),
    tables: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    assumptions: Sequence[str] = (),
) -> AnalysisResult:
    results = dict(values)
    results.setdefault("reliability_label", "medium")
    results.setdefault("reliability_score", 0.5)
    results.setdefault("validity_checks", [])
    results.setdefault("assumptions", list(assumptions))
    results.setdefault("export_tables", dict(tables or {}))
    return AnalysisResult.create(
        curve=curve,
        analysis_type=analysis_type,
        q_range=q_range,
        results=results,
        warnings=[str(item) for item in warnings],
    )


def _run_data_quality(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    quality = curve_quality_metrics(curve, q_range)
    q_min = _finite_float(quality.get("q_min"))
    q_max = _finite_float(quality.get("q_max"))
    d_min = None if q_max is None or q_max <= 0.0 else _finite_float(2.0 * math.pi / q_max)
    d_max = None if q_min is None or q_min <= 0.0 else _finite_float(2.0 * math.pi / q_min)
    values = {
        "q_min": q_min,
        "q_max": q_max,
        "d_min": d_min,
        "d_max": d_max,
        "point_count": quality.get("data_points"),
        "I_min": quality.get("I_min"),
        "I_max": quality.get("I_max"),
        "dynamic_range": quality.get("dynamic_range"),
        "nan_count": quality.get("nan_points"),
        "negative_count": quality.get("negative_intensity_points"),
        "zero_count": quality.get("zero_intensity_points"),
        "duplicate_q_count": quality.get("duplicate_q_points"),
        "log_usable_points": quality.get("positive_log_points"),
    }
    return _result_with_values(curve, "data_quality", q_range, values)


def _run_derived_coordinates(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    derived = build_curve_derived_table(curve)
    rows = [_native(row) for row in derived.table.to_dict(orient="records")]
    values: dict[str, Any] = {}
    for metric in METHOD_REGISTRY["derived_coordinates"].metrics:
        values[metric.name] = None
        values[f"{metric.name}_status"] = "not_applicable"
        values[f"{metric.name}_invalid_reason"] = "Derived coordinates are available as a per-point table, not a single batch scalar."
    return _result_with_values(
        curve,
        "derived_coordinates",
        q_range,
        values,
        warnings=derived.warnings,
        tables={"derived_coordinates": rows},
    )


def _run_guinier(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    return guinier_analysis(curve, q_range)


def _run_power_law(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    return power_law_analysis(curve, q_range)


def _run_local_slope(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    source = local_slope(curve, q_range)
    values = dict(source.results)
    values["alpha_q"] = source.results.get("alpha")
    plateaus = source.results.get("plateaus")
    values["plateau_count"] = len(plateaus) if isinstance(plateaus, list) else None
    return _result_with_values(
        curve,
        "local_slope",
        q_range,
        values,
        warnings=source.warnings,
        tables=source.results.get("export_tables", {}),
        assumptions=source.results.get("assumptions", []),
    )


def _run_crossover(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    rows = detect_crossovers(curve.q[mask], curve.intensity[mask])
    primary = rows[0] if rows else {}
    values = {
        "crossover_q": primary.get("crossover_q"),
        "crossover_d": primary.get("crossover_d"),
        "slope_difference": primary.get("slope_difference"),
        "confidence": primary.get("confidence"),
    }
    return _result_with_values(curve, "crossover", q_range, values, warnings=rows.warnings, tables={"crossovers": list(rows)})


def _run_peaks(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    source = detect_peaks(curve, q_range)
    rows = source.results.get("peaks", [])
    primary = rows[0] if rows else {}
    values = dict(source.results)
    values.update(
        {
            "q_star": primary.get("peak_q"),
            "d_star": primary.get("d"),
            "height": primary.get("peak_I"),
            "area": primary.get("area"),
            "FWHM": primary.get("FWHM"),
            "HWHM": primary.get("HWHM"),
            "asymmetry": primary.get("asymmetry"),
            "prominence": primary.get("prominence"),
            "SNR": primary.get("SNR"),
            "correlation_length": primary.get("correlation_length"),
            "export_tables": {"peaks": rows},
        }
    )
    return _result_with_values(curve, "peaks", q_range, values, warnings=source.warnings, tables={"peaks": rows})


def _run_shoulders(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    rows = detect_shoulders(curve.q[mask], curve.intensity[mask])
    primary = rows[0] if rows else {}
    values = {name: primary.get(name) for name in ("shoulder_q", "shoulder_d", "curvature", "confidence")}
    return _result_with_values(curve, "shoulders", q_range, values, warnings=rows.warnings, tables={"shoulders": list(rows)})


def _run_oscillations(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    source = analyze_oscillations(curve.q[mask], curve.intensity[mask])
    values = {
        "extrema_count": len(source.get("oscillations", [])),
        "period": source.get("mean_peak_spacing"),
        "decay": None,
        "decay_status": "not_applicable",
        "decay_invalid_reason": "The current oscillation helper does not estimate a decay scalar.",
    }
    return _result_with_values(
        curve,
        "oscillations",
        q_range,
        values,
        warnings=source.get("warnings", []),
        tables={"oscillations": source.get("oscillations", [])},
    )


def _run_porod(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    source = porod_deep_analysis(
        curve,
        q_range,
        contrast=config.contrast,
        volume_fraction=config.volume_fraction,
        absolute_intensity=config.absolute_intensity,
        two_phase_confirmed=False,
    )
    values = dict(source.results)
    values.update(
        {
            "alpha": source.results.get("power_law_alpha"),
            "porod_K": source.results.get("q4I_plateau_mean"),
            "relative_K": source.results.get("q4I_plateau_cv"),
            "plateau_mean": source.results.get("q4I_plateau_mean"),
            "plateau_std": source.results.get("q4I_plateau_std"),
            "plateau_cv": source.results.get("q4I_plateau_cv"),
            "noise_score": source.results.get("noise_score"),
        }
    )
    return _result_with_values(
        curve,
        "porod",
        q_range,
        values,
        warnings=source.warnings,
        tables=source.results.get("export_tables", {}),
        assumptions=source.results.get("assumptions", []),
    )


def _run_kratky(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    source = kratky_metrics(curve, q_range)
    values = dict(source.results)
    values.update(
        {
            "q_peak": source.results.get("q_K"),
            "d_peak": source.results.get("d_K"),
            "q2I_peak": source.results.get("q2I_max"),
        }
    )
    return _result_with_values(curve, "kratky", q_range, values, warnings=source.warnings)


def _run_compensated(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    source = porod_metrics(curve, q_range)
    values = {
        "alpha": None,
        "alpha_status": "not_applicable",
        "alpha_invalid_reason": "Compensated q^4 I(q) statistics do not fit an exponent.",
        "plateau_mean": source.results.get("q4I_plateau_mean"),
        "plateau_std": source.results.get("q4I_plateau_std"),
        "plateau_cv": source.results.get("q4I_plateau_cv"),
    }
    return _result_with_values(curve, "compensated", q_range, values, warnings=source.warnings)


def _run_invariant(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    return invariant_with_extrapolation(
        curve,
        q_range,
        contrast=config.contrast,
        absolute_intensity=config.absolute_intensity,
    )


def _run_integrals(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    source = extended_integrals(curve.q[mask], curve.intensity[mask])
    return _result_with_values(
        curve,
        "integrals",
        q_range,
        source,
        warnings=source.get("warnings", []),
        tables={},
    )


def _default_dmax(q_range: tuple[float, float]) -> float:
    q_low, q_high = q_range
    return float(max(2.0 * math.pi / max(q_low, 1e-12), 4.0 * math.pi / max(q_high, q_low, 1e-12)))


def _run_pr(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    return compute_pr(curve, q_range, dmax=_default_dmax(q_range))


def _run_correlation(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    return compute_correlation_function(curve, q_range)


def _run_lamellar(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    return lamellar_analysis(curve, q_range)


def _run_shape_models(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> list[AnalysisResult]:
    allowed_models = list(config.allowed_models) if config.allowed_models else None
    return list(
        fit_all_allowed_models(
            curve,
            q_range,
            allowed_models=allowed_models,
        ).values()
    )


# Keep this mapping explicit: registry additions must deliberately choose a
# concrete numerical handler instead of being silently skipped by a batch.
ANALYSIS_HANDLERS: dict[str, Handler] = {
    "data_quality": _run_data_quality,
    "derived_coordinates": _run_derived_coordinates,
    "guinier": _run_guinier,
    "power_law": _run_power_law,
    "local_slope": _run_local_slope,
    "crossover": _run_crossover,
    "peaks": _run_peaks,
    "shoulders": _run_shoulders,
    "oscillations": _run_oscillations,
    "porod": _run_porod,
    "kratky": _run_kratky,
    "compensated": _run_compensated,
    "invariant": _run_invariant,
    "integrals": _run_integrals,
    "pr": _run_pr,
    "correlation": _run_correlation,
    "lamellar": _run_lamellar,
    "shape_models": _run_shape_models,
}


def validate_registered_handlers(config: AutoBatchConfig) -> None:
    """Fail at batch startup if an applicable registry method lacks a handler."""

    applicable = applicable_method_ids(config)
    missing = [method_id for method_id in applicable if not callable(ANALYSIS_HANDLERS.get(method_id))]
    unknown = [method_id for method_id in ANALYSIS_HANDLERS if method_id not in METHOD_REGISTRY]
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append("missing handler(s): " + ", ".join(missing))
        if unknown:
            details.append("handler(s) without a registry method: " + ", ".join(unknown))
        raise BatchConfigurationError("Invalid registered analysis dispatch: " + "; ".join(details))


validate_registered_analysis_handlers = validate_registered_handlers


def _normalize_handler_results(value: AnalysisResult | list[AnalysisResult]) -> list[AnalysisResult]:
    if isinstance(value, AnalysisResult):
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, AnalysisResult) for item in value):
        return value
    raise TypeError("registered analysis handlers must return one AnalysisResult or a non-empty list[AnalysisResult]")


def run_registered_analysis(
    curve: CurveData,
    method_id: str,
    q_range: tuple[float, float] | None,
    config: AutoBatchConfig,
) -> list[AnalysisEnvelope]:
    """Run one registry method and return complete, auditable batch envelopes.

    Handler completeness is checked before any numerical work.  Handler runtime
    exceptions are isolated into a single ``FIT_FAILED`` envelope so a caller
    can continue later methods/curves without losing the failure reason.
    """

    validate_registered_handlers(config)
    if method_id not in METHOD_REGISTRY:
        raise BatchConfigurationError(f"Unknown registry method: {method_id}")
    if method_id not in applicable_method_ids(config):
        return [
            _blank_envelope(
                curve,
                method_id,
                _normalized_q_range(q_range),
                status=AnalysisStatus.NOT_APPLICABLE,
                reason="Method is not applicable to the supplied batch configuration.",
            )
        ]
    normalized_range = _normalized_q_range(q_range)
    if normalized_range is None:
        return [
            _blank_envelope(
                curve,
                method_id,
                None,
                status=AnalysisStatus.MISSING_PREREQUISITE,
                reason="A finite ascending q range is required before this analysis can run.",
            )
        ]
    handler = ANALYSIS_HANDLERS[method_id]
    try:
        results = _normalize_handler_results(handler(curve, normalized_range, config))
        return [_envelope_from_result(curve, method_id, result) for result in results]
    except Exception as exc:
        reason = f"{exc.__class__.__name__}: {exc}" if str(exc) else exc.__class__.__name__
        return [
            _blank_envelope(
                curve,
                method_id,
                normalized_range,
                status=AnalysisStatus.FIT_FAILED,
                reason=reason,
            )
        ]


__all__ = [
    "ANALYSIS_HANDLERS",
    "BatchConfigurationError",
    "run_registered_analysis",
    "validate_registered_analysis_handlers",
    "validate_registered_handlers",
]
