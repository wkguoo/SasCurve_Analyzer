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


def _reliability_status(status: AnalysisStatus, label: str, score: float) -> str:
    """Classify reliability separately from execution status."""

    if status in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID}:
        return "invalid"
    if status in {AnalysisStatus.MISSING_PREREQUISITE, AnalysisStatus.NOT_APPLICABLE, AnalysisStatus.CANCELLED}:
        return "not_evaluated"
    if label in {RELIABILITY_INVALID, "invalid"}:
        return "invalid"
    if score >= 0.75:
        return "reliable"
    if score >= 0.55:
        return "tentative"
    return "low"


_DETECTION_STATUSES = {"not_evaluated", "not_run", "not_detected", "tentative", "detected", "ambiguous"}
_REPORTING_STATUSES = {"not_evaluated", "not_reportable", "exploratory", "reportable"}
_FEATURE_METHODS = {"peaks", "shoulders", "oscillations", "crossover", "lamellar"}


def _execution_status(status: AnalysisStatus, q_range: tuple[float, float] | None) -> str:
    """Separate whether a handler ran from the legacy result status."""

    if status is AnalysisStatus.MISSING_PREREQUISITE and q_range is None:
        return "not_run"
    if status is AnalysisStatus.NOT_APPLICABLE:
        return "not_applicable"
    return status.value


def _detection_status(
    result: AnalysisResult,
    method_id: str,
    status: AnalysisStatus,
) -> tuple[str, list[str]]:
    """Report local-feature detection without changing the fit status."""

    if status in {
        AnalysisStatus.MISSING_PREREQUISITE,
        AnalysisStatus.NOT_APPLICABLE,
        AnalysisStatus.FIT_FAILED,
        AnalysisStatus.INVALID,
        AnalysisStatus.CANCELLED,
    }:
        return "not_run", ["analysis_not_executed"]

    explicit = result.results.get("detection_status")
    if isinstance(explicit, str) and explicit in _DETECTION_STATUSES:
        raw_codes = result.results.get("detection_reason_codes", [])
        codes = [str(item) for item in raw_codes] if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)) else []
        return explicit, codes or [f"{method_id}_detection_status_from_method_gate"]

    count_value: Any = None
    feature_label: str | None = None
    if method_id == "peaks":
        count_value = result.results.get("confirmed_peak_count", result.results.get("peak_count"))
        feature_label = "peak"
    elif method_id == "shoulders":
        tables = result.results.get("export_tables", {})
        count_value = result.results.get(
            "confirmed_shoulder_count",
            len(tables.get("shoulders", [])) if isinstance(tables, Mapping) else None,
        )
        feature_label = "shoulder"
    elif method_id == "oscillations":
        count_value = result.results.get("confirmed_cycle_count", result.results.get("extrema_count"))
        feature_label = "oscillation"
    elif method_id == "crossover":
        tables = result.results.get("export_tables", {})
        count_value = result.results.get(
            "confirmed_crossover_count",
            len(tables.get("crossovers", [])) if isinstance(tables, Mapping) else None,
        )
        feature_label = "crossover"
    elif method_id == "lamellar":
        count_value = result.results.get("confirmed_peak_count", result.results.get("peak_count"))
        feature_label = "lamellar_peak"
    elif method_id == "local_slope":
        count_value = result.results.get("confirmed_plateau_count", result.results.get("plateau_count"))
        feature_label = "plateau"
    else:
        return "not_evaluated", []

    if count_value is None:
        return "not_evaluated", ["feature_count_unavailable"]
    try:
        count = int(count_value)
    except (TypeError, ValueError, OverflowError):
        return "not_evaluated", ["feature_count_invalid"]
    if count <= 0:
        return "not_detected", [f"no_{feature_label}_detected_in_effective_q_range"]
    return "detected", [f"{feature_label}_detected_in_effective_q_range"]


def _reporting_status(
    result: AnalysisResult,
    method_id: str,
    status: AnalysisStatus,
    detection_status: str,
    label: str,
    score: float,
) -> tuple[str, list[str]]:
    """Return report eligibility without treating numerical detection as proof."""

    explicit = result.results.get("reporting_status")
    if isinstance(explicit, str) and explicit in _REPORTING_STATUSES:
        raw_codes = result.results.get("reporting_reason_codes", [])
        codes = [str(item) for item in raw_codes] if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)) else []
        return explicit, codes or ["method_reporting_status_from_method_gate"]
    if status in {
        AnalysisStatus.MISSING_PREREQUISITE,
        AnalysisStatus.NOT_APPLICABLE,
        AnalysisStatus.FIT_FAILED,
        AnalysisStatus.INVALID,
        AnalysisStatus.CANCELLED,
    }:
        return "not_reportable", ["analysis_not_executed_or_invalid"]
    if method_id in _FEATURE_METHODS:
        if detection_status in {"detected", "tentative", "ambiguous"}:
            return "exploratory", ["local_feature_requires_independent_confirmation"]
        return "not_reportable", ["no_reportable_feature_detected"]
    if status is AnalysisStatus.ASSUMPTION_DEPENDENT:
        return "exploratory", ["method_result_depends_on_explicit_assumptions"]
    if label in {RELIABILITY_INVALID, "invalid"} or score < 0.5:
        return "not_reportable", ["reliability_threshold_not_met"]
    return "reportable", ["registered_method_result_passed_basic_reporting_gate"]


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
    for name in (
        "eligible_points",
        "actual_fit_points",
        "execution_fit_points",
        "execution_log_q_span_decades",
        "candidate_count",
        "confirmed_count",
        "confirmed_peak_count",
        "confirmed_shoulder_count",
        "confirmed_crossover_count",
        "confirmed_cycle_count",
        "confirmed_plateau_count",
        "noise_separation_score",
        "amplitude_to_noise",
        "period_cv",
        "candidate_n_points",
        "consensus_execution_n_points",
        "consensus_execution_n_points_min",
        "consensus_execution_n_points_max",
    ):
        if name in result.results:
            quality[name] = _native(result.results.get(name))
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
    detection_status, detection_codes = _detection_status(result, method_id, status)
    reporting_status, reporting_codes = _reporting_status(
        result,
        method_id,
        status,
        detection_status,
        label,
        score,
    )
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
        execution_status=_execution_status(status, _normalized_q_range(result.q_range)),
        detection_status=detection_status,
        reliability_status=_reliability_status(status, label, score),
        reporting_status=reporting_status,
        reporting_reason_codes=reporting_codes,
        range_source="runner_q_range",
        detection_reason_codes=detection_codes,
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
        execution_status=_execution_status(status, q_range),
        detection_status="not_run",
        reliability_status=_reliability_status(
            status,
            "invalid" if status in {AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID} else "low",
            0.0,
        ),
        reporting_status="not_reportable",
        reporting_reason_codes=["analysis_not_executed_or_invalid"],
        range_source="runner_q_range",
        range_reason_codes=["analysis_prerequisite_not_satisfied"],
        detection_reason_codes=["analysis_not_executed"],
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
    derived = build_curve_derived_table(curve, q_range=q_range)
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
    source = power_law_analysis(curve, q_range)
    values = dict(source.results)
    q_start = _finite_float(values.get("q_start"))
    q_end = _finite_float(values.get("q_end"))
    actual_fit_points = int(values.get("actual_fit_points", 0) or 0)
    execution_span = None
    if q_start is not None and q_end is not None and q_start > 0.0 and q_end > q_start:
        execution_span = float(math.log10(q_end / q_start))
    values["execution_fit_points"] = actual_fit_points
    values["execution_log_q_span_decades"] = execution_span

    validity = values.get("validity", {})
    fit_valid = isinstance(validity, Mapping) and bool(validity.get("fit_valid"))
    if fit_valid:
        reporting_codes: list[str] = []
        if execution_span is None:
            reporting_codes.append("execution_log_q_span_unavailable")
        elif execution_span < config.reporting_min_log_q_span_decades:
            reporting_codes.append("execution_log_q_span_below_reporting_threshold")
        if actual_fit_points < 5:
            reporting_codes.append("execution_fit_points_below_reporting_minimum")
        if reporting_codes:
            values["reporting_status"] = "exploratory"
            values["reporting_reason_codes"] = reporting_codes
            source.warnings.append(
                "Power-law fit is retained for audit, but its executed q interval does not meet the reporting gate."
            )
    source.results.update(values)
    return source


def _run_local_slope(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    source = local_slope(curve, q_range)
    values = dict(source.results)
    values["alpha_q"] = source.results.get("alpha")
    plateaus = source.results.get("plateaus")
    plateau_rows = plateaus if isinstance(plateaus, list) else []
    confirmed_plateaus = [
        row
        for row in plateau_rows
        if isinstance(row, Mapping)
        and _finite_float(row.get("stability_score")) is not None
        and float(row["stability_score"]) >= 0.5
    ]
    values["plateau_count"] = len(plateau_rows)
    values["confirmed_plateau_count"] = len(confirmed_plateaus)
    values["detection_status"] = (
        "detected"
        if confirmed_plateaus
        else "tentative"
        if plateau_rows
        else "not_detected"
    )
    values["detection_reason_codes"] = (
        ["plateau_confirmation_passed"]
        if confirmed_plateaus
        else ["plateau_candidates_found_but_stability_threshold_not_met"]
        if plateau_rows
        else ["no_stable_local_slope_plateau"]
    )
    values["reporting_status"] = "exploratory" if confirmed_plateaus else "not_reportable"
    values["reporting_reason_codes"] = (
        ["local_slope_plateau_is_descriptive"]
        if confirmed_plateaus
        else ["no_confirmed_local_slope_plateau"]
    )
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
    candidate_count = len(rows)
    values = {
        "crossover_q": primary.get("crossover_q"),
        "crossover_d": primary.get("crossover_d"),
        "slope_difference": primary.get("slope_difference"),
        "confidence": primary.get("confidence"),
        "candidate_count": candidate_count,
        "confirmed_crossover_count": 0,
        "detection_status": "tentative" if candidate_count else "not_detected",
        "detection_reason_codes": [
            "crossover_candidates_found_but_two_stable_slope_windows_not_confirmed"
            if candidate_count
            else "no_crossover_candidate"
        ],
        "reporting_status": "not_reportable",
        "reporting_reason_codes": ["crossover_requires_two_independent_stable_slope_windows"],
    }
    return _result_with_values(curve, "crossover", q_range, values, warnings=rows.warnings, tables={"crossovers": list(rows)})


def _run_peaks(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    source = detect_peaks(curve, q_range, noise_score_threshold=config.feature_confirmed_noise_score)
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
    confirmed_count = int(source.results.get("confirmed_peak_count", 0) or 0)
    values["reporting_status"] = "exploratory" if confirmed_count else "not_reportable"
    values["reporting_reason_codes"] = (
        ["peak_requires_manual_or_independent_confirmation"]
        if confirmed_count
        else ["no_peak_passed_area_and_noise_confirmation"]
    )
    return _result_with_values(curve, "peaks", q_range, values, warnings=source.warnings, tables={"peaks": rows})


def _run_shoulders(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    del config
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    rows = detect_shoulders(curve.q[mask], curve.intensity[mask])
    primary = rows[0] if rows else {}
    candidate_count = len(rows)
    values = {
        name: primary.get(name) for name in ("shoulder_q", "shoulder_d", "curvature", "confidence")
    }
    values.update(
        {
            "candidate_count": candidate_count,
            "confirmed_shoulder_count": 0,
            "detection_status": "tentative" if candidate_count else "not_detected",
            "detection_reason_codes": [
                "shoulder_candidates_found_but_multiscale_persistence_not_confirmed"
                if candidate_count
                else "no_shoulder_candidate"
            ],
            "reporting_status": "not_reportable",
            "reporting_reason_codes": ["shoulder_requires_multiscale_and_noise_confirmation"],
        }
    )
    return _result_with_values(curve, "shoulders", q_range, values, warnings=rows.warnings, tables={"shoulders": list(rows)})


def _run_oscillations(curve: CurveData, q_range: tuple[float, float], config: AutoBatchConfig) -> AnalysisResult:
    mask = (curve.q >= q_range[0]) & (curve.q <= q_range[1])
    source = analyze_oscillations(curve.q[mask], curve.intensity[mask])
    peaks = source.get("peaks", []) if isinstance(source.get("peaks"), list) else []
    peak_q = np.asarray([row.get("q") for row in peaks if isinstance(row, Mapping)], dtype=float)
    peak_q = peak_q[np.isfinite(peak_q)]
    periods = np.diff(peak_q) if peak_q.size >= 3 else np.asarray([], dtype=float)
    period_cv = (
        float(np.std(periods) / abs(np.mean(periods)))
        if periods.size >= 2 and np.mean(periods) != 0.0
        else None
    )
    residual = np.asarray(source.get("residual", []), dtype=float)
    finite_residual = residual[np.isfinite(residual)]
    robust_noise = (
        float(1.4826 * np.median(np.abs(finite_residual - np.median(finite_residual))))
        if finite_residual.size
        else None
    )
    extrema = source.get("oscillations", []) if isinstance(source.get("oscillations"), list) else []
    extrema_residual = np.asarray(
        [row.get("residual") for row in extrema if isinstance(row, Mapping)],
        dtype=float,
    )
    extrema_residual = extrema_residual[np.isfinite(extrema_residual)]
    amplitude_to_noise = (
        float(np.median(np.abs(extrema_residual)) / robust_noise)
        if robust_noise is not None and robust_noise > 0.0 and extrema_residual.size
        else None
    )
    cycle_count = int(source.get("oscillation_count", 0) or 0)
    confirmed_cycle_count = (
        cycle_count
        if cycle_count >= config.oscillation_min_cycles
        and period_cv is not None
        and period_cv <= config.oscillation_period_cv_max
        and amplitude_to_noise is not None
        and amplitude_to_noise >= config.feature_confirmed_noise_score
        else 0
    )
    values = {
        "extrema_count": len(source.get("oscillations", [])),
        "period": source.get("mean_peak_spacing"),
        "decay": None,
        "decay_status": "not_applicable",
        "decay_invalid_reason": "The current oscillation helper does not estimate a decay scalar.",
        "candidate_cycle_count": cycle_count,
        "confirmed_cycle_count": confirmed_cycle_count,
        "period_cv": period_cv,
        "amplitude_to_noise": amplitude_to_noise,
        "detection_status": (
            "detected"
            if confirmed_cycle_count
            else "tentative"
            if cycle_count >= config.oscillation_candidate_min_cycles
            else "not_detected"
        ),
        "detection_reason_codes": [
            "oscillation_period_and_noise_confirmation_passed"
            if confirmed_cycle_count
            else "oscillation_candidates_found_but_period_or_noise_confirmation_not_passed"
            if cycle_count >= config.oscillation_candidate_min_cycles
            else "insufficient_oscillation_cycles"
        ],
        "reporting_status": "exploratory" if confirmed_cycle_count else "not_reportable",
        "reporting_reason_codes": (
            ["oscillation_requires_independent_scattering_interpretation"]
            if confirmed_cycle_count
            else ["oscillation_period_not_confirmed"]
        ),
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
