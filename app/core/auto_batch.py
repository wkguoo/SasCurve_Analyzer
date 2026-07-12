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
    DEFAULT_EFFECTIVE_Q_RANGE,
    ParameterValue,
    ProgressEvent,
)
from app.core.batch_cache import job_cache_key, load_job_envelopes, save_job_envelopes, save_run_checkpoint
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


def _q_range_for_method(
    run: AutoBatchRun,
    curve: CurveData,
    method_id: str,
) -> tuple[float, float] | None:
    region_type = _METHOD_REGION_TYPES.get(method_id)
    effective_q_range = _configured_effective_q_range(run)
    if region_type is not None:
        q_range = run.consensus_regions.get(region_type)
        if q_range is not None:
            q_range = (
                max(q_range[0], effective_q_range[0]),
                min(q_range[1], effective_q_range[1]),
            )
            if q_range[0] >= q_range[1]:
                q_range = None
        if q_range is None:
            _append_warning_once(
                run,
                f"No batch consensus q range for '{region_type}'; curve '{curve.name}' method "
                f"'{method_id}' receives None because strict per-frame fallback is disabled.",
            )
        return q_range

    q_range = _full_q_range(curve, effective_q_range)
    if q_range is None:
        _append_warning_once(
            run,
            f"Curve '{curve.name}' has no safe finite full q range within the effective q interval; "
            f"method '{method_id}' receives None.",
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
    effective_low, effective_high = _configured_effective_q_range(run)
    _append_warning_once(
        run,
        f"Effective q range applied to batch analyses: [{effective_low:.12g}, {effective_high:.12g}] Å^-1.",
    )
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
            if cache_root is not None:
                save_run_checkpoint(cache_root, run)
            return _finish_cancelled(run)

        q_range = _q_range_for_method(run, curve, method_id)
        cache_key = job_cache_key(curve, method_id, config, q_range) if cache_root is not None else None
        envelopes: list[AnalysisEnvelope] | None = None
        used_cache = False
        if cache_root is not None and cache_key is not None:
            cached = load_job_envelopes(cache_root, cache_key)
            if cached is not None:
                remapped = _remap_cached_envelopes(cached, curve, method_id)
                try:
                    envelopes = _validate_runner_output(remapped, curve, method_id)
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


__all__ = ["AnalysisRunner", "run_auto_batch"]
