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


def invariant_with_extrapolation(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    low_q_method: str = "disabled",
    high_q_method: str = "disabled",
    contrast: float | None = None,
    absolute_intensity: bool = False,
) -> AnalysisResult:
    q, intensity = _valid_range(curve, q_range)
    if q.size >= 2:
        q_measured = float(np.trapezoid(q**2 * intensity, q))
        q_min = float(q.min())
        q_max = float(q.max())
    else:
        q_measured = float("nan")
        q_min = float("nan")
        q_max = float("nan")

    low_q_contribution = 0.0
    high_q_contribution = 0.0
    extrapolation_notes: list[str] = []
    if q.size >= 3 and low_q_method == "constant":
        low_q_contribution = float(intensity[0] * q_min**3 / 3.0)
        extrapolation_notes.append("Low-q constant extrapolation used.")
    elif q.size >= 5 and low_q_method == "guinier":
        guinier = guinier_analysis(curve, (q_min, q[min(q.size - 1, max(4, q.size // 5))]))
        rg = guinier.results.get("Rg")
        i0 = guinier.results.get("I0")
        if rg is not None and i0 is not None:
            q_low = np.linspace(0.0, q_min, 80)
            low_i = float(i0) * np.exp(-(float(rg) ** 2) * q_low**2 / 3.0)
            low_q_contribution = float(np.trapezoid(q_low**2 * low_i, q_low))
            extrapolation_notes.append("Low-q Guinier extrapolation used.")
    if q.size >= 3 and high_q_method == "porod_q^-4":
        porod_constant = float(np.median((q[-max(3, q.size // 10) :] ** 4) * intensity[-max(3, q.size // 10) :]))
        high_q_contribution = float(porod_constant / q_max) if q_max > 0 else 0.0
        extrapolation_notes.append("High-q Porod q^-4 extrapolation used.")
    elif q.size >= 6 and high_q_method == "power_law":
        start = max(0, q.size - max(6, q.size // 4))
        power = power_law_analysis(curve, (float(q[start]), q_max), min_points=5)
        alpha = power.results.get("alpha")
        prefactor = power.results.get("prefactor")
        if alpha is not None and prefactor is not None and alpha > 3.0:
            high_q_contribution = float(prefactor * (q_max ** (3.0 - alpha)) / (alpha - 3.0))
            extrapolation_notes.append("High-q power-law extrapolation used.")

    q_total = q_measured + low_q_contribution + high_q_contribution
    contrast_factor = None
    volume_fraction_candidate = None
    can_estimate_volume_fraction = (
        absolute_intensity
        and contrast is not None
        and contrast != 0
        and np.isfinite(contrast)
        and np.isfinite(q_total)
        and q_total > 0
        and q.size >= 5
    )
    if can_estimate_volume_fraction:
        contrast_factor = float(q_total / (2.0 * np.pi**2 * contrast**2))
        if 0.0 <= contrast_factor <= 0.25:
            volume_fraction_candidate = float((1.0 - np.sqrt(1.0 - 4.0 * contrast_factor)) / 2.0)

    assumptions = []
    if low_q_method != "disabled" or high_q_method != "disabled":
        assumptions.append("q_extrapolation_assumption")
    if contrast is None or not absolute_intensity:
        assumptions.extend(["absolute_intensity_required", "contrast_required", "two_phase_required"])
    checks = [
        validity_check("enough_points", q.size >= 5, severity="error", message="Invariant needs at least five points.", value=int(q.size), threshold=5),
        validity_check("absolute_intensity", absolute_intensity, severity="warning", message="Absolute intensity is required for volume-fraction interpretation."),
        validity_check("contrast_supplied", contrast is not None and contrast != 0, severity="warning", message="Contrast is required for volume-fraction interpretation."),
        validity_check("volume_fraction_physical", volume_fraction_candidate is not None if contrast is not None and absolute_intensity else True, severity="warning", message="Invariant/contrast combination does not give a physical 0-0.5 volume fraction."),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    results = {
        "Q_measured": q_measured,
        "Q_low_q_extrapolated": low_q_contribution,
        "Q_high_q_extrapolated": high_q_contribution,
        "Q_total": q_total,
        "q_min": q_min,
        "q_max": q_max,
        "integration_points": int(q.size),
        "low_q_method": low_q_method,
        "high_q_method": high_q_method,
        "contrast": contrast,
        "absolute_intensity": absolute_intensity,
        "contrast_factor_phi_1_minus_phi": contrast_factor,
        "volume_fraction_candidate": volume_fraction_candidate,
        "extrapolation_notes": extrapolation_notes,
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
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="invariant_deep",
        q_range=q_range,
        parameters={"low_q_method": low_q_method, "high_q_method": high_q_method, "contrast": contrast, "absolute_intensity": absolute_intensity},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )
