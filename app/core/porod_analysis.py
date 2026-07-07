from __future__ import annotations

import numpy as np

from app.core.analysis_schema import RESULT_GROUP_POROD, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.model_free import power_law_analysis
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def porod_deep_analysis(
    curve: CurveData,
    q_range: tuple[float, float],
    *,
    contrast: float | None = None,
    volume_fraction: float | None = None,
    absolute_intensity: bool = False,
) -> AnalysisResult:
    mask = (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & (curve.q >= q_range[0])
        & (curve.q <= q_range[1])
    )
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    q4i = q**4 * intensity
    plateau_mean = float(np.nanmean(q4i)) if q4i.size else None
    plateau_std = float(np.nanstd(q4i)) if q4i.size else None
    plateau_cv = float(plateau_std / abs(plateau_mean)) if plateau_mean not in (None, 0.0) else None
    power = power_law_analysis(curve, q_range, min_points=5) if q.size >= 5 else None
    alpha = None if power is None else power.results.get("alpha")
    specific_surface_candidate = None
    interface_area_density_candidate = None
    stable_positive_plateau = plateau_mean is not None and plateau_mean > 0 and plateau_cv is not None and plateau_cv <= 0.2
    porod_like_alpha = alpha is not None and abs(float(alpha) - 4.0) <= 0.4
    if absolute_intensity and contrast not in (None, 0.0) and stable_positive_plateau and porod_like_alpha:
        interface_area_density_candidate = float(plateau_mean / (2.0 * np.pi * contrast**2))
        specific_surface_candidate = interface_area_density_candidate
    assumptions = []
    if contrast is None or not absolute_intensity:
        assumptions.extend(["absolute_intensity_required", "contrast_required", "two_phase_required"])
    if volume_fraction is None:
        assumptions.append("volume_fraction_optional_for_specific_surface_normalization")
    checks = [
        validity_check("enough_points", q.size >= 5, severity="error", message="Porod analysis needs at least five high-q points.", value=int(q.size), threshold=5),
        validity_check("stable_q4I_plateau", stable_positive_plateau, severity="warning", message="q^4I(q) plateau is not stable or not positive.", value=plateau_cv, threshold=0.2),
        validity_check("porod_alpha_near_4", porod_like_alpha, severity="warning", message="Fitted high-q exponent is not close to Porod q^-4.", value=alpha, threshold="4 +/- 0.4"),
        validity_check("absolute_intensity", absolute_intensity, severity="warning", message="Absolute intensity is required for absolute surface estimates."),
        validity_check("contrast_supplied", contrast is not None and contrast != 0, severity="warning", message="Contrast is required for absolute surface estimates."),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    results = {
        "q4I_plateau_mean": plateau_mean,
        "q4I_plateau_std": plateau_std,
        "q4I_plateau_cv": plateau_cv,
        "power_law_alpha": alpha,
        "specific_surface_candidate": specific_surface_candidate,
        "interface_area_density_candidate": interface_area_density_candidate,
        "contrast": contrast,
        "volume_fraction": volume_fraction,
        "absolute_intensity": absolute_intensity,
        "points": int(q.size),
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_POROD,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Porod surface estimates require a two-phase system, absolute intensity, known contrast, and a stable q^4I plateau.",
            "If these assumptions are missing, plateau metrics are descriptive only.",
        ],
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="porod_deep",
        q_range=q_range,
        parameters={"contrast": contrast, "volume_fraction": volume_fraction, "absolute_intensity": absolute_intensity},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )

