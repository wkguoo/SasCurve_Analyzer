"""Batch-stable ranking and transition flags for complete shape-model fits.

The functions in this module only summarize already-produced model envelopes.
They never rerun a fit or change the chosen main model frame by frame.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, ParameterValue


MIN_MAIN_MODEL_COVERAGE = 0.70
MIN_MAIN_MODEL_RESIDUAL_PASS_RATE = 0.70
MAX_MAIN_MODEL_BOUND_HIT_RATE = 0.30
MAX_MAIN_MODEL_UNCERTAINTY = 1.0
MIN_MAIN_MODEL_RELIABILITY_PASS_RATE = 0.70
MIN_MAIN_MODEL_RELIABILITY_SCORE = 0.50


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _status_value(item: AnalysisEnvelope | Mapping[str, Any]) -> str | None:
    if isinstance(item, AnalysisEnvelope):
        value = item.status
    else:
        value = item.get("status")
    return value.value if isinstance(value, AnalysisStatus) else str(value) if isinstance(value, str) else None


def _fit_quality(item: AnalysisEnvelope | Mapping[str, Any]) -> Mapping[str, Any]:
    value = item.fit_quality if isinstance(item, AnalysisEnvelope) else item.get("fit_quality", {})
    return value if isinstance(value, Mapping) else {}


def _parameters(item: AnalysisEnvelope | Mapping[str, Any]) -> list[ParameterValue | Mapping[str, Any]]:
    value = item.parameters if isinstance(item, AnalysisEnvelope) else item.get("parameters", [])
    return list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _parameter_value(item: AnalysisEnvelope | Mapping[str, Any], name: str) -> Any:
    for parameter in _parameters(item):
        if isinstance(parameter, ParameterValue) and parameter.name == name:
            return parameter.value
        if isinstance(parameter, Mapping) and parameter.get("name") == name:
            return parameter.get("value")
    return None


def _model_name(item: AnalysisEnvelope | Mapping[str, Any]) -> str | None:
    direct = _parameter_value(item, "model_name")
    if direct not in (None, ""):
        return str(direct)
    quality = _fit_quality(item)
    if quality.get("model_name") not in (None, ""):
        return str(quality["model_name"])
    if isinstance(item, Mapping) and item.get("model_name") not in (None, ""):
        return str(item["model_name"])
    analysis_id = item.analysis_id if isinstance(item, AnalysisEnvelope) else item.get("analysis_id")
    if isinstance(analysis_id, str) and ":shape_models:" in analysis_id:
        return analysis_id.rsplit(":", 1)[-1]
    return None


def _curve_id(item: AnalysisEnvelope | Mapping[str, Any]) -> str:
    value = item.curve_id if isinstance(item, AnalysisEnvelope) else item.get("curve_id")
    return str(value) if value not in (None, "") else "unknown-curve"


def _curve_name(item: AnalysisEnvelope | Mapping[str, Any]) -> str | None:
    value = item.curve_name if isinstance(item, AnalysisEnvelope) else item.get("curve_name")
    return str(value) if value not in (None, "") else None


def _is_shape_model(item: AnalysisEnvelope | Mapping[str, Any]) -> bool:
    value = item.analysis_type if isinstance(item, AnalysisEnvelope) else item.get("analysis_type")
    return value == "shape_models" or _model_name(item) is not None


def _is_valid_fit(item: AnalysisEnvelope | Mapping[str, Any]) -> bool:
    if _status_value(item) not in {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}:
        return False
    quality = _fit_quality(item)
    return quality.get("converged") is not False


def _residual_pass(item: AnalysisEnvelope | Mapping[str, Any]) -> bool:
    quality = _fit_quality(item)
    explicit = quality.get("residual_pass")
    if isinstance(explicit, bool):
        return explicit
    r_squared = _finite_float(quality.get("R2"))
    if r_squared is not None:
        return r_squared >= 0.90
    if isinstance(item, Mapping):
        checks = item.get("validity_checks", [])
    else:
        checks = item.validity_checks
    if isinstance(checks, Sequence):
        for check in checks:
            if isinstance(check, Mapping) and check.get("name") in {"fit_quality_r2", "residual_quality"}:
                return bool(check.get("passed"))
    return False


def _reliability_ok(item: AnalysisEnvelope | Mapping[str, Any]) -> bool:
    """Return whether one frame-level fit is reliable enough for main-model evidence."""

    if isinstance(item, AnalysisEnvelope):
        label = str(item.reliability_label or "")
        score = _finite_float(item.reliability_score)
    else:
        label = str(item.get("reliability_label") or "")
        score = _finite_float(item.get("reliability_score"))
    quality = _fit_quality(item)
    if not label:
        label = str(quality.get("reliability_label") or "medium")
    if score is None:
        score = _finite_float(quality.get("reliability_score"))
    if label in {"invalid", "low"}:
        return False
    if score is not None and score < MIN_MAIN_MODEL_RELIABILITY_SCORE:
        return False
    return True


def _bound_hit(item: AnalysisEnvelope | Mapping[str, Any]) -> bool:
    for parameter in _parameters(item):
        if isinstance(parameter, ParameterValue) and parameter.bound_hit is True:
            return True
        if isinstance(parameter, Mapping) and parameter.get("bound_hit") is True:
            return True
        if isinstance(parameter, ParameterValue) and parameter.name == "bound_hit":
            value = parameter.value
        elif isinstance(parameter, Mapping) and parameter.get("name") == "bound_hit":
            value = parameter.get("value")
        else:
            continue
        if value is True:
            return True
        if isinstance(value, Mapping) and any(nested is True for nested in value.values()):
            return True
    return False


def _uncertainty(item: AnalysisEnvelope | Mapping[str, Any]) -> float | None:
    quality = _fit_quality(item)
    direct = _finite_float(quality.get("uncertainty_score"))
    if direct is not None and direct >= 0.0:
        return direct
    relative_errors: list[float] = []
    for parameter in _parameters(item):
        if isinstance(parameter, ParameterValue):
            value, stderr = parameter.value, parameter.stderr
        elif isinstance(parameter, Mapping):
            value, stderr = parameter.get("value"), parameter.get("stderr")
        else:
            continue
        numeric_value = _finite_float(value)
        numeric_stderr = _finite_float(stderr)
        if numeric_value is not None and numeric_stderr is not None and numeric_stderr >= 0.0 and numeric_value != 0.0:
            relative_errors.append(abs(numeric_stderr / numeric_value))
    parameter_values = _parameter_value(item, "parameter_value")
    standard_errors = _parameter_value(item, "stderr")
    if isinstance(parameter_values, Mapping) and isinstance(standard_errors, Mapping):
        for name, value in parameter_values.items():
            numeric_value = _finite_float(value)
            numeric_stderr = _finite_float(standard_errors.get(name))
            if numeric_value is not None and numeric_stderr is not None and numeric_stderr >= 0.0 and numeric_value != 0.0:
                relative_errors.append(abs(numeric_stderr / numeric_value))
    return float(median(relative_errors)) if relative_errors else None


def _metric(item: AnalysisEnvelope | Mapping[str, Any], name: str) -> float | None:
    return _finite_float(_fit_quality(item).get(name))


def _ascending_rank(values: Mapping[str, float | None]) -> dict[str, int | None]:
    finite = sorted({value for value in values.values() if value is not None})
    return {name: None if value is None else finite.index(value) + 1 for name, value in values.items()}


def _frame_count(items: Sequence[AnalysisEnvelope | Mapping[str, Any]], total_frames: int | None) -> int:
    if total_frames is not None:
        if isinstance(total_frames, bool) or not isinstance(total_frames, int) or total_frames < 0:
            raise ValueError("total_frames must be a non-negative integer when supplied")
        return total_frames
    return len({_curve_id(item) for item in items if _is_shape_model(item)})


def _main_model_eligibility(
    *,
    coverage: float,
    residual_pass_rate: float,
    bound_hit_rate: float,
    uncertainty: float | None,
    reliability_pass_rate: float,
    coverage_threshold: float,
) -> tuple[bool, list[str]]:
    """Return eligibility and explicit failure reasons for batch main-model selection."""

    reasons: list[str] = []
    if coverage < coverage_threshold:
        reasons.append("coverage_below_threshold")
    if residual_pass_rate < MIN_MAIN_MODEL_RESIDUAL_PASS_RATE:
        reasons.append("residual_pass_rate_below_threshold")
    if bound_hit_rate > MAX_MAIN_MODEL_BOUND_HIT_RATE:
        reasons.append("bound_hit_rate_above_threshold")
    if uncertainty is None:
        reasons.append("uncertainty_missing")
    elif uncertainty > MAX_MAIN_MODEL_UNCERTAINTY:
        reasons.append("uncertainty_above_threshold")
    if reliability_pass_rate < MIN_MAIN_MODEL_RELIABILITY_PASS_RATE:
        reasons.append("reliability_pass_rate_below_threshold")
    return not reasons, reasons


def rank_models(
    analyses: Sequence[AnalysisEnvelope | Mapping[str, Any]],
    *,
    total_frames: int | None = None,
    coverage_threshold: float = MIN_MAIN_MODEL_COVERAGE,
) -> list[dict[str, Any]]:
    """Rank valid model fits without discarding low-quality evidence.

    The ordering is deterministic: coverage (descending), median AICc rank,
    median BIC rank, residual-pass rate (descending), bound-hit rate
    (ascending), uncertainty (ascending), then model name.  Models that fail
    main-model gates (coverage, residual pass rate, bound hits, uncertainty,
    reliability) remain visible but are marked ineligible as the batch main
    model.
    """

    if not 0.0 <= coverage_threshold <= 1.0:
        raise ValueError("coverage_threshold must be in [0, 1]")
    model_items = [item for item in analyses if _is_shape_model(item) and _model_name(item) is not None]
    frame_total = _frame_count(model_items, total_frames)
    grouped: OrderedDict[str, list[AnalysisEnvelope | Mapping[str, Any]]] = OrderedDict()
    for item in model_items:
        name = _model_name(item)
        if name is not None:
            grouped.setdefault(name, []).append(item)

    summaries: list[dict[str, Any]] = []
    for model_name, items in grouped.items():
        # One model can only contribute one valid result per frame.  A duplicate
        # row is reduced to the most favorable valid result deterministically.
        per_frame: OrderedDict[str, list[AnalysisEnvelope | Mapping[str, Any]]] = OrderedDict()
        for item in items:
            per_frame.setdefault(_curve_id(item), []).append(item)
        chosen = [
            min(rows, key=_frame_model_sort_key)
            for rows in per_frame.values()
            if any(_is_valid_fit(row) for row in rows)
        ]
        valid = [item for item in chosen if _is_valid_fit(item)]
        aicc_values = [value for item in valid if (value := _metric(item, "AICc")) is not None]
        bic_values = [value for item in valid if (value := _metric(item, "BIC")) is not None]
        uncertainty_values = [value for item in valid if (value := _uncertainty(item)) is not None]
        valid_count = len(valid)
        coverage = valid_count / frame_total if frame_total else 0.0
        residual_pass_rate = (sum(_residual_pass(item) for item in valid) / valid_count) if valid_count else 0.0
        bound_hit_rate = (sum(_bound_hit(item) for item in valid) / valid_count) if valid_count else 1.0
        uncertainty = float(median(uncertainty_values)) if uncertainty_values else None
        reliability_pass_rate = (
            (sum(_reliability_ok(item) for item in valid) / valid_count) if valid_count else 0.0
        )
        eligible, eligibility_failures = _main_model_eligibility(
            coverage=coverage,
            residual_pass_rate=residual_pass_rate,
            bound_hit_rate=bound_hit_rate,
            uncertainty=uncertainty,
            reliability_pass_rate=reliability_pass_rate,
            coverage_threshold=coverage_threshold,
        )
        summaries.append(
            {
                "model_name": model_name,
                "total_frames": frame_total,
                "successful_fit_count": valid_count,
                "coverage": coverage,
                "median_aicc": float(median(aicc_values)) if aicc_values else None,
                "median_bic": float(median(bic_values)) if bic_values else None,
                "residual_pass_rate": residual_pass_rate,
                "bound_hit_rate": bound_hit_rate,
                "uncertainty": uncertainty,
                "reliability_pass_rate": reliability_pass_rate,
                "eligible_for_main_model": eligible,
                "eligibility_failures": eligibility_failures,
                "coverage_threshold": coverage_threshold,
                "residual_pass_rate_threshold": MIN_MAIN_MODEL_RESIDUAL_PASS_RATE,
                "bound_hit_rate_threshold": MAX_MAIN_MODEL_BOUND_HIT_RATE,
                "uncertainty_threshold": MAX_MAIN_MODEL_UNCERTAINTY,
                "reliability_pass_rate_threshold": MIN_MAIN_MODEL_RELIABILITY_PASS_RATE,
            }
        )

    aicc_ranks = _ascending_rank({row["model_name"]: row["median_aicc"] for row in summaries})
    bic_ranks = _ascending_rank({row["model_name"]: row["median_bic"] for row in summaries})
    for row in summaries:
        row["median_AICc"] = row["median_aicc"]
        row["median_BIC"] = row["median_bic"]
        row["median_aicc_rank"] = aicc_ranks[row["model_name"]]
        row["median_bic_rank"] = bic_ranks[row["model_name"]]

    def sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            -float(row["coverage"]),
            row["median_aicc_rank"] if row["median_aicc_rank"] is not None else math.inf,
            row["median_bic_rank"] if row["median_bic_rank"] is not None else math.inf,
            -float(row["residual_pass_rate"]),
            float(row["bound_hit_rate"]),
            float(row["uncertainty"]) if row["uncertainty"] is not None else math.inf,
            str(row["model_name"]),
        )

    summaries.sort(key=sort_key)
    for index, row in enumerate(summaries, start=1):
        row["rank"] = index
    return summaries


def select_batch_main_model(
    rankings: Sequence[Mapping[str, Any]] | Sequence[AnalysisEnvelope],
    *,
    coverage_threshold: float = MIN_MAIN_MODEL_COVERAGE,
) -> str | None:
    """Choose one fixed batch-level main model using full eligibility gates."""

    if not rankings:
        return None
    first = rankings[0]
    normalized: list[Mapping[str, Any]]
    if isinstance(first, AnalysisEnvelope):
        normalized = rank_models(rankings, coverage_threshold=coverage_threshold)
    else:
        normalized = [item for item in rankings if isinstance(item, Mapping)]
    eligible = [item for item in normalized if bool(item.get("eligible_for_main_model"))]
    if not eligible:
        return None
    selected = min(eligible, key=lambda item: (int(item.get("rank", math.inf)), str(item.get("model_name", ""))))
    value = selected.get("model_name")
    return str(value) if value not in (None, "") else None


def _frame_model_sort_key(item: AnalysisEnvelope | Mapping[str, Any]) -> tuple[Any, ...]:
    aicc = _metric(item, "AICc")
    bic = _metric(item, "BIC")
    uncertainty = _uncertainty(item)
    return (
        0 if _is_valid_fit(item) else 1,
        aicc if aicc is not None else math.inf,
        bic if bic is not None else math.inf,
        0 if _residual_pass(item) else 1,
        1 if _bound_hit(item) else 0,
        uncertainty if uncertainty is not None else math.inf,
        _model_name(item) or "",
    )


def flag_possible_model_transitions(
    analyses: Sequence[AnalysisEnvelope | Mapping[str, Any]],
    main_model: str | None,
    *,
    consecutive_frames: int = 3,
) -> list[dict[str, Any]]:
    """Flag a different per-frame winner only after a sustained three-frame run.

    The supplied ``main_model`` is copied into every output row and is never
    changed.  These are review flags, not automatic model switches.
    """

    if isinstance(consecutive_frames, bool) or not isinstance(consecutive_frames, int) or consecutive_frames < 1:
        raise ValueError("consecutive_frames must be a positive integer")
    by_frame: OrderedDict[str, list[AnalysisEnvelope | Mapping[str, Any]]] = OrderedDict()
    for item in analyses:
        if _is_shape_model(item) and _model_name(item) is not None:
            by_frame.setdefault(_curve_id(item), []).append(item)

    flags: list[dict[str, Any]] = []
    active_candidate: str | None = None
    streak = 0
    for curve_id, items in by_frame.items():
        valid = [item for item in items if _is_valid_fit(item)]
        best = min(valid, key=_frame_model_sort_key) if valid else None
        best_name = _model_name(best) if best is not None else None
        if main_model is None or best_name is None or best_name == main_model:
            active_candidate = None
            streak = 0
        elif best_name == active_candidate:
            streak += 1
        else:
            active_candidate = best_name
            streak = 1
        flags.append(
            {
                "curve_id": curve_id,
                "curve_name": _curve_name(items[0]),
                "main_model": main_model,
                "frame_best_model": best_name,
                "candidate_model": active_candidate,
                "consecutive_frames": streak,
                "required_consecutive_frames": consecutive_frames,
                "possible_model_transition": bool(active_candidate is not None and streak >= consecutive_frames),
                "reason": (
                    "alternative_model_wins_required_consecutive_frames"
                    if active_candidate is not None and streak >= consecutive_frames
                    else None
                ),
            }
        )
    return flags


__all__ = [
    "MAX_MAIN_MODEL_BOUND_HIT_RATE",
    "MAX_MAIN_MODEL_UNCERTAINTY",
    "MIN_MAIN_MODEL_COVERAGE",
    "MIN_MAIN_MODEL_RELIABILITY_PASS_RATE",
    "MIN_MAIN_MODEL_RESIDUAL_PASS_RATE",
    "flag_possible_model_transitions",
    "rank_models",
    "select_batch_main_model",
]
