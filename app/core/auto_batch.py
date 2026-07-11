"""Read-only, failure-isolating orchestration for automated 1D SAS batches."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

from app.core.analysis_runner import run_registered_analysis, validate_registered_handlers
from app.core.auto_batch_schema import (
    AnalysisEnvelope,
    AnalysisStatus,
    AutoBatchConfig,
    AutoBatchRun,
    ParameterValue,
    ProgressEvent,
)
from app.core.batch_consensus import resolve_consensus_regions
from app.core.batch_inputs import collect_batch_inputs
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
_PARTIAL_FAILURE_STATUSES = {
    AnalysisStatus.FIT_FAILED,
    AnalysisStatus.INVALID,
    AnalysisStatus.CANCELLED,
}


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


def _valid_q_range(value: object) -> tuple[float, float] | None:
    """Return a finite, ascending q interval or ``None`` without guessing."""

    if not isinstance(value, tuple) or len(value) != 2:
        return None
    try:
        q_start = float(value[0])
        q_end = float(value[1])
    except (TypeError, ValueError):
        return None
    if not np.isfinite(q_start) or not np.isfinite(q_end) or q_start >= q_end:
        return None
    return (q_start, q_end)


def _consensus_q_ranges(
    raw_regions: object,
    run: AutoBatchRun,
) -> tuple[dict[str, tuple[float, float]], bool]:
    """Extract only executable q tuples from consensus objects for audit storage."""

    if not isinstance(raw_regions, Mapping):
        raise TypeError("resolve_consensus_regions() must return a mapping")

    q_ranges: dict[str, tuple[float, float]] = {}
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
        q_ranges[normalized_name] = q_range
    return q_ranges, had_problem


def _full_q_range(curve: CurveData) -> tuple[float, float] | None:
    """Calculate a usable full finite q range without applying any data repair."""

    try:
        q_values = np.asarray(curve.q, dtype=float).reshape(-1)
    except (AttributeError, TypeError, ValueError):
        return None
    finite_q = q_values[np.isfinite(q_values)]
    if finite_q.size < 2:
        return None
    q_start = float(np.min(finite_q))
    q_end = float(np.max(finite_q))
    if not np.isfinite(q_start) or not np.isfinite(q_end) or q_start >= q_end:
        return None
    return (q_start, q_end)


def _q_range_for_method(
    run: AutoBatchRun,
    curve: CurveData,
    method_id: str,
) -> tuple[float, float] | None:
    region_type = _METHOD_REGION_TYPES.get(method_id)
    if region_type is not None:
        q_range = run.consensus_regions.get(region_type)
        if q_range is None:
            _append_warning_once(
                run,
                f"No batch consensus q range for '{region_type}'; curve '{curve.name}' method "
                f"'{method_id}' receives None because strict per-frame fallback is disabled.",
            )
        return q_range

    q_range = _full_q_range(curve)
    if q_range is None:
        _append_warning_once(
            run,
            f"Curve '{curve.name}' has no safe finite full q range; method '{method_id}' receives None.",
        )
    return q_range


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
    )


def _append_cancelled_jobs(
    run: AutoBatchRun,
    jobs: list[tuple[CurveData, str]],
) -> None:
    for curve, method_id in jobs:
        run.analyses.append(
            _cancelled_envelope(curve, method_id, _q_range_for_method(run, curve, method_id))
        )


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
) -> AutoBatchRun:
    """Run every applicable method while isolating each individual method failure.

    The function only reads source files through :func:`collect_batch_inputs`.
    It never writes an output package or changes the imported curves.  Unless
    a caller deliberately injects a test/custom runner, it uses the production
    registry runner and validates dispatch completeness before input work.
    """

    run = AutoBatchRun(
        batch_id=config.batch_id,
        config_snapshot=asdict(config),
    )

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
    had_failure = bool(run.failed_inputs)
    methods = applicable_method_ids(config)
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
            return _finish_cancelled(run)

        q_range = _q_range_for_method(run, curve, method_id)
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

        run.analyses.extend(envelopes)
        if any(item.status in _PARTIAL_FAILURE_STATUSES for item in envelopes):
            had_failure = True
        completed += 1
        _emit_progress(
            run,
            progress_callback,
            ProgressEvent(completed, total, curve.name, method_id),
        )
        if _cancel_requested(run, cancel_requested):
            _append_cancelled_jobs(run, jobs[job_index + 1 :])
            return _finish_cancelled(run)

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

    run.status = "partial_success" if had_failure else "completed"
    run.finished_at = utc_now_iso()
    return run


__all__ = ["AnalysisRunner", "run_auto_batch"]
