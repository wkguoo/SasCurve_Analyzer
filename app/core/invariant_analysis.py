from __future__ import annotations

import numpy as np

from app.core.analysis_schema import RESULT_GROUP_INVARIANT, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.model_free import guinier_analysis, power_law_analysis
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _valid_range(curve: CurveData, q_range: tuple[float, float]) -> tuple[np.ndarray, np.ndarray]:
    mask = (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & (curve.q >= q_range[0])
        & (curve.q <= q_range[1])
    )
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if q.size > 1:
        order = np.argsort(q)
        q = q[order]
        intensity = intensity[order]
    return q, intensity


def _safe_trapezoid(values: np.ndarray, q: np.ndarray) -> float | None:
    if values.size < 2 or q.size < 2:
        return None
    if not (np.all(np.isfinite(values)) and np.all(np.isfinite(q))):
        return None
    with np.errstate(over="ignore", invalid="ignore"):
        integral = float(np.trapezoid(values, q))
    return integral if np.isfinite(integral) else None


def _integral_in_interval(q: np.ndarray, values: np.ndarray, lower: float, upper: float) -> float | None:
    if q.size < 2 or not (np.isfinite(lower) and np.isfinite(upper)):
        return None
    start = max(float(q[0]), float(lower))
    end = min(float(q[-1]), float(upper))
    if not (np.isfinite(start) and np.isfinite(end)) or end <= start:
        return None
    inside = (q > start) & (q < end)
    q_interval = np.concatenate(([start], q[inside], [end]))
    values_interval = np.interp(q_interval, q, values)
    return _safe_trapezoid(values_interval, q_interval)


def _measured_q_bands(q: np.ndarray, intensity: np.ndarray) -> tuple[dict[str, float | None], dict[str, str], dict[str, str | None], dict[str, float] | None]:
    names = ("Q_low", "Q_mid", "Q_high")
    values = {name: None for name in names}
    statuses = {name: "missing_prerequisite" for name in names}
    reasons = {name: "At least two valid q points with a finite q^2 I(q) integrand are required for measured-range band integration." for name in names}
    if q.size < 2:
        return values, statuses, reasons, None
    q_min = float(q[0])
    q_max = float(q[-1])
    first_boundary = (2.0 * q_min / 3.0) + (q_max / 3.0)
    second_boundary = (q_min / 3.0) + (2.0 * q_max / 3.0)
    if not (np.isfinite(first_boundary) and np.isfinite(second_boundary) and q_min < first_boundary < second_boundary < q_max):
        reasons = {name: "Finite increasing q-band boundaries could not be constructed from the selected range." for name in names}
        return values, statuses, reasons, None
    with np.errstate(over="ignore", invalid="ignore"):
        integrand = q**2 * intensity
    if not np.all(np.isfinite(integrand)):
        statuses = {name: "invalid_value" for name in names}
        reasons = {name: "q^2 I(q) became non-finite, so the measured-range band integral is unavailable." for name in names}
        return values, statuses, reasons, {"low_mid": first_boundary, "mid_high": second_boundary}
    intervals = (("Q_low", q_min, first_boundary), ("Q_mid", first_boundary, second_boundary), ("Q_high", second_boundary, q_max))
    for name, lower, upper in intervals:
        integral = _integral_in_interval(q, integrand, lower, upper)
        if integral is None:
            statuses[name] = "invalid_value"
            reasons[name] = "Finite trapezoidal integration of this measured q band overflowed or became non-finite."
        else:
            values[name] = integral
            statuses[name] = "available"
            reasons[name] = None
    return values, statuses, reasons, {"low_mid": first_boundary, "mid_high": second_boundary}


def invariant_with_extrapolation(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    low_q_method: str = "disabled",
    high_q_method: str = "disabled",
    contrast: float | None = None,
    absolute_intensity: bool = False,
) -> AnalysisResult:
    contrast_value = None
    contrast_invalid_reason = None
    if contrast is not None:
        try:
            candidate_contrast = float(contrast)
        except (TypeError, ValueError):
            contrast_invalid_reason = "Scattering contrast must be numeric, finite, and non-zero."
        else:
            if np.isfinite(candidate_contrast):
                contrast_value = candidate_contrast
            else:
                contrast_invalid_reason = "Scattering contrast was non-finite and was withheld from the result."
    if contrast_value is None:
        contrast_status = "missing_prerequisite"
        contrast_reason = contrast_invalid_reason or "Scattering contrast is required."
    elif contrast_value == 0.0:
        contrast_status = "missing_prerequisite"
        contrast_reason = "Scattering contrast must be non-zero."
    else:
        contrast_status = "satisfied"
        contrast_reason = None
    q, intensity = _valid_range(curve, q_range)
    q_measured = None
    q_measured_status = "missing_prerequisite"
    q_measured_invalid_reason = "At least two finite selected q/I(q) points are required for the measured invariant."
    if q.size:
        q_min = float(q.min())
        q_max = float(q.max())
    else:
        q_min = None
        q_max = None
    if q.size >= 2:
        with np.errstate(over="ignore", invalid="ignore"):
            measured_integrand = q**2 * intensity
        q_measured = _safe_trapezoid(measured_integrand, q)
        if q_measured is None:
            q_measured_status = "invalid_value"
            q_measured_invalid_reason = "q^2 I(q) or its trapezoidal integration became non-finite."
        else:
            q_measured_status = "available"
            q_measured_invalid_reason = None

    measured_bands, measured_band_statuses, measured_band_reasons, q_band_boundaries = _measured_q_bands(q, intensity)

    low_q_contribution = None
    high_q_contribution = None
    low_q_for_total = 0.0
    high_q_for_total = 0.0
    low_q_status = "not_requested" if low_q_method == "disabled" else "missing_prerequisite"
    high_q_status = "not_requested" if high_q_method == "disabled" else "missing_prerequisite"
    low_q_invalid_reason = "No low-q extrapolation method was requested." if low_q_method == "disabled" else "Insufficient valid points for the requested low-q extrapolation."
    high_q_invalid_reason = "No high-q extrapolation method was requested." if high_q_method == "disabled" else "Insufficient valid points for the requested high-q extrapolation."
    porod_plateau_status = "not_applicable" if high_q_method != "porod_q^-4" else "missing_prerequisite"
    porod_plateau_invalid_reason = (
        "Porod plateau validation is only applicable to the porod_q^-4 high-q method."
        if high_q_method != "porod_q^-4"
        else "At least three finite selected tail points are required for a Porod q^-4 extrapolation."
    )
    porod_plateau_relative_spread = None
    extrapolation_notes: list[str] = []
    if q.size >= 3 and low_q_method == "constant":
        with np.errstate(over="ignore", invalid="ignore"):
            low_candidate = np.float64(intensity[0]) * np.float64(q_min) ** 3 / 3.0
        if np.isfinite(low_candidate):
            low_q_contribution = float(low_candidate)
            low_q_for_total = low_q_contribution
            low_q_status = "available"
            low_q_invalid_reason = None
            extrapolation_notes.append("Low-q constant extrapolation used.")
        else:
            low_q_status = "invalid_value"
            low_q_invalid_reason = "The low-q constant extrapolation integral overflowed or became non-finite."
    elif q.size >= 5 and low_q_method == "guinier":
        guinier = guinier_analysis(curve, (q_min, q[min(q.size - 1, max(4, q.size // 5))]))
        rg = guinier.results.get("Rg")
        i0 = guinier.results.get("I0")
        if rg is not None and i0 is not None:
            q_low = np.linspace(0.0, q_min, 80)
            with np.errstate(over="ignore", invalid="ignore"):
                low_i = float(i0) * np.exp(-(float(rg) ** 2) * q_low**2 / 3.0)
                low_integrand = q_low**2 * low_i
            low_candidate = _safe_trapezoid(low_integrand, q_low)
            if low_candidate is not None:
                low_q_contribution = low_candidate
                low_q_for_total = low_q_contribution
                low_q_status = "available"
                low_q_invalid_reason = None
                extrapolation_notes.append("Low-q Guinier extrapolation used.")
            else:
                low_q_status = "invalid_value"
                low_q_invalid_reason = "The low-q Guinier extrapolation integral overflowed or became non-finite."
        else:
            low_q_invalid_reason = "The low-q Guinier fit did not return finite Rg and I0 values."
    elif low_q_method not in {"disabled", "constant", "guinier"}:
        low_q_status = "invalid_method"
        low_q_invalid_reason = "Supported low-q methods are 'disabled', 'constant', and 'guinier'."
    if high_q_method == "porod_q^-4":
        if q.size >= 3:
            tail_points = max(3, q.size // 10)
            with np.errstate(over="ignore", invalid="ignore"):
                porod_values = (q[-tail_points:] ** 4) * intensity[-tail_points:]
            if not np.all(np.isfinite(porod_values)):
                porod_plateau_status = "invalid_value"
                porod_plateau_invalid_reason = "Every selected q^4 I(q) tail value must be finite for Porod extrapolation."
                high_q_status = "invalid_value"
                high_q_invalid_reason = porod_plateau_invalid_reason
            elif not np.all(porod_values > 0.0):
                porod_plateau_status = "invalid_value"
                porod_plateau_invalid_reason = "Every selected q^4 I(q) tail value must be strictly positive for Porod extrapolation."
                high_q_status = "invalid_value"
                high_q_invalid_reason = porod_plateau_invalid_reason
            else:
                porod_constant = float(np.median(porod_values))
                with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                    normalized_values = porod_values / porod_constant
                if not (np.isfinite(porod_constant) and porod_constant > 0.0 and np.all(np.isfinite(normalized_values))):
                    porod_plateau_status = "invalid_value"
                    porod_plateau_invalid_reason = "A finite positive Porod plateau constant and finite normalized tail values are required."
                    high_q_status = "invalid_value"
                    high_q_invalid_reason = porod_plateau_invalid_reason
                else:
                    normalized_mean = float(np.mean(normalized_values))
                    normalized_std = float(np.std(normalized_values))
                    if np.isfinite(normalized_mean) and normalized_mean > 0.0 and np.isfinite(normalized_std):
                        porod_plateau_relative_spread = float(normalized_std / normalized_mean)
                    if porod_plateau_relative_spread is None or not np.isfinite(porod_plateau_relative_spread) or porod_plateau_relative_spread > 0.15:
                        porod_plateau_status = "invalid_value"
                        porod_plateau_invalid_reason = "The selected positive q^4 I(q) tail values do not meet the Porod relative-spread threshold of 0.15."
                        high_q_status = "invalid_value"
                        high_q_invalid_reason = porod_plateau_invalid_reason
                    else:
                        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                            contribution_candidate = porod_constant / q_max
                        if np.isfinite(contribution_candidate) and contribution_candidate > 0.0:
                            high_q_contribution = float(contribution_candidate)
                            high_q_for_total = high_q_contribution
                            high_q_status = "available"
                            high_q_invalid_reason = None
                            porod_plateau_status = "satisfied"
                            porod_plateau_invalid_reason = None
                            extrapolation_notes.append("High-q Porod q^-4 extrapolation used after plateau validation.")
                        else:
                            porod_plateau_status = "invalid_value"
                            porod_plateau_invalid_reason = "The Porod tail integral was not finite and positive."
                            high_q_status = "invalid_value"
                            high_q_invalid_reason = porod_plateau_invalid_reason
        else:
            high_q_status = "missing_prerequisite"
            high_q_invalid_reason = porod_plateau_invalid_reason
    elif q.size >= 6 and high_q_method == "power_law":
        start = max(0, q.size - max(6, q.size // 4))
        power = power_law_analysis(curve, (float(q[start]), q_max), min_points=5)
        alpha = power.results.get("alpha")
        prefactor = power.results.get("prefactor")
        if alpha is not None and prefactor is not None and np.isfinite(alpha) and np.isfinite(prefactor) and alpha > 3.0:
            high_q_contribution = float(prefactor * (q_max ** (3.0 - alpha)) / (alpha - 3.0))
            if np.isfinite(high_q_contribution):
                high_q_for_total = high_q_contribution
                high_q_status = "available"
                high_q_invalid_reason = None
                extrapolation_notes.append("High-q power-law extrapolation used.")
            else:
                high_q_contribution = None
                high_q_invalid_reason = "The high-q power-law integral was not finite."
        else:
            high_q_invalid_reason = "A finite high-q power law with exponent greater than 3 is required for convergence."
    elif high_q_method not in {"disabled", "porod_q^-4", "power_law"}:
        high_q_status = "invalid_method"
        high_q_invalid_reason = "Supported high-q methods are 'disabled', 'porod_q^-4', and 'power_law'."

    if q_measured is None:
        q_total = None
        q_total_invalid_reason = q_measured_invalid_reason
    else:
        with np.errstate(over="ignore", invalid="ignore"):
            total_candidate = q_measured + low_q_for_total + high_q_for_total
        q_total = float(total_candidate) if np.isfinite(total_candidate) else None
        q_total_invalid_reason = None if q_total is not None else "The measured invariant and available extrapolation contributions did not sum to a finite value."
    if low_q_status == "available" and high_q_status == "available":
        q_extrapolation_status = "model_dependent"
        q_extrapolation_invalid_reason = "Both tails were extrapolated with user-selected models; the total invariant remains model-dependent."
    elif low_q_method == "disabled" and high_q_method == "disabled":
        q_extrapolation_status = "finite_range"
        q_extrapolation_invalid_reason = "Neither low-q nor high-q extrapolation was requested, so Q_total is limited to the measured q range."
    else:
        q_extrapolation_status = "incomplete"
        q_extrapolation_invalid_reason = "At least one required q-range tail was not successfully extrapolated."

    contrast_factor = None
    volume_fraction_candidate = None
    volume_fraction_prerequisite_reasons: list[str] = []
    if not absolute_intensity:
        volume_fraction_prerequisite_reasons.append("Absolute intensity calibration is required.")
    if contrast_status != "satisfied":
        volume_fraction_prerequisite_reasons.append(contrast_reason or "Scattering contrast must be finite and non-zero.")
    if q.size < 5:
        volume_fraction_prerequisite_reasons.append("At least five valid q points are required.")
    if q_total is None or not np.isfinite(q_total) or q_total <= 0:
        volume_fraction_prerequisite_reasons.append("The total invariant must be finite and positive.")
    can_estimate_volume_fraction = not volume_fraction_prerequisite_reasons
    if can_estimate_volume_fraction:
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            contrast_factor_candidate = q_total / (2.0 * np.pi**2 * contrast_value**2)
        if np.isfinite(contrast_factor_candidate):
            contrast_factor = float(contrast_factor_candidate)
            if 0.0 <= contrast_factor <= 0.25:
                volume_fraction_value = (1.0 - np.sqrt(1.0 - 4.0 * contrast_factor)) / 2.0
                if np.isfinite(volume_fraction_value):
                    volume_fraction_candidate = float(volume_fraction_value)

    if volume_fraction_prerequisite_reasons:
        volume_fraction_status = "missing_prerequisite"
        volume_fraction_invalid_reason = " ".join(volume_fraction_prerequisite_reasons)
    elif volume_fraction_candidate is None:
        volume_fraction_status = "invalid_value"
        volume_fraction_invalid_reason = "Invariant and contrast do not yield a physical two-phase volume fraction in the 0-0.5 branch."
    else:
        volume_fraction_status = "assumption_dependent"
        volume_fraction_invalid_reason = "The numerical value requires the unconfirmed two-phase sample-model assumption."
    contrast_factor_status = "available" if contrast_factor is not None else "missing_prerequisite"
    contrast_factor_invalid_reason = None if contrast_factor is not None else " ".join(volume_fraction_prerequisite_reasons) or "Contrast factor could not be calculated."

    assumptions = ["two_phase_required", "sample_type_not_confirmed", "finite_q_coverage"]
    if low_q_method != "disabled" or high_q_method != "disabled":
        assumptions.append("q_extrapolation_assumption")
    if contrast_status != "satisfied" or not absolute_intensity:
        assumptions.extend(["absolute_intensity_required", "contrast_required", "two_phase_required"])
    checks = [
        validity_check("enough_points", q.size >= 5, severity="error", message="Invariant needs at least five points.", value=int(q.size), threshold=5),
        validity_check("measured_invariant_finite", q_measured is not None, severity="error", message="Measured q^2 I(q) invariant must be finite.", value=q_measured),
        validity_check("absolute_intensity", absolute_intensity, severity="warning", message="Absolute intensity is required for volume-fraction interpretation."),
        validity_check("contrast_supplied", contrast_status == "satisfied", severity="warning", message="A finite non-zero contrast is required for volume-fraction interpretation."),
        validity_check("volume_fraction_physical", volume_fraction_candidate is not None if contrast_status == "satisfied" and absolute_intensity else True, severity="warning", message="Invariant/contrast combination does not give a physical 0-0.5 volume fraction."),
        validity_check("q_extrapolation_complete", q_extrapolation_status == "model_dependent", severity="warning", message="The invariant remains finite-range or has incomplete tail extrapolation.", value=q_extrapolation_status),
        validity_check("porod_plateau_valid", high_q_method != "porod_q^-4" or porod_plateau_status == "satisfied", severity="warning", message="High-q Porod extrapolation requires at least three finite, strictly positive q^4 I(q) tail values with relative spread <= 0.15.", value=porod_plateau_relative_spread, threshold=0.15),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    if label == "high":
        label = "assumption_dependent"
    integrand_table = []
    for q_value, intensity_value in zip(q, intensity):
        with np.errstate(over="ignore", invalid="ignore"):
            weighted_intensity = q_value**2 * intensity_value
        integrand_table.append(
            {
                "q": float(q_value),
                "I_observed": float(intensity_value),
                "q_squared_I": float(weighted_intensity) if np.isfinite(weighted_intensity) else None,
            }
        )
    results = {
        "Q_measured": q_measured,
        "Q_measured_status": q_measured_status,
        "Q_measured_invalid_reason": q_measured_invalid_reason,
        "Q_low": measured_bands["Q_low"],
        "Q_low_status": measured_band_statuses["Q_low"],
        "Q_low_invalid_reason": measured_band_reasons["Q_low"],
        "Q_mid": measured_bands["Q_mid"],
        "Q_mid_status": measured_band_statuses["Q_mid"],
        "Q_mid_invalid_reason": measured_band_reasons["Q_mid"],
        "Q_high": measured_bands["Q_high"],
        "Q_high_status": measured_band_statuses["Q_high"],
        "Q_high_invalid_reason": measured_band_reasons["Q_high"],
        "q_band_boundaries": q_band_boundaries,
        "Q_band_definition": {
            "integrand": "q^2 I(q)",
            "range": "selected finite q range",
            "partition": "three equal q-width bands",
            "tail_extrapolations_are_excluded": True,
        },
        "Q_low_q_extrapolated": low_q_contribution,
        "Q_high_q_extrapolated": high_q_contribution,
        "Q_total": q_total,
        "Q_total_status": "assumption_dependent" if q_total is not None else q_measured_status,
        "Q_total_invalid_reason": None if q_total is not None else q_total_invalid_reason,
        "q_min": q_min,
        "q_max": q_max,
        "integration_points": int(q.size),
        "low_q_method": low_q_method,
        "high_q_method": high_q_method,
        "low_q_extrapolation_status": low_q_status,
        "low_q_extrapolation_invalid_reason": low_q_invalid_reason,
        "high_q_extrapolation_status": high_q_status,
        "high_q_extrapolation_invalid_reason": high_q_invalid_reason,
        "q_extrapolation_status": q_extrapolation_status,
        "q_extrapolation_invalid_reason": q_extrapolation_invalid_reason,
        "porod_plateau_status": porod_plateau_status,
        "porod_plateau_invalid_reason": porod_plateau_invalid_reason,
        "porod_plateau_relative_spread": porod_plateau_relative_spread,
        "contrast": contrast_value,
        "contrast_status": contrast_status,
        "contrast_invalid_reason": contrast_reason,
        "absolute_intensity": absolute_intensity,
        "contrast_factor_phi_1_minus_phi": contrast_factor,
        "contrast_factor_phi_1_minus_phi_status": contrast_factor_status,
        "contrast_factor_phi_1_minus_phi_invalid_reason": contrast_factor_invalid_reason,
        "volume_fraction_candidate": volume_fraction_candidate,
        "volume_fraction": volume_fraction_candidate,
        "volume_fraction_status": volume_fraction_status,
        "volume_fraction_invalid_reason": volume_fraction_invalid_reason,
        "extrapolation_notes": extrapolation_notes,
        "prerequisites": {
            "sample_type": {
                "status": "assumption_required",
                "reason": "Volume-fraction interpretation requires a two-phase sample model that is not confirmed by this calculation.",
            },
            "absolute_intensity": {
                "status": "satisfied" if absolute_intensity else "missing_prerequisite",
                "reason": None if absolute_intensity else "Absolute intensity calibration was not declared.",
            },
            "contrast": {
                "status": contrast_status,
                "reason": contrast_reason,
            },
            "q_extrapolation": {"status": q_extrapolation_status, "reason": q_extrapolation_invalid_reason},
            "porod_plateau": {"status": porod_plateau_status, "reason": porod_plateau_invalid_reason},
        },
        "assumption_status": "assumption_dependent",
        "analysis_status": "assumption_dependent",
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_INVARIANT,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Measured invariant is finite-range unless low-q and high-q extrapolations are explicitly enabled.",
            "Volume fraction requires absolute intensity, correct contrast, and a two-phase interpretation.",
        ],
        export_tables={"invariant_integrand": integrand_table},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="invariant_deep",
        q_range=q_range,
        parameters={"low_q_method": low_q_method, "high_q_method": high_q_method, "contrast": contrast_value, "absolute_intensity": absolute_intensity},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )
