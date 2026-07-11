from __future__ import annotations

import math
import numbers

import numpy as np

from app.core.analysis_schema import RESULT_GROUP_POROD, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.model_free import power_law_analysis
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _finite_scalar(value) -> float | None:
    """Return a built-in finite float, or ``None`` for an unavailable scalar."""

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _finite_statistics(values: np.ndarray) -> dict:
    """Return finite plateau statistics without publishing overflowed reductions."""

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

    minimum = _finite_scalar(np.min(values))
    maximum = _finite_scalar(np.max(values))
    median = _finite_scalar(np.median(values))
    scale = _finite_scalar(np.max(np.abs(values)))
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
        mean = _finite_scalar(scale * np.mean(scaled))
        std = _finite_scalar(scale * np.std(scaled))
        value_range = _finite_scalar(maximum - minimum) if minimum is not None and maximum is not None else None
    if mean is None or std is None or value_range is None:
        return {
            **empty,
            "min": minimum,
            "max": maximum,
            "median": median,
            "reduction_reason": "statistical_reduction_overflowed_or_became_non_finite",
        }
    cv = _finite_scalar(std / abs(mean)) if mean != 0.0 else None
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


def _normalized_contrast(contrast) -> tuple[float | None, float | None, str | None]:
    """Validate contrast and its denominator before an absolute Porod division."""

    if contrast is None:
        return None, None, "contrast_not_supplied"
    if isinstance(contrast, bool) or not isinstance(contrast, numbers.Real):
        return None, None, "contrast_must_be_a_finite_numeric_value"
    value = _finite_scalar(contrast)
    if value is None:
        return None, None, "contrast_must_be_finite"
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        squared = value * value
        denominator = 2.0 * math.pi * squared
    if not math.isfinite(squared) or squared <= 0.0:
        return None, None, "contrast_square_is_not_finite_and_positive"
    if not math.isfinite(denominator) or denominator <= 0.0:
        return None, None, "contrast_denominator_is_not_finite_and_positive"
    return value, float(denominator), None


def _plateau_candidate(q: np.ndarray, q4i: np.ndarray, *, relative_step_tolerance: float = 0.2) -> dict:
    """Choose the longest contiguous locally stable q⁴I segment.

    This is a numerical candidate only.  Its validity remains separately
    reported through point-count, sign, and relative-variation checks.
    """

    if not q.size:
        return {
            "q_min": None,
            "q_max": None,
            "points": 0,
            "values": np.array([], dtype=float),
            "reason": "no_finite_q4I_points",
        }
    if q.size == 1:
        return {
            "q_min": float(q[0]),
            "q_max": float(q[0]),
            "points": 1,
            "values": q4i.copy(),
            "reason": "fewer_than_two_contiguous_points",
        }

    left_values = q4i[:-1]
    right_values = q4i[1:]
    pair_scale = np.maximum(np.maximum(np.abs(left_values), np.abs(right_values)), np.finfo(float).tiny)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        scaled_difference = np.abs((left_values / pair_scale) - (right_values / pair_scale))
        scaled_pair_mean = 0.5 * ((left_values / pair_scale) + (right_values / pair_scale))
        relative_step = scaled_difference / np.abs(scaled_pair_mean)
    stable_edges = np.isfinite(relative_step) & (relative_step <= relative_step_tolerance)
    runs: list[tuple[int, int]] = []
    start = 0
    for edge_index, stable in enumerate(stable_edges):
        if not stable:
            runs.append((start, edge_index + 1))
            start = edge_index + 1
    runs.append((start, q.size))
    run_start, run_end = max(runs, key=lambda bounds: (bounds[1] - bounds[0], -bounds[0]))
    candidate_values = q4i[run_start:run_end]
    return {
        "q_min": float(q[run_start]),
        "q_max": float(q[run_end - 1]),
        "points": int(run_end - run_start),
        "values": candidate_values,
        "reason": "longest_contiguous_local_step_candidate",
    }


def porod_deep_analysis(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    contrast: float | None = None,
    volume_fraction: float | None = None,
    absolute_intensity: bool = False,
    two_phase_confirmed: bool = False,
) -> AnalysisResult:
    mask = (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & (curve.q >= q_range[0])
        & (curve.q <= q_range[1])
    )
    selected_q = curve.q[mask]
    selected_intensity = curve.intensity[mask]
    if selected_q.size > 1:
        order = np.argsort(selected_q, kind="stable")
        selected_q = selected_q[order]
        selected_intensity = selected_intensity[order]
    with np.errstate(over="ignore", invalid="ignore"):
        selected_q4i = selected_q**4 * selected_intensity
    finite_q4i_mask = np.isfinite(selected_q4i)
    q = selected_q[finite_q4i_mask]
    intensity = selected_intensity[finite_q4i_mask]
    q4i = selected_q4i[finite_q4i_mask]
    selected_stats = _finite_statistics(q4i)
    plateau_mean = selected_stats["mean"]
    plateau_std = selected_stats["std"]
    plateau_cv = selected_stats["cv"]
    candidate = _plateau_candidate(q, q4i)
    candidate_stats = _finite_statistics(candidate["values"])
    candidate_valid = bool(
        candidate["points"] >= 5
        and candidate_stats["mean"] is not None
        and candidate_stats["mean"] > 0.0
        and candidate_stats["cv"] is not None
        and candidate_stats["cv"] <= 0.2
    )
    candidate_reason = candidate["reason"]
    if candidate["points"] < 5:
        candidate_reason = "fewer_than_five_candidate_points"
    elif candidate_stats["reduction_reason"] is not None:
        candidate_reason = f"candidate_statistics_unavailable:{candidate_stats['reduction_reason']}"
    elif candidate_stats["mean"] is None or candidate_stats["mean"] <= 0.0:
        candidate_reason = "candidate_plateau_not_positive"
    elif candidate_stats["cv"] is None or candidate_stats["cv"] > 0.2:
        candidate_reason = "candidate_relative_variation_above_0.2"
    else:
        candidate_reason = "candidate_passes_point_sign_and_relative_variation_checks"
    power = power_law_analysis(curve, q_range, min_points=5) if q.size >= 5 else None
    alpha = None if power is None else _finite_scalar(power.results.get("alpha"))
    contrast_value, contrast_denominator, contrast_reason = _normalized_contrast(contrast)
    absolute_intensity_confirmed = absolute_intensity is True
    two_phase_is_confirmed = two_phase_confirmed is True
    specific_surface_candidate = None
    interface_area_density_candidate = None
    stable_positive_plateau = plateau_mean is not None and plateau_mean > 0 and plateau_cv is not None and plateau_cv <= 0.2
    porod_like_alpha = alpha is not None and abs(alpha - 4.0) <= 0.4
    if (
        absolute_intensity_confirmed
        and contrast_denominator is not None
        and two_phase_is_confirmed
        and candidate_valid
        and porod_like_alpha
    ):
        surface_value = _finite_scalar(candidate_stats["mean"] / contrast_denominator)
        if surface_value is not None and surface_value > 0.0:
            interface_area_density_candidate = surface_value
            specific_surface_candidate = surface_value
    assumptions = []
    if not absolute_intensity_confirmed:
        assumptions.append("absolute_intensity_required")
    if contrast_value is None:
        assumptions.append("contrast_required")
    if not two_phase_is_confirmed:
        assumptions.append("two_phase_required")
    if volume_fraction is None:
        assumptions.append("volume_fraction_optional_for_specific_surface_normalization")
    checks = [
        validity_check("enough_points", q.size >= 5, severity="error", message="Porod analysis needs at least five finite q⁴I high-q points.", value=int(q.size), threshold=5),
        validity_check("stable_q4I_plateau", stable_positive_plateau, severity="warning", message="q\u2074I(q) plateau is not stable or not positive.", value=plateau_cv, threshold=0.2),
        validity_check("contiguous_plateau_candidate", candidate_valid, severity="warning", message="A positive, stable contiguous q\u2074I(q) plateau candidate is required for absolute surface estimates.", value=candidate_stats["cv"], threshold=0.2),
        validity_check("porod_alpha_near_4", porod_like_alpha, severity="warning", message="Fitted high-q exponent is not close to Porod q^-4.", value=alpha, threshold="4 +/- 0.4"),
        validity_check("absolute_intensity", absolute_intensity_confirmed, severity="warning", message="Absolute intensity is required for absolute surface estimates."),
        validity_check("contrast_supplied", contrast_value is not None, severity="warning", message="Contrast is required for absolute surface estimates."),
        validity_check("two_phase_confirmed", two_phase_is_confirmed, severity="warning", message="Explicit two-phase confirmation is required for absolute surface estimates."),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    warnings = warning_messages_from_checks(checks)
    excluded_q4i_count = int(selected_q.size - q.size)
    if excluded_q4i_count:
        warnings.append(f"Excluded {excluded_q4i_count} selected points because q⁴I(q) was not finite after multiplication.")
    if selected_stats["reduction_reason"] is not None:
        warnings.append(
            "q⁴I(q) plateau statistics are unavailable because finite-value reduction would overflow or become non-finite: "
            f"{selected_stats['reduction_reason']}."
        )
    if contrast_reason is not None:
        warnings.append(f"Absolute surface candidate is unavailable because contrast validation failed: {contrast_reason}.")
    if not candidate_valid:
        warnings.append(f"Contiguous q⁴I plateau candidate is unavailable or limited: {candidate_reason}.")
    results = {
        "q4I_plateau_mean": plateau_mean,
        "q4I_plateau_std": plateau_std,
        "q4I_plateau_cv": plateau_cv,
        "q4I_plateau_min": selected_stats["min"],
        "q4I_plateau_max": selected_stats["max"],
        "q4I_plateau_median": selected_stats["median"],
        "q4I_plateau_range": selected_stats["range"],
        "q4I_plateau_q_min": float(q[0]) if q.size else None,
        "q4I_plateau_q_max": float(q[-1]) if q.size else None,
        "q4I_plateau_points": int(q.size),
        "q4I_finite_points": int(q.size),
        "q4I_excluded_nonfinite_count": excluded_q4i_count,
        "plateau_candidate_q_min": candidate["q_min"],
        "plateau_candidate_q_max": candidate["q_max"],
        "plateau_candidate_range": {"q_min": candidate["q_min"], "q_max": candidate["q_max"]},
        "plateau_candidate_points": candidate["points"],
        "plateau_candidate_mean": candidate_stats["mean"],
        "plateau_candidate_std": candidate_stats["std"],
        "plateau_candidate_cv": candidate_stats["cv"],
        "plateau_candidate_min": candidate_stats["min"],
        "plateau_candidate_max": candidate_stats["max"],
        "plateau_candidate_median": candidate_stats["median"],
        "plateau_candidate_value_range": candidate_stats["range"],
        "plateau_candidate_valid": candidate_valid,
        "plateau_candidate_reason": candidate_reason,
        "noise_score": candidate_stats["cv"],
        "q4I_noise_score": candidate_stats["cv"],
        "power_law_alpha": alpha,
        "specific_surface_candidate": specific_surface_candidate,
        "interface_area_density_candidate": interface_area_density_candidate,
        "contrast": contrast_value,
        "contrast_validity_reason": contrast_reason,
        "volume_fraction": _finite_scalar(volume_fraction),
        "absolute_intensity": absolute_intensity_confirmed,
        "two_phase_confirmed": two_phase_is_confirmed,
        "points": int(selected_q.size),
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_POROD,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Porod surface estimates require a two-phase system, absolute intensity, known contrast, and a stable q\u2074I plateau.",
            "If these assumptions are missing, plateau metrics are descriptive only.",
        ],
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="porod_deep",
        q_range=q_range,
        parameters={
            "contrast": contrast_value,
            "contrast_validity_reason": contrast_reason,
            "volume_fraction": _finite_scalar(volume_fraction),
            "absolute_intensity": absolute_intensity_confirmed,
            "two_phase_confirmed": two_phase_is_confirmed,
        },
        results=results,
        warnings=warnings,
    )

