"""Optional, reproducible uncertainty summaries for already-selected SAS fits.

This module has no knowledge of GUI, files, or a specific fitting model.  A
caller supplies a callback that refits an in-memory point-index sample or q
range.  Callback failures are captured in the returned audit instead of being
allowed to invalidate the primary fit that requested the optional analysis.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.core.cancellation import cancellation_requested


FitCallback = Callable[[np.ndarray], Any]
RangeCallback = Callable[[tuple[float, float]], Any]
_QUANTILE_LEVELS = (0.025, 0.5, 0.975)
_QUANTILE_NAMES = ("p2_5", "p50", "p97_5")
_CALLBACK_METADATA_KEYS = frozenset(
    {
        "analysis_type",
        "converged",
        "error",
        "error_message",
        "failure_count",
        "fit_points",
        "model_name",
        "reason",
        "status",
        "success",
        "success_count",
        "valid",
        "warnings",
    }
)


def _finite_float(value: Any) -> float | None:
    """Return a finite numeric scalar without coercing sequences or arrays."""

    if isinstance(value, (bool, np.bool_, np.ndarray, str, bytes)):
        return None
    if not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if np.isfinite(numeric) else None


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a positive integer")
    numeric = _finite_float(value)
    if numeric is None or not numeric.is_integer() or numeric <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(numeric)


def _seed_value(value: Any) -> tuple[int | None, str | None]:
    """Validate a native or NumPy non-negative integer seed scalar."""

    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        return None, "seed_must_be_non_negative_finite_integer"
    numeric = int(value)
    if numeric < 0:
        return None, "seed_must_be_non_negative_finite_integer"
    return numeric, None


def _config_option(config: Any | None, name: str, default: Any) -> Any:
    """Read an optional configuration field without importing batch orchestration."""

    if config is None:
        return default
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


def _disabled_summary(
    *,
    method: str,
    seed: int | None,
    sample_count: int | None,
    variant_count: int,
    minimum_valid_fits: int,
    reason: str,
) -> "UncertaintySummary":
    return UncertaintySummary(
        method=method,
        enabled=False,
        status="not_enabled",
        reason=reason,
        seed=seed,
        sample_count=sample_count,
        variant_count=variant_count,
        success_count=0,
        failure_count=0,
        minimum_valid_fits=minimum_valid_fits,
        parameter_quantiles={},
        coefficient_of_variation={},
        coefficient_of_variation_reasons={},
        sensitivity_score=None,
        sensitivity_reason=reason,
        attempts=[],
    )


def _invalid_summary(
    *,
    method: str,
    reason: str,
    seed: int | None,
    sample_count: int | None,
    variant_count: int,
    minimum_valid_fits: int,
) -> "UncertaintySummary":
    return UncertaintySummary(
        method=method,
        enabled=True,
        status="invalid_input",
        reason=reason,
        seed=seed,
        sample_count=sample_count,
        variant_count=variant_count,
        success_count=0,
        failure_count=0,
        minimum_valid_fits=minimum_valid_fits,
        parameter_quantiles={},
        coefficient_of_variation={},
        coefficient_of_variation_reasons={},
        sensitivity_score=None,
        sensitivity_reason=reason,
        attempts=[],
    )


@dataclass(frozen=True)
class UncertaintySummary:
    """JSON-safe result of an optional bootstrap or q-range calculation.

    ``status`` describes only the optional uncertainty calculation.  It must
    never be interpreted as the validity status of the primary fit.
    """

    method: str
    enabled: bool
    status: str
    reason: str | None
    seed: int | None
    sample_count: int | None
    variant_count: int
    success_count: int
    failure_count: int
    minimum_valid_fits: int
    parameter_quantiles: dict[str, dict[str, float | None]]
    coefficient_of_variation: dict[str, float | None]
    coefficient_of_variation_reasons: dict[str, str | None]
    sensitivity_score: float | None
    sensitivity_reason: str | None
    attempts: list[dict[str, Any]]

    @property
    def parameter_cv(self) -> dict[str, float | None]:
        """Compatibility-friendly alias for coefficient-of-variation values."""

        return self.coefficient_of_variation

    @property
    def successful_fit_count(self) -> int:
        return self.success_count

    @property
    def failed_fit_count(self) -> int:
        return self.failure_count

    def to_dict(self) -> dict[str, Any]:
        """Return native finite values and explicit null reasons for export."""

        return {
            "method": self.method,
            "enabled": bool(self.enabled),
            "status": self.status,
            "reason": self.reason,
            "seed": self.seed,
            "sample_count": self.sample_count,
            "variant_count": self.variant_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "successful_fit_count": self.successful_fit_count,
            "failed_fit_count": self.failed_fit_count,
            "minimum_valid_fits": self.minimum_valid_fits,
            "parameter_quantiles": self.parameter_quantiles,
            "coefficient_of_variation": self.coefficient_of_variation,
            "parameter_cv": self.parameter_cv,
            "coefficient_of_variation_reasons": self.coefficient_of_variation_reasons,
            "sensitivity_score": self.sensitivity_score,
            "sensitivity_reason": self.sensitivity_reason,
            "attempts": self.attempts,
        }


def _resolve_included_indices(
    fit_callback: FitCallback,
    included_indices: Sequence[Any] | np.ndarray | None,
) -> tuple[np.ndarray | None, str | None]:
    source = included_indices
    if source is None:
        for attribute_name in ("included_indices", "included_point_indices", "valid_indices", "indices"):
            candidate = getattr(fit_callback, attribute_name, None)
            if candidate is not None:
                source = candidate
                break
    if source is None:
        return None, "included_indices_not_supplied"
    try:
        raw = np.asarray(source, dtype=float)
    except (TypeError, ValueError):
        return None, "included_indices_not_numeric"
    if raw.ndim != 1 or raw.size == 0:
        return None, "included_indices_empty_or_not_one_dimensional"
    if not np.all(np.isfinite(raw)) or not np.all(raw == np.floor(raw)) or np.any(raw < 0.0):
        return None, "included_indices_must_be_non_negative_finite_integers"
    return raw.astype(int, copy=True), None


def _parameter_mapping(value: Any) -> tuple[dict[str, float] | None, str | None]:
    """Extract finite fitted parameters from common core-result shapes."""

    source = value
    if hasattr(source, "results") and isinstance(getattr(source, "results"), Mapping):
        source = getattr(source, "results")
    if not isinstance(source, Mapping):
        return None, "callback_returned_non_mapping"
    converged = source.get("converged")
    if isinstance(converged, (bool, np.bool_)) and not bool(converged):
        return None, "callback_reported_nonconvergence"

    has_parameters = "parameters" in source
    has_parameter_records = "parameter_records" in source
    candidates: Any = source.get("parameters", source.get("parameter_records", source))
    extracted: dict[str, float] = {}
    if isinstance(candidates, Mapping):
        for name, raw_value in candidates.items():
            if not has_parameters and not has_parameter_records and str(name) in _CALLBACK_METADATA_KEYS:
                continue
            item = raw_value.get("value") if isinstance(raw_value, Mapping) else raw_value
            numeric = _finite_float(item)
            if numeric is not None:
                extracted[str(name)] = numeric
    elif isinstance(candidates, Sequence) and not isinstance(candidates, (str, bytes)):
        for row in candidates:
            if not isinstance(row, Mapping) or "name" not in row:
                continue
            numeric = _finite_float(row.get("value"))
            if numeric is not None:
                extracted[str(row["name"])] = numeric
    if not extracted:
        return None, "callback_returned_no_finite_parameters"
    return extracted, None


def _q_range_bounds(value: Any) -> tuple[float | None, float | None]:
    """Require exactly two non-boolean finite numeric q bounds."""

    if isinstance(value, np.ndarray):
        if value.ndim != 1 or value.size != 2:
            return None, None
        bounds = (value[0], value[1])
    elif isinstance(value, (str, bytes, Mapping)):
        return None, None
    else:
        try:
            bounds = list(value)
        except TypeError:
            return None, None
    if len(bounds) != 2:
        return None, None
    q_low = _finite_float(bounds[0])
    q_high = _finite_float(bounds[1])
    if q_low is None or q_high is None or q_low >= q_high:
        return None, None
    return q_low, q_high


def _attempt_row(
    *,
    attempt_index: int,
    success: bool,
    reason: str | None,
    parameters: Mapping[str, float] | None,
    resampled_indices: np.ndarray | None = None,
    q_range: tuple[float | None, float | None] | None = None,
    lower_shift_fraction: float | None = None,
    upper_shift_fraction: float | None = None,
) -> dict[str, Any]:
    return {
        "attempt_index": int(attempt_index),
        "success": bool(success),
        "reason": reason,
        "parameters": {} if parameters is None else {str(name): _finite_float(value) for name, value in parameters.items()},
        "resampled_indices": None if resampled_indices is None else [int(index) for index in resampled_indices],
        "q_range": None if q_range is None else [_finite_float(q_range[0]), _finite_float(q_range[1])],
        "lower_shift_fraction": _finite_float(lower_shift_fraction),
        "upper_shift_fraction": _finite_float(upper_shift_fraction),
    }


def _statistics(parameter_rows: Sequence[Mapping[str, float]]) -> tuple[
    dict[str, dict[str, float | None]],
    dict[str, float | None],
    dict[str, str | None],
    float | None,
    str | None,
]:
    values_by_name: dict[str, list[float]] = {}
    for row in parameter_rows:
        for name, value in row.items():
            numeric = _finite_float(value)
            if numeric is not None:
                values_by_name.setdefault(str(name), []).append(numeric)

    quantiles: dict[str, dict[str, float | None]] = {}
    coefficient_of_variation: dict[str, float | None] = {}
    cv_reasons: dict[str, str | None] = {}
    bounded_scores: list[float] = []
    for name in sorted(values_by_name):
        values = np.asarray(values_by_name[name], dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            raw_quantiles = np.quantile(values, _QUANTILE_LEVELS)
        quantiles[name] = {
            label: _finite_float(raw_quantiles[index])
            for index, label in enumerate(_QUANTILE_NAMES)
        }
        if values.size < 2:
            coefficient_of_variation[name] = None
            cv_reasons[name] = "fewer_than_two_valid_parameter_values"
            continue
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            mean = np.mean(values)
            standard_deviation = np.std(values, ddof=1)
            cv = _finite_float(standard_deviation / abs(mean)) if mean != 0.0 else None
        if cv is None:
            coefficient_of_variation[name] = None
            cv_reasons[name] = "zero_or_non_finite_parameter_mean_or_variation"
            continue
        coefficient_of_variation[name] = cv
        cv_reasons[name] = None
        bounded_scores.append(float(cv / (1.0 + cv)))

    if bounded_scores:
        sensitivity_score = _finite_float(max(bounded_scores))
        return quantiles, coefficient_of_variation, cv_reasons, sensitivity_score, None
    return (
        quantiles,
        coefficient_of_variation,
        cv_reasons,
        None,
        "no_finite_parameter_coefficient_of_variation",
    )


def _completed_summary(
    *,
    method: str,
    seed: int | None,
    sample_count: int | None,
    variant_count: int,
    minimum_valid_fits: int,
    successes: Sequence[Mapping[str, float]],
    attempts: list[dict[str, Any]],
    cancelled: bool = False,
) -> UncertaintySummary:
    success_count = len(successes)
    failure_count = sum(not bool(row["success"]) for row in attempts)
    if cancelled:
        quantiles, cv, cv_reasons, sensitivity_score, sensitivity_reason = _statistics(successes)
        return UncertaintySummary(
            method=method,
            enabled=True,
            status="cancelled",
            reason="cancel_requested",
            seed=seed,
            sample_count=sample_count,
            variant_count=variant_count,
            success_count=success_count,
            failure_count=failure_count,
            minimum_valid_fits=minimum_valid_fits,
            parameter_quantiles=quantiles,
            coefficient_of_variation=cv,
            coefficient_of_variation_reasons=cv_reasons,
            sensitivity_score=sensitivity_score,
            sensitivity_reason=sensitivity_reason or "cancel_requested",
            attempts=attempts,
        )
    if success_count < minimum_valid_fits:
        return UncertaintySummary(
            method=method,
            enabled=True,
            status="insufficient_valid_fits",
            reason="success_count_below_minimum_valid_fits",
            seed=seed,
            sample_count=sample_count,
            variant_count=variant_count,
            success_count=success_count,
            failure_count=failure_count,
            minimum_valid_fits=minimum_valid_fits,
            parameter_quantiles={},
            coefficient_of_variation={},
            coefficient_of_variation_reasons={},
            sensitivity_score=None,
            sensitivity_reason="success_count_below_minimum_valid_fits",
            attempts=attempts,
        )
    quantiles, cv, cv_reasons, sensitivity_score, sensitivity_reason = _statistics(successes)
    return UncertaintySummary(
        method=method,
        enabled=True,
        status="completed",
        reason=None,
        seed=seed,
        sample_count=sample_count,
        variant_count=variant_count,
        success_count=success_count,
        failure_count=failure_count,
        minimum_valid_fits=minimum_valid_fits,
        parameter_quantiles=quantiles,
        coefficient_of_variation=cv,
        coefficient_of_variation_reasons=cv_reasons,
        sensitivity_score=sensitivity_score,
        sensitivity_reason=sensitivity_reason,
        attempts=attempts,
    )


def bootstrap_fit(
    fit_callback: FitCallback,
    *,
    included_indices: Sequence[Any] | np.ndarray | None = None,
    sample_count: int = 200,
    seed: int = 12345,
    enabled: bool = True,
    minimum_valid_fits: int = 3,
    config: Any | None = None,
) -> UncertaintySummary:
    """Resample included point indices with replacement and summarize refits.

    To keep the function independent of any particular curve class, callers
    pass explicit ``included_indices`` or attach one of the documented index
    attributes to the callback.  Failures from the optional callback become
    auditable failed attempts, not exceptions that invalidate the primary fit.
    """

    sample_count = _config_option(config, "bootstrap_samples", sample_count)
    seed = _config_option(config, "bootstrap_seed", seed)
    enabled = _config_option(config, "enable_bootstrap", enabled)
    count = _positive_int(sample_count, "sample_count")
    minimum = _positive_int(minimum_valid_fits, "minimum_valid_fits")
    if not isinstance(enabled, (bool, np.bool_)):
        raise ValueError("enabled must be a boolean")
    computation_seed, seed_reason = _seed_value(seed)
    if not enabled:
        return _disabled_summary(
            method="bootstrap",
            seed=computation_seed,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
            reason="bootstrap_not_enabled",
        )
    if seed_reason is not None:
        return _invalid_summary(
            method="bootstrap",
            reason=seed_reason,
            seed=None,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
        )

    base_indices, index_reason = _resolve_included_indices(fit_callback, included_indices)
    if base_indices is None:
        return UncertaintySummary(
            method="bootstrap",
            enabled=True,
            status="missing_prerequisite",
            reason=index_reason,
            seed=computation_seed,
            sample_count=count,
            variant_count=0,
            success_count=0,
            failure_count=0,
            minimum_valid_fits=minimum,
            parameter_quantiles={},
            coefficient_of_variation={},
            coefficient_of_variation_reasons={},
            sensitivity_score=None,
            sensitivity_reason=index_reason,
            attempts=[],
        )

    try:
        generator = np.random.default_rng(computation_seed)
    except (TypeError, ValueError, OverflowError):
        return _invalid_summary(
            method="bootstrap",
            reason="seed_must_be_non_negative_finite_integer",
            seed=None,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
        )
    successes: list[dict[str, float]] = []
    attempts: list[dict[str, Any]] = []
    cancelled = False
    for attempt_index in range(count):
        if cancellation_requested():
            cancelled = True
            break
        sampled_indices = generator.choice(base_indices, size=base_indices.size, replace=True)
        try:
            parameters, reason = _parameter_mapping(fit_callback(sampled_indices.copy()))
        except Exception as exc:  # Optional callback failures must remain isolated.
            parameters = None
            reason = f"callback_exception:{type(exc).__name__}"
        success = parameters is not None
        if success:
            successes.append(parameters)
        attempts.append(
            _attempt_row(
                attempt_index=attempt_index,
                success=success,
                reason=reason,
                parameters=parameters,
                resampled_indices=sampled_indices,
            )
        )
    return _completed_summary(
        method="bootstrap",
        seed=computation_seed,
        sample_count=count,
        variant_count=0,
        minimum_valid_fits=minimum,
        successes=successes,
        attempts=attempts,
        cancelled=cancelled,
    )


def moving_block_residual_bootstrap_fit(
    fit_callback: FitCallback,
    *,
    residual_count: int,
    sample_count: int = 200,
    seed: int = 12345,
    block_length: int = 0,
    enabled: bool = True,
    minimum_valid_fits: int = 3,
    config: Any | None = None,
) -> UncertaintySummary:
    """Bootstrap residual donor indices in contiguous moving blocks.

    The fitted q grid remains fixed and ordered.  Only residual donors are
    resampled; consecutive residuals inside each block retain their original
    order.  This is a robustness calculation, not a substitute for instrument
    measurement errors.
    """

    sample_count = _config_option(config, "bootstrap_samples", sample_count)
    seed = _config_option(config, "bootstrap_seed", seed)
    block_length = _config_option(config, "bootstrap_block_length", block_length)
    enabled = _config_option(config, "enable_bootstrap", enabled)
    count = _positive_int(sample_count, "sample_count")
    minimum = _positive_int(minimum_valid_fits, "minimum_valid_fits")
    n_residuals = _positive_int(residual_count, "residual_count")
    if not isinstance(enabled, (bool, np.bool_)):
        raise ValueError("enabled must be a boolean")
    computation_seed, seed_reason = _seed_value(seed)
    if not enabled:
        return _disabled_summary(
            method="moving_block_residual_bootstrap",
            seed=computation_seed,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
            reason="bootstrap_not_enabled",
        )
    if seed_reason is not None:
        return _invalid_summary(
            method="moving_block_residual_bootstrap",
            reason=seed_reason,
            seed=None,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
        )
    if isinstance(block_length, (bool, np.bool_)):
        return _invalid_summary(
            method="moving_block_residual_bootstrap",
            reason="block_length_must_be_zero_or_positive_integer",
            seed=computation_seed,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
        )
    try:
        configured_block = int(block_length)
    except (TypeError, ValueError, OverflowError):
        configured_block = -1
    if configured_block < 0 or configured_block != block_length:
        return _invalid_summary(
            method="moving_block_residual_bootstrap",
            reason="block_length_must_be_zero_or_positive_integer",
            seed=computation_seed,
            sample_count=count,
            variant_count=0,
            minimum_valid_fits=minimum,
        )
    actual_block = configured_block or max(2, int(round(n_residuals ** (1.0 / 3.0))))
    actual_block = min(actual_block, n_residuals)
    generator = np.random.default_rng(computation_seed)
    successes: list[dict[str, float]] = []
    attempts: list[dict[str, Any]] = []
    base = np.arange(n_residuals, dtype=int)
    block_count = int(np.ceil(n_residuals / actual_block))
    cancelled = False
    for attempt_index in range(count):
        if cancellation_requested():
            cancelled = True
            break
        starts = generator.integers(0, n_residuals, size=block_count)
        donor_indices = np.concatenate(
            [base[(start + np.arange(actual_block)) % n_residuals] for start in starts]
        )[:n_residuals]
        try:
            parameters, reason = _parameter_mapping(fit_callback(donor_indices.copy()))
        except Exception as exc:
            parameters = None
            reason = f"callback_exception:{type(exc).__name__}"
        success = parameters is not None
        if success:
            successes.append(parameters)
        row = _attempt_row(
            attempt_index=attempt_index,
            success=success,
            reason=reason,
            parameters=parameters,
            resampled_indices=donor_indices,
        )
        row["block_length"] = actual_block
        row["q_order_preserved"] = True
        attempts.append(row)
    return _completed_summary(
        method="moving_block_residual_bootstrap",
        seed=computation_seed,
        sample_count=count,
        variant_count=0,
        minimum_valid_fits=minimum,
        successes=successes,
        attempts=attempts,
        cancelled=cancelled,
    )


def range_sensitivity(
    range_callback: RangeCallback,
    q_range: tuple[float, float],
    *,
    boundary_fraction: float = 0.05,
    enabled: bool = True,
    minimum_valid_fits: int = 3,
    hard_q_range: tuple[float, float] | None = None,
    config: Any | None = None,
) -> UncertaintySummary:
    """Refit all nine lower/upper boundary combinations around a q range."""

    boundary_fraction = _config_option(config, "sensitivity_boundary_fraction", boundary_fraction)
    enabled = _config_option(config, "enable_range_sensitivity", enabled)
    minimum = _positive_int(minimum_valid_fits, "minimum_valid_fits")
    if not isinstance(enabled, (bool, np.bool_)):
        raise ValueError("enabled must be a boolean")
    if not enabled:
        return _disabled_summary(
            method="range_sensitivity",
            seed=None,
            sample_count=None,
            variant_count=0,
            minimum_valid_fits=minimum,
            reason="range_sensitivity_not_enabled",
        )

    fraction = _finite_float(boundary_fraction)
    if fraction is None or not 0.0 < fraction < 0.5:
        return _invalid_summary(
            method="range_sensitivity",
            reason="boundary_fraction_must_be_finite_and_in_(0,0.5)",
            seed=None,
            sample_count=None,
            variant_count=0,
            minimum_valid_fits=minimum,
        )
    q_low, q_high = _q_range_bounds(q_range)
    if q_low is None or q_high is None:
        return _invalid_summary(
            method="range_sensitivity",
            reason="q_range_must_contain_two_finite_ascending_bounds",
            seed=None,
            sample_count=None,
            variant_count=0,
            minimum_valid_fits=minimum,
        )

    hard_low, hard_high = (None, None)
    if hard_q_range is not None:
        hard_low, hard_high = _q_range_bounds(hard_q_range)
        if hard_low is None or hard_high is None:
            return _invalid_summary(
                method="range_sensitivity",
                reason="hard_q_range_must_contain_two_finite_ascending_bounds",
                seed=None,
                sample_count=None,
                variant_count=0,
                minimum_valid_fits=minimum,
            )

    width = q_high - q_low
    shifts = (-fraction, 0.0, fraction)
    successes: list[dict[str, float]] = []
    attempts: list[dict[str, Any]] = []
    cancelled = False
    for lower_shift in shifts:
        for upper_shift in shifts:
            if cancellation_requested():
                cancelled = True
                break
            variant_low = _finite_float(q_low + lower_shift * width)
            variant_high = _finite_float(q_high + upper_shift * width)
            if variant_low is not None and hard_low is not None:
                variant_low = max(variant_low, hard_low)
            if variant_high is not None and hard_high is not None:
                variant_high = min(variant_high, hard_high)
            attempt_index = len(attempts)
            if variant_low is None or variant_high is None or variant_low >= variant_high:
                attempts.append(
                    _attempt_row(
                        attempt_index=attempt_index,
                        success=False,
                        reason="invalid_boundary_variant",
                        parameters=None,
                        q_range=(variant_low, variant_high),
                        lower_shift_fraction=lower_shift,
                        upper_shift_fraction=upper_shift,
                    )
                )
                continue
            try:
                parameters, reason = _parameter_mapping(range_callback((variant_low, variant_high)))
            except Exception as exc:  # Optional callback failures must remain isolated.
                parameters = None
                reason = f"callback_exception:{type(exc).__name__}"
            success = parameters is not None
            if success:
                successes.append(parameters)
            attempts.append(
                _attempt_row(
                    attempt_index=attempt_index,
                    success=success,
                    reason=reason,
                    parameters=parameters,
                    q_range=(variant_low, variant_high),
                    lower_shift_fraction=lower_shift,
                    upper_shift_fraction=upper_shift,
                )
            )
        if cancelled:
            break
    return _completed_summary(
        method="range_sensitivity",
        seed=None,
        sample_count=None,
        variant_count=len(attempts),
        minimum_valid_fits=minimum,
        successes=successes,
        attempts=attempts,
        cancelled=cancelled,
    )


__all__ = [
    "UncertaintySummary",
    "bootstrap_fit",
    "moving_block_residual_bootstrap_fit",
    "range_sensitivity",
]
