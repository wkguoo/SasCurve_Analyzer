"""Read-only, failure-isolating orchestration for automated 1D SAS batches."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from app.core.analysis_runner import run_registered_analysis, validate_registered_handlers
from app.core.auto_batch_schema import (
    AnalysisEnvelope,
    AnalysisStatus,
    AutoBatchConfig,
    AutoBatchRun,
    DEFAULT_EFFECTIVE_Q_RANGE,
    ParameterValue,
    ProgressEvent,
)
from app.core.batch_cache import job_cache_key, load_job_envelopes, save_job_envelopes, save_run_checkpoint
from app.core.batch_consensus import resolve_consensus_regions
from app.core.batch_inputs import collect_batch_inputs
from app.core.auto_regions import detect_auto_regions
from app.core.data_model import CurveData, utc_now_iso
from app.core.metric_registry import METHOD_REGISTRY, applicable_method_ids
from app.core.model_selection import flag_possible_model_transitions, rank_models, select_batch_main_model
from app.core.sequence_analysis import analyze_sequence


AnalysisRunner = Callable[
    [CurveData, str, tuple[float, float] | None, AutoBatchConfig],
    list[AnalysisEnvelope],
]


_METHOD_REGION_TYPES = {
    "guinier": "guinier",
    "power_law": "power_law",
    "local_slope": "power_law",
    "crossover": "power_law",
    "porod": "porod",
    "peaks": "peak",
    "shoulders": "peak",
    "oscillations": "peak",
    "lamellar": "peak",
}


@dataclass(frozen=True)
class MethodRangeDecision:
    """The range decision for one curve-method job.

    The configured effective q interval is the hard data boundary. Only the
    three shared-fit methods below require a method-specific candidate or
    consensus interval. Local-feature and descriptive methods receive the
    finite curve range inside the effective boundary and perform their own
    detection internally.
    """

    method_id: str
    q_range: tuple[float, float] | None
    region_type: str | None
    range_source: str
    candidate_status: str
    consensus_status: str
    reason_codes: tuple[str, ...] = ()
    candidate_count: int = 0
    fit_ready_candidate_count: int = 0
    selection_basis: str = "not_recorded"
    selection_evidence: dict[str, Any] = field(default_factory=dict)


_CANDIDATE_CONSENSUS_METHODS = {"guinier", "power_law", "porod"}
# Hard failures: numerical/envelope-level problems that block treating the batch
# as scientifically complete even if the runner finished every job.
_HARD_FAILURE_STATUSES = {
    AnalysisStatus.FIT_FAILED,
    AnalysisStatus.INVALID,
    AnalysisStatus.CANCELLED,
}
# Limitations: method not applicable or depends on assumptions — not hard crashes.
_LIMITATION_STATUSES = {
    AnalysisStatus.MISSING_PREREQUISITE,
    AnalysisStatus.ASSUMPTION_DEPENDENT,
    AnalysisStatus.NOT_APPLICABLE,
}
# Usable for reporting: explicit success or assumption-dependent results.
_USABLE_STATUSES = {
    AnalysisStatus.SUCCESS,
    AnalysisStatus.ASSUMPTION_DEPENDENT,
}
# Backward-compatible alias used when accumulating orchestration had_failure flags.
_PARTIAL_FAILURE_STATUSES = _HARD_FAILURE_STATUSES


def _exception_text(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


def _append_warning_once(run: AutoBatchRun, warning: str) -> None:
    if warning not in run.warnings:
        run.warnings.append(warning)


def _cancel_requested(run: AutoBatchRun, callback: Callable[[], bool] | None) -> bool:
    """Call the optional cancellation hook without allowing it to crash a run."""

    if callback is None:
        return False
    try:
        return bool(callback())
    except Exception as exc:
        _append_warning_once(
            run,
            "Cancellation check failed "
            f"({_exception_text(exc)}); batch was safely cancelled before remaining jobs.",
        )
        return True


def _finish_cancelled(run: AutoBatchRun) -> AutoBatchRun:
    run.status = "cancelled"
    run.finished_at = utc_now_iso()
    _append_warning_once(run, "Cancellation requested; remaining analysis jobs were not run.")
    return run


def _finalize_batch_status(run: AutoBatchRun, *, had_failure: bool) -> str:
    """Classify finished-batch scientific completeness (not merely that jobs ran).

    - ``completed``: every envelope is success.
    - ``completed_with_limitations``: usable results exist, and only limitations
      (missing prerequisite / assumption-dependent / not applicable) remain.
    - ``partial_success``: hard failures (or orchestration failures) mixed with
      at least one usable result.
    - ``failed``: no usable results (including empty analyses).

    Cancellation is handled separately via :func:`_finish_cancelled`.
    """

    statuses = [_normalize_envelope_status(item.status) for item in run.analyses]
    has_hard = had_failure or any(status in _HARD_FAILURE_STATUSES for status in statuses)
    has_limit = any(status in _LIMITATION_STATUSES for status in statuses)
    has_usable = any(status in _USABLE_STATUSES for status in statuses)

    if not statuses or not has_usable:
        return "failed"
    if has_hard:
        return "partial_success"
    if has_limit:
        return "completed_with_limitations"
    return "completed"


def _valid_q_range(value: object) -> tuple[float, float] | None:
    """Return a finite, ascending q interval or ``None`` without guessing."""

    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        q_start = float(value[0])
        q_end = float(value[1])
    except (TypeError, ValueError):
        return None
    if not np.isfinite(q_start) or not np.isfinite(q_end) or q_start >= q_end:
        return None
    return (q_start, q_end)


def _configured_effective_q_range(run: AutoBatchRun) -> tuple[float, float]:
    """Read the validated user q interval stored in the run snapshot."""

    configured = _valid_q_range(run.config_snapshot.get("effective_q_range"))
    return configured or DEFAULT_EFFECTIVE_Q_RANGE


def _consensus_q_ranges(
    raw_regions: object,
    run: AutoBatchRun,
) -> tuple[dict[str, tuple[float, float]], bool]:
    """Extract executable q tuples and retain consensus evidence for audit."""

    if not isinstance(raw_regions, Mapping):
        raise TypeError("resolve_consensus_regions() must return a mapping")

    q_ranges: dict[str, tuple[float, float]] = {}
    run.consensus_region_details = {}
    had_problem = False
    for region_name, region in raw_regions.items():
        normalized_name = str(region_name)
        q_range = _valid_q_range(getattr(region, "q_range", None))
        if q_range is None:
            had_problem = True
            _append_warning_once(
                run,
                f"Ignored invalid batch consensus q range for '{normalized_name}'; affected methods receive None.",
            )
            continue
        effective_low, effective_high = _configured_effective_q_range(run)
        clipped = (max(q_range[0], effective_low), min(q_range[1], effective_high))
        if clipped[0] >= clipped[1]:
            had_problem = True
            _append_warning_once(
                run,
                f"Ignored batch consensus q range for '{normalized_name}' because it is outside the effective q range.",
            )
            continue
        q_ranges[normalized_name] = clipped
        execution_counts: dict[str, int] = {}
        for curve in run.curves:
            q_values = np.asarray(curve.q, dtype=float).reshape(-1)
            intensity_values = np.asarray(curve.intensity, dtype=float).reshape(-1)
            size = min(q_values.size, intensity_values.size)
            q_values = q_values[:size]
            intensity_values = intensity_values[:size]
            usable = (
                np.isfinite(q_values)
                & np.isfinite(intensity_values)
                & (q_values > 0.0)
                & (intensity_values > 0.0)
                & (q_values >= clipped[0])
                & (q_values <= clipped[1])
            )
            execution_counts[str(curve.curve_id)] = int(np.count_nonzero(usable))
        supporting_ids = list(getattr(region, "supporting_curve_ids", ()) or ())
        supporting_execution_counts = [execution_counts.get(str(curve_id), 0) for curve_id in supporting_ids]
        run.consensus_region_details[normalized_name] = {
            "region_type": normalized_name,
            "q_start": clipped[0],
            "q_end": clipped[1],
            "consensus_status": "available",
            "coverage": float(getattr(region, "coverage", 0.0)),
            "median_score": float(getattr(region, "median_score", 0.0)),
            "median_n_points": float(getattr(region, "median_n_points", 0.0)),
            "candidate_n_points_min": float(getattr(region, "candidate_n_points_min", 0.0)),
            "candidate_n_points_max": float(getattr(region, "candidate_n_points_max", 0.0)),
            "supporting_curve_ids": supporting_ids,
            "execution_n_points_by_curve": execution_counts,
            "execution_n_points_min": min(supporting_execution_counts) if supporting_execution_counts else None,
            "execution_n_points_max": max(supporting_execution_counts) if supporting_execution_counts else None,
            "execution_n_points_median": float(np.median(supporting_execution_counts)) if supporting_execution_counts else None,
            "log_median_q_range": getattr(region, "log_median_q_range", None),
            "effective_q_range": [effective_low, effective_high],
            "selection_basis": "method-specific candidate consensus",
            "cluster_rule": "abs(delta_log_q_center)<=0.35",
            "coverage_rule": "coverage>=configured_consensus_min_coverage",
            "range_rule": "strict_intersection(max_candidate_start,min_candidate_end)",
        }
    effective_low, effective_high = _configured_effective_q_range(run)
    for region_type in sorted(_CANDIDATE_CONSENSUS_METHODS):
        run.consensus_region_details.setdefault(
            region_type,
            {
                "region_type": region_type,
                "q_start": None,
                "q_end": None,
                "consensus_status": "no_consensus",
                "coverage": 0.0,
                "median_score": None,
                "median_n_points": None,
                "supporting_curve_ids": [],
                "execution_n_points_by_curve": {},
                "execution_n_points_min": None,
                "execution_n_points_max": None,
                "execution_n_points_median": None,
                "log_median_q_range": None,
                "effective_q_range": [effective_low, effective_high],
                "selection_basis": "method-specific candidate consensus",
                "cluster_rule": "abs(delta_log_q_center)<=0.35",
                "coverage_rule": "coverage>=configured_consensus_min_coverage",
                "range_rule": "strict_intersection(max_candidate_start,min_candidate_end)",
                "reason_codes": ["no_method_specific_batch_consensus"],
            },
        )
    return q_ranges, had_problem


def _full_q_range(
    curve: CurveData,
    effective_q_range: tuple[float, float] | None = None,
) -> tuple[float, float] | None:
    """Calculate a usable finite q range without modifying the curve."""

    try:
        q_values = np.asarray(curve.q, dtype=float).reshape(-1)
    except (AttributeError, TypeError, ValueError):
        return None
    finite_q = q_values[np.isfinite(q_values)]
    if effective_q_range is not None:
        finite_q = finite_q[
            (finite_q >= effective_q_range[0])
            & (finite_q <= effective_q_range[1])
        ]
    if finite_q.size < 2:
        return None
    q_start = float(np.min(finite_q))
    q_end = float(np.max(finite_q))
    if not np.isfinite(q_start) or not np.isfinite(q_end) or q_start >= q_end:
        return None
    return (q_start, q_end)


def _configured_per_frame_fallback(run: AutoBatchRun) -> bool:
    return bool(run.config_snapshot.get("allow_per_frame_range_fallback", False))


def _evidence_value(row: Mapping[str, Any], metrics: Mapping[str, Any], key: str) -> Any:
    value = row.get(key)
    if value is None:
        value = metrics.get(key)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return value if isinstance(value, str) else None
    return numeric if np.isfinite(numeric) else None


def _candidate_selection_evidence(
    row: Mapping[str, Any] | None,
    *,
    candidate_count: int,
    fit_ready_candidate_count: int,
) -> dict[str, Any]:
    """Keep compact, method-specific evidence for the selected/top candidate."""

    evidence: dict[str, Any] = {
        "candidate_count": int(candidate_count),
        "fit_ready_candidate_count": int(fit_ready_candidate_count),
        "candidate_selection_rule": "highest_score_then_n_points_then_lowest_q",
        "candidate_window_sampling": "log_q_multiscale",
    }
    if not isinstance(row, Mapping):
        return evidence
    metrics = row.get("metrics") if isinstance(row.get("metrics"), Mapping) else {}
    evidence["candidate_q_start"] = _evidence_value(row, metrics, "q_start")
    evidence["candidate_q_end"] = _evidence_value(row, metrics, "q_end")
    evidence["candidate_score"] = _evidence_value(row, metrics, "score")
    evidence["candidate_n_points"] = _evidence_value(row, metrics, "n_points")
    for key in (
        "log_q_span_decades",
        "R2",
        "qRg_max",
        "local_alpha_std",
        "local_alpha_stability_score",
        "alpha_plausibility_score",
        "alpha_within_tolerance",
        "q4I_plateau_cv",
        "plateau_stability_score",
        "positive_plateau_score",
        "q_position_score",
        "high_q_noise_score",
    ):
        value = _evidence_value(row, metrics, key)
        if value is not None:
            evidence[key] = value
    warnings = row.get("warnings")
    if isinstance(warnings, list) and warnings:
        evidence["candidate_warnings"] = " | ".join(str(item) for item in warnings[:3])
    return evidence


def _effective_q_selection_evidence(
    curve: CurveData,
    effective_q_range: tuple[float, float],
    q_range: tuple[float, float] | None,
) -> dict[str, Any]:
    q = np.asarray(curve.q, dtype=float).reshape(-1)
    intensity = np.asarray(curve.intensity, dtype=float).reshape(-1)
    size = min(q.size, intensity.size)
    q = q[:size]
    intensity = intensity[:size]
    finite_pair = np.isfinite(q) & np.isfinite(intensity)
    inside = finite_pair & (q >= effective_q_range[0]) & (q <= effective_q_range[1])
    positive_log = inside & (q > 0.0) & (intensity > 0.0)
    return {
        "effective_q_low": effective_q_range[0],
        "effective_q_high": effective_q_range[1],
        "actual_q_start": None if q_range is None else q_range[0],
        "actual_q_end": None if q_range is None else q_range[1],
        "finite_pair_count": int(np.count_nonzero(inside)),
        "positive_log_point_count": int(np.count_nonzero(positive_log)),
        "selection_rule": "import_time_effective_q_filter_then_finite_curve_range",
    }


def _consensus_selection_evidence(
    run: AutoBatchRun,
    region_type: str,
    effective_q_range: tuple[float, float],
) -> dict[str, Any]:
    detail = run.consensus_region_details.get(region_type, {})
    detail = detail if isinstance(detail, Mapping) else {}
    supporting = detail.get("supporting_curve_ids")
    supporting_count = len(supporting) if isinstance(supporting, list) else None
    return {
        "effective_q_low": effective_q_range[0],
        "effective_q_high": effective_q_range[1],
        "candidate_score": detail.get("median_score"),
        "consensus_status": detail.get("consensus_status"),
        "coverage": detail.get("coverage"),
        "candidate_n_points": detail.get("median_n_points"),
        "candidate_n_points_min": detail.get("candidate_n_points_min"),
        "candidate_n_points_max": detail.get("candidate_n_points_max"),
        "consensus_execution_n_points": detail.get("execution_n_points_median"),
        "consensus_execution_n_points_min": detail.get("execution_n_points_min"),
        "consensus_execution_n_points_max": detail.get("execution_n_points_max"),
        "consensus_supporting_curve_count": supporting_count,
        "consensus_cluster_rule": "abs(delta_log_q_center)<=0.35",
        "consensus_coverage_rule": "coverage>=configured_consensus_min_coverage",
        "consensus_range_rule": "strict_intersection(max_candidate_start,min_candidate_end)",
        "log_median_q_range": detail.get("log_median_q_range"),
        "selection_rule": "method_specific_candidate_consensus",
    }


def _serialize_selection_evidence(evidence: Mapping[str, Any]) -> str:
    def json_default(value: Any) -> Any:
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, tuple):
            return list(value)
        return str(value)

    return json.dumps(dict(evidence), ensure_ascii=False, separators=(",", ":"), default=json_default)


def _candidate_range_from_curve(
    curve: CurveData,
    region_type: str,
    effective_q_range: tuple[float, float],
) -> tuple[tuple[float, float] | None, str, tuple[str, ...], int, int, dict[str, Any]]:
    """Inspect one method's candidates without treating a candidate as a fit."""

    try:
        detection = detect_auto_regions(curve, q_range=effective_q_range)
    except Exception:
        return None, "invalid_input", ("candidate_scan_failed",), 0, 0, {
            "candidate_count": 0,
            "fit_ready_candidate_count": 0,
            "candidate_scan_error": "candidate_scan_failed",
        }
    rows = detection.results.get("candidates", [])
    if not isinstance(rows, list):
        return None, "not_detected", ("candidate_rows_missing",), 0, 0, {
            "candidate_count": 0,
            "fit_ready_candidate_count": 0,
            "candidate_scan_error": "candidate_rows_missing",
        }
    matching = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("region_type") == f"{region_type}_candidate"
    ]
    ready: list[tuple[dict[str, Any], tuple[float, float]]] = []
    for row in matching:
        if row.get("fit_ready") is not True:
            continue
        q_range = _valid_q_range((row.get("q_start"), row.get("q_end")))
        if q_range is None:
            continue
        clipped = (
            max(q_range[0], effective_q_range[0]),
            min(q_range[1], effective_q_range[1]),
        )
        if clipped[0] < clipped[1]:
            ready.append((dict(row), clipped))
    if not matching:
        return None, "not_detected", ("no_method_candidate_detected",), 0, 0, {
            "candidate_count": 0,
            "fit_ready_candidate_count": 0,
            "candidate_selection_rule": "highest_score_then_n_points_then_lowest_q",
            "candidate_window_sampling": "log_q_multiscale",
        }
    if not ready:
        best_row = max(
            matching,
            key=lambda row: (
                float(row.get("score", 0.0) or 0.0),
                float(row.get("n_points", 0.0) or 0.0),
            ),
        )
        return (
            None,
            "not_fit_ready",
            ("method_candidates_not_fit_ready",),
            len(matching),
            0,
            _candidate_selection_evidence(
                best_row,
                candidate_count=len(matching),
                fit_ready_candidate_count=0,
            ),
        )

    def sort_key(item: tuple[dict[str, Any], tuple[float, float]]) -> tuple[float, float, float, float]:
        row, q_range = item
        try:
            score = float(row.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        try:
            n_points = float(row.get("n_points", 0.0))
        except (TypeError, ValueError):
            n_points = 0.0
        return (score, n_points, -q_range[0], -q_range[1])

    selected_row, selected_range = max(ready, key=sort_key)
    return (
        selected_range,
        "fit_ready",
        ("method_candidate_available",),
        len(matching),
        len(ready),
        _candidate_selection_evidence(
            selected_row,
            candidate_count=len(matching),
            fit_ready_candidate_count=len(ready),
        ),
    )


def _range_decision_for_method(
    run: AutoBatchRun,
    curve: CurveData,
    method_id: str,
) -> MethodRangeDecision:
    effective_q_range = _configured_effective_q_range(run)
    spec = METHOD_REGISTRY.get(method_id)
    strategy = getattr(spec, "range_strategy", "effective")
    if strategy != "candidate_consensus" or method_id not in _CANDIDATE_CONSENSUS_METHODS:
        q_range = _full_q_range(curve, effective_q_range)
        if q_range is None:
            reason_codes = ("insufficient_finite_q_coverage",)
            _append_warning_once(
                run,
                f"Curve '{curve.name}' has no safe finite q range within the effective q interval; "
                f"method '{method_id}' receives None.",
            )
            return MethodRangeDecision(
                method_id,
                None,
                None,
                "none",
                "invalid_input",
                "not_required",
                reason_codes,
                selection_basis="effective_q_boundary_unavailable",
                selection_evidence=_effective_q_selection_evidence(curve, effective_q_range, None),
            )
        return MethodRangeDecision(
            method_id,
            q_range,
            None,
            "effective_q_range",
            "not_required",
            "not_required",
            ("method_uses_effective_q_boundary",),
            selection_basis="effective_q_boundary_after_import_filter",
            selection_evidence=_effective_q_selection_evidence(curve, effective_q_range, q_range),
        )

    region_type = _METHOD_REGION_TYPES.get(method_id)
    q_range = run.consensus_regions.get(region_type) if region_type is not None else None
    if q_range is not None:
        clipped = (
            max(q_range[0], effective_q_range[0]),
            min(q_range[1], effective_q_range[1]),
        )
        if clipped[0] < clipped[1]:
            return MethodRangeDecision(
                method_id,
                clipped,
                region_type,
                "batch_method_consensus",
                "fit_ready",
                "available",
                ("method_specific_consensus",),
                selection_basis="method_candidate_consensus_log_q_cluster_strict_intersection",
                selection_evidence=_consensus_selection_evidence(
                    run,
                    region_type or method_id,
                    effective_q_range,
                ),
            )

    (
        candidate_range,
        candidate_status,
        candidate_codes,
        candidate_count,
        ready_count,
        candidate_evidence,
    ) = _candidate_range_from_curve(curve, region_type or method_id, effective_q_range)
    consensus_codes = ("method_consensus_not_available",)
    if candidate_range is not None and _configured_per_frame_fallback(run):
        reason_codes = (*consensus_codes, *candidate_codes, "per_frame_fallback_used")
        return MethodRangeDecision(
            method_id,
            candidate_range,
            region_type,
            "per_frame_candidate_fallback",
            candidate_status,
            "not_available",
            reason_codes,
            candidate_count,
            ready_count,
            selection_basis="method_candidate_scan_log_q_multiscale_best_fit_ready_per_frame",
            selection_evidence={
                **candidate_evidence,
                "fallback_rule": "same_method_per_frame_candidate_only_when_explicitly_enabled",
            },
        )

    reason_codes = (*consensus_codes, *candidate_codes)
    if not _configured_per_frame_fallback(run):
        reason_codes = (*reason_codes, "per_frame_fallback_disabled")
    _append_warning_once(
        run,
        f"Method '{method_id}' on curve '{curve.name}' has no executable method-specific q interval; "
        f"status={candidate_status}, reasons={','.join(reason_codes)}.",
    )
    return MethodRangeDecision(
        method_id,
        None,
        region_type,
        "none",
        candidate_status,
        "not_available",
        reason_codes,
        candidate_count,
        ready_count,
        selection_basis="method_candidate_scan_no_executable_interval",
        selection_evidence={
            **candidate_evidence,
            "fallback_rule": "no_cross_method_borrowing; per_frame_fallback_disabled",
        },
    )


def _q_range_for_method(
    run: AutoBatchRun,
    curve: CurveData,
    method_id: str,
) -> tuple[float, float] | None:
    """Compatibility wrapper returning only the executable q tuple."""

    return _range_decision_for_method(run, curve, method_id).q_range


def _range_audit_row(curve: CurveData, decision: MethodRangeDecision) -> dict[str, Any]:
    evidence = decision.selection_evidence

    def first_value(*keys: str) -> Any:
        for key in keys:
            if key in evidence and evidence[key] is not None:
                return evidence[key]
        return None

    return {
        "curve_id": curve.curve_id,
        "curve_name": curve.name,
        "method_id": decision.method_id,
        "region_type": decision.region_type,
        "q_start": None if decision.q_range is None else decision.q_range[0],
        "q_end": None if decision.q_range is None else decision.q_range[1],
        "range_source": decision.range_source,
        "candidate_status": decision.candidate_status,
        "consensus_status": decision.consensus_status,
        "candidate_count": decision.candidate_count,
        "fit_ready_candidate_count": decision.fit_ready_candidate_count,
        "q_selection_basis": decision.selection_basis,
        "q_selection_score": first_value("candidate_score"),
        "q_selection_coverage": first_value("coverage"),
        "q_selection_n_points": first_value("candidate_n_points"),
        "q_selection_n_points_min": first_value("candidate_n_points_min"),
        "q_selection_n_points_max": first_value("candidate_n_points_max"),
        "q_execution_n_points": first_value("consensus_execution_n_points", "execution_n_points"),
        "q_execution_n_points_min": first_value("consensus_execution_n_points_min"),
        "q_execution_n_points_max": first_value("consensus_execution_n_points_max"),
        "q_selection_log_q_span_decades": first_value("log_q_span_decades"),
        "q_selection_R2": first_value("R2"),
        "q_selection_stability_score": first_value("local_alpha_stability_score", "plateau_stability_score"),
        "q_selection_physics_score": first_value("alpha_plausibility_score", "positive_plateau_score"),
        "q_selection_noise_score": first_value("high_q_noise_score"),
        "q_selection_plateau_cv": first_value("q4I_plateau_cv"),
        "q_selection_qRg_max": first_value("qRg_max"),
        "q_selection_evidence": _serialize_selection_evidence(evidence),
        "reason_codes": " | ".join(decision.reason_codes),
    }


def _numeric_parameter(envelope: AnalysisEnvelope, name: str) -> float | None:
    for parameter in envelope.parameters:
        if parameter.name != name:
            continue
        try:
            value = float(parameter.value)
        except (TypeError, ValueError, OverflowError):
            return None
        return value if np.isfinite(value) else None
    return None


def _feature_q_tolerance(curve: CurveData, effective_q_range: tuple[float, float]) -> float:
    q = np.asarray(curve.q, dtype=float).reshape(-1)
    q = q[np.isfinite(q) & (q >= effective_q_range[0]) & (q <= effective_q_range[1])]
    q = np.unique(np.sort(q))
    if q.size < 2:
        return 1e-12
    spacing = np.diff(q)
    finite_spacing = spacing[np.isfinite(spacing) & (spacing > 0.0)]
    if finite_spacing.size == 0:
        return 1e-12
    return max(1e-12, float(np.median(finite_spacing) * 0.5))


def _link_related_local_features(run: AutoBatchRun) -> None:
    """Mark shoulder/crossover overlap instead of reporting duplicate features."""

    effective_q_range = _configured_effective_q_range(run)
    by_curve: dict[str, dict[str, AnalysisEnvelope]] = {}
    for item in run.analyses:
        if item.analysis_type not in {"shoulders", "crossover"}:
            continue
        by_curve.setdefault(item.curve_id, {})[item.analysis_type] = item

    curve_by_id = {str(curve.curve_id): curve for curve in run.curves}
    relation = "shoulder_crossover_same_q_grid_transition"
    for curve_id, items in by_curve.items():
        shoulder = items.get("shoulders")
        crossover = items.get("crossover")
        curve = curve_by_id.get(str(curve_id))
        if shoulder is None or crossover is None or curve is None:
            continue
        shoulder_q = _numeric_parameter(shoulder, "shoulder_q")
        crossover_q = _numeric_parameter(crossover, "crossover_q")
        if shoulder_q is None or crossover_q is None:
            continue
        tolerance = _feature_q_tolerance(curve, effective_q_range)
        if abs(shoulder_q - crossover_q) > tolerance:
            continue
        for current, other in ((shoulder, crossover), (crossover, shoulder)):
            if other.analysis_id not in current.related_analysis_ids:
                current.related_analysis_ids.append(other.analysis_id)
            current.feature_relation = relation
            current.fit_quality["feature_relation"] = relation
            current.fit_quality["related_analysis_ids"] = list(current.related_analysis_ids)
            current.fit_quality["q_match_tolerance"] = tolerance
            current.detection_status = "ambiguous"
            if "shoulder_crossover_q_overlap" not in current.detection_reason_codes:
                current.detection_reason_codes.append("shoulder_crossover_q_overlap")
            current.reporting_status = "not_reportable"
            if "shared_local_derivative_evidence_requires_joint_interpretation" not in current.reporting_reason_codes:
                current.reporting_reason_codes.append("shared_local_derivative_evidence_requires_joint_interpretation")
            warning = (
                f"Shoulder/crossover q locations overlap for curve '{current.curve_name}' within "
                f"{tolerance:.6g}; the two rows are linked and are not independent reportable features."
            )
            if warning not in current.warnings:
                current.warnings.append(warning)


def _normalize_envelope_status(status: object) -> AnalysisStatus:
    """Return one supported status without relying on hashability of arbitrary values."""

    if isinstance(status, AnalysisStatus):
        return status
    if isinstance(status, str):
        try:
            return AnalysisStatus(status)
        except ValueError as exc:
            raise TypeError(
                "AnalysisEnvelope.status must be an AnalysisStatus or a supported status string; "
                f"got {status!r}."
            ) from exc
    raise TypeError(
        "AnalysisEnvelope.status must be an AnalysisStatus or a supported status string; "
        f"got {type(status).__name__}."
    )


def _validate_runner_output(
    output: object,
    curve: CurveData,
    method_id: str,
) -> list[AnalysisEnvelope]:
    if not isinstance(output, list):
        raise TypeError(
            "analysis_runner must return list[AnalysisEnvelope], "
            f"got {type(output).__name__}."
        )
    if not output:
        raise TypeError("analysis_runner must return a non-empty list[AnalysisEnvelope].")
    for item in output:
        if not isinstance(item, AnalysisEnvelope):
            raise TypeError("analysis_runner list items must all be AnalysisEnvelope instances.")
        item.status = _normalize_envelope_status(item.status)
        if item.curve_id != curve.curve_id:
            raise ValueError(
                "AnalysisEnvelope.curve_id must match the scheduled curve: "
                f"expected {curve.curve_id!r}, got {item.curve_id!r}."
            )
        if item.analysis_type != method_id:
            raise ValueError(
                "AnalysisEnvelope.analysis_type must match the scheduled method: "
                f"expected {method_id!r}, got {item.analysis_type!r}."
            )
    return output


def _failure_envelope(
    curve: CurveData,
    method_id: str,
    q_range: tuple[float, float] | None,
    reason: str,
) -> AnalysisEnvelope:
    parameters = [
        ParameterValue(
            name=metric.name,
            value=None,
            unit=metric.unit_role,
            status=AnalysisStatus.FIT_FAILED,
            invalid_reason=reason,
        )
        for metric in METHOD_REGISTRY[method_id].metrics
    ]
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}",
        analysis_type=method_id,
        status=AnalysisStatus.FIT_FAILED,
        q_range=q_range,
        parameters=parameters,
        invalid_reason=reason,
        warnings=[reason],
        execution_status="fit_failed",
        reporting_status="not_reportable",
        reporting_reason_codes=["analysis_execution_failed"],
    )


def _cancelled_envelope(
    curve: CurveData,
    method_id: str,
    q_range: tuple[float, float] | None,
) -> AnalysisEnvelope:
    reason = "Cancellation requested before this analysis job was executed."
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}",
        analysis_type=method_id,
        status=AnalysisStatus.CANCELLED,
        q_range=q_range,
        parameters=[
            ParameterValue(
                name=metric.name,
                value=None,
                unit=metric.unit_role,
                status=AnalysisStatus.CANCELLED,
                invalid_reason=reason,
            )
            for metric in METHOD_REGISTRY[method_id].metrics
        ],
        invalid_reason=reason,
        warnings=[reason],
        execution_status="cancelled",
        reporting_status="not_reportable",
        reporting_reason_codes=["analysis_cancelled"],
        detection_status="not_run",
    )


def _apply_range_context(
    envelopes: list[AnalysisEnvelope],
    decision: MethodRangeDecision,
) -> list[AnalysisEnvelope]:
    """Attach the range decision to every envelope produced by one job."""

    for item in envelopes:
        item.q_range = decision.q_range
        if isinstance(item.status, AnalysisStatus):
            item.execution_status = (
                "not_run"
                if item.status is AnalysisStatus.MISSING_PREREQUISITE and decision.q_range is None
                else "not_applicable"
                if item.status is AnalysisStatus.NOT_APPLICABLE
                else item.status.value
            )
        else:
            item.execution_status = str(item.status)
        item.candidate_status = decision.candidate_status
        item.consensus_status = decision.consensus_status
        item.range_source = decision.range_source
        item.range_reason_codes = list(decision.reason_codes)
        item.q_selection_basis = decision.selection_basis
        item.q_selection_evidence = _serialize_selection_evidence(decision.selection_evidence)
        if item.status is AnalysisStatus.CANCELLED:
            item.detection_status = "not_run"
    return envelopes


def _append_cancelled_jobs(
    run: AutoBatchRun,
    jobs: list[tuple[CurveData, str]],
) -> None:
    for curve, method_id in jobs:
        decision = _range_decision_for_method(run, curve, method_id)
        run.range_audit.append(_range_audit_row(curve, decision))
        run.analyses.append(_apply_range_context(
            [_cancelled_envelope(curve, method_id, decision.q_range)],
            decision,
        )[0])


def _remap_cached_envelopes(
    envelopes: list[AnalysisEnvelope],
    curve: CurveData,
    method_id: str,
) -> list[AnalysisEnvelope]:
    """Rebind cached envelopes to the freshly imported curve identity."""

    remapped: list[AnalysisEnvelope] = []
    for item in envelopes:
        suffix = ""
        if item.analysis_id and ":" in item.analysis_id:
            # Preserve model suffix after method id when present: curve:method:model
            parts = str(item.analysis_id).split(":")
            if len(parts) >= 3:
                suffix = ":" + ":".join(parts[2:])
            elif item.analysis_type == method_id and len(parts) == 2 and parts[-1] != method_id:
                suffix = f":{parts[-1]}"
        remapped.append(
            AnalysisEnvelope(
                curve_id=curve.curve_id,
                curve_name=curve.name,
                analysis_id=f"{curve.curve_id}:{method_id}{suffix}",
                analysis_type=method_id,
                status=item.status,
                q_range=item.q_range,
                parameters=list(item.parameters),
                fit_quality=dict(item.fit_quality),
                tables={name: list(rows) for name, rows in item.tables.items()},
                validity_checks=list(item.validity_checks),
                reliability_label=item.reliability_label,
                reliability_score=item.reliability_score,
                assumptions=list(item.assumptions),
                warnings=list(item.warnings),
                invalid_reason=item.invalid_reason,
                artifact_paths=dict(item.artifact_paths),
                execution_status=item.execution_status,
                candidate_status=item.candidate_status,
                consensus_status=item.consensus_status,
                detection_status=item.detection_status,
                reliability_status=item.reliability_status,
                reporting_status=item.reporting_status,
                reporting_reason_codes=list(item.reporting_reason_codes),
                related_analysis_ids=list(item.related_analysis_ids),
                feature_relation=item.feature_relation,
                range_source=item.range_source,
                range_reason_codes=list(item.range_reason_codes),
                detection_reason_codes=list(item.detection_reason_codes),
                q_selection_basis=item.q_selection_basis,
                q_selection_evidence=item.q_selection_evidence,
            )
        )
    return remapped


def _emit_progress(
    run: AutoBatchRun,
    callback: Callable[[ProgressEvent], None] | None,
    event: ProgressEvent,
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        _append_warning_once(
            run,
            f"Progress callback failed for '{event.curve_name}'/{event.operation}: {_exception_text(exc)}. "
            "Batch continued.",
        )


def run_auto_batch(
    input_dir: str | Path,
    config: AutoBatchConfig,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    analysis_runner: AnalysisRunner | None = None,
    cache_dir: str | Path | None = None,
) -> AutoBatchRun:
    """Run every applicable method while isolating each individual method failure.

    The function only reads source files through :func:`collect_batch_inputs`.
    It never writes a user result package or changes the imported curves.
    Optional ``cache_dir`` stores per-job envelopes and a final compute
    checkpoint so a failed export or interrupted batch can resume without
    recomputing finished jobs.
    """

    run = AutoBatchRun(
        batch_id=config.batch_id,
        config_snapshot=asdict(config),
    )
    cache_root = Path(cache_dir) if cache_dir is not None else None
    cache_hits = 0

    if analysis_runner is None:
        validate_registered_handlers(config)
        runner = run_registered_analysis
    else:
        runner = analysis_runner

    if _cancel_requested(run, cancel_requested):
        return _finish_cancelled(run)

    collected = collect_batch_inputs(input_dir, config)
    run.curves = list(collected.curves)
    run.input_manifest = list(collected.manifest)
    run.failed_inputs = list(collected.failed_inputs)
    run.warnings = list(collected.warnings)
    if collected.import_summary:
        run.config_snapshot["input_import_summary"] = dict(collected.import_summary)
    effective_low, effective_high = _configured_effective_q_range(run)
    _append_warning_once(
        run,
        f"Effective q range applied to batch analyses: [{effective_low:.12g}, {effective_high:.12g}] Å^-1.",
    )
    had_failure = bool(run.failed_inputs)
    methods = applicable_method_ids(config)
    run.config_snapshot["q_selection_policy"] = {
        "effective_q_boundary": "applied at import time; all downstream data remain within it",
        "method_specific_fit_methods": sorted(_CANDIDATE_CONSENSUS_METHODS),
        "effective_boundary_methods": sorted(
            method_id for method_id in methods if method_id not in _CANDIDATE_CONSENSUS_METHODS
        ),
        "candidate_window_sampling": "log_q_multiscale",
        "candidate_selection_rule": "highest_score_then_n_points_then_lowest_q",
        "consensus_cluster_rule": "abs(delta_log_q_center)<=0.35",
        "consensus_coverage_rule": f"coverage>={config.consensus_min_coverage:g}",
        "consensus_range_rule": "strict_intersection(max_candidate_start,min_candidate_end)",
        "per_frame_fallback_rule": "same_method_only; disabled_by_default",
        "cross_method_intersection": False,
        "reporting_min_log_q_span_decades": config.reporting_min_log_q_span_decades,
        "feature_confirmed_noise_score": config.feature_confirmed_noise_score,
        "oscillation_candidate_min_cycles": config.oscillation_candidate_min_cycles,
        "oscillation_min_cycles": config.oscillation_min_cycles,
        "oscillation_period_cv_max": config.oscillation_period_cv_max,
    }
    jobs = [(curve, method_id) for curve in run.curves for method_id in methods]

    if _cancel_requested(run, cancel_requested):
        _append_cancelled_jobs(run, jobs)
        return _finish_cancelled(run)

    try:
        raw_consensus = resolve_consensus_regions(run.curves, config)
        run.consensus_regions, consensus_problem = _consensus_q_ranges(raw_consensus, run)
        had_failure = had_failure or consensus_problem
    except Exception as exc:
        had_failure = True
        run.consensus_regions = {}
        run.consensus_region_details = {}
        _append_warning_once(
            run,
            f"Consensus region resolution failed: {_exception_text(exc)}. Continuing without consensus ranges.",
        )

    if _cancel_requested(run, cancel_requested):
        _append_cancelled_jobs(run, jobs)
        return _finish_cancelled(run)

    total = len(jobs)
    completed = 0

    for job_index, (curve, method_id) in enumerate(jobs):
        if _cancel_requested(run, cancel_requested):
            _append_cancelled_jobs(run, jobs[job_index:])
            if cache_root is not None:
                save_run_checkpoint(cache_root, run)
            return _finish_cancelled(run)

        decision = _range_decision_for_method(run, curve, method_id)
        q_range = decision.q_range
        run.range_audit.append(_range_audit_row(curve, decision))
        cache_key = job_cache_key(curve, method_id, config, q_range) if cache_root is not None else None
        envelopes: list[AnalysisEnvelope] | None = None
        used_cache = False
        if cache_root is not None and cache_key is not None:
            cached = load_job_envelopes(cache_root, cache_key)
            if cached is not None:
                remapped = _remap_cached_envelopes(cached, curve, method_id)
                try:
                    envelopes = _apply_range_context(
                        _validate_runner_output(remapped, curve, method_id),
                        decision,
                    )
                    used_cache = True
                    cache_hits += 1
                except Exception:
                    envelopes = None

        if envelopes is None:
            try:
                envelopes = _validate_runner_output(
                    runner(curve, method_id, q_range, config),
                    curve,
                    method_id,
                )
            except Exception as exc:
                had_failure = True
                reason = _exception_text(exc)
                envelopes = [_failure_envelope(curve, method_id, q_range, reason)]
            envelopes = _apply_range_context(envelopes, decision)
            cacheable = not any(item.status in _PARTIAL_FAILURE_STATUSES for item in envelopes)
            if cache_root is not None and cache_key is not None and cacheable:
                try:
                    save_job_envelopes(cache_root, cache_key, envelopes)
                except Exception as exc:
                    _append_warning_once(
                        run,
                        f"Failed to write job cache for '{curve.name}'/{method_id}: {_exception_text(exc)}.",
                    )

        run.analyses.extend(envelopes)
        if any(item.status in _PARTIAL_FAILURE_STATUSES for item in envelopes):
            had_failure = True
        completed += 1
        _emit_progress(
            run,
            progress_callback,
            ProgressEvent(
                completed,
                total,
                curve.name,
                method_id,
                message="cache_hit" if used_cache else "computed",
            ),
        )
        if _cancel_requested(run, cancel_requested):
            _append_cancelled_jobs(run, jobs[job_index + 1 :])
            if cache_root is not None:
                save_run_checkpoint(cache_root, run)
            return _finish_cancelled(run)

    _link_related_local_features(run)

    try:
        run.rankings = rank_models(run.analyses, total_frames=len(run.curves))
        run.main_model = select_batch_main_model(run.rankings)
        run.transition_flags = flag_possible_model_transitions(run.analyses, run.main_model)
    except Exception as exc:
        had_failure = True
        _append_warning_once(
            run,
            f"Batch model selection summary failed: {_exception_text(exc)}. Individual analysis envelopes were retained.",
        )

    if config.enable_sequence_analysis:
        try:
            run.sequence_results = analyze_sequence(run.curves, run.analyses, config)
            for warning in run.sequence_results.get("warnings", []):
                _append_warning_once(run, str(warning))
        except Exception as exc:
            had_failure = True
            run.sequence_results = {"status": "invalid", "invalid_reason": _exception_text(exc)}
            _append_warning_once(run, f"Sequence analysis failed: {_exception_text(exc)}.")

    run.status = _finalize_batch_status(run, had_failure=had_failure)
    run.finished_at = utc_now_iso()
    if cache_hits:
        _append_warning_once(run, f"Restored {cache_hits} analysis job(s) from compute cache.")
    if cache_root is not None:
        try:
            save_run_checkpoint(cache_root, run)
        except Exception as exc:
            _append_warning_once(run, f"Failed to write run checkpoint: {_exception_text(exc)}.")
    return run


__all__ = ["AnalysisRunner", "MethodRangeDecision", "run_auto_batch"]
