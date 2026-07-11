from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from app.core.analysis_schema import EXPORT_TABLE_CORRELATION_FUNCTION, RESULT_GROUP_TWO_PHASE, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def compute_correlation_function(
    curve: CurveData,
    q_range: tuple[float, float],
    options: dict | None = None,
) -> AnalysisResult:
    options = dict(options or {})
    r_points = int(options.get("r_points", 200))
    r_max = options.get("r_max")
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
    if r_max is None:
        r_max = 200.0
        if q.size > 2:
            minimum_spacing = float(np.min(np.diff(q)))
            if minimum_spacing > 0.0:
                with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                    candidate_r_max = float(2.0 * np.pi / minimum_spacing)
                if np.isfinite(candidate_r_max) and candidate_r_max > 0.0:
                    r_max = candidate_r_max
    else:
        try:
            r_max = float(r_max)
        except (TypeError, ValueError) as exc:
            raise ValueError("r_max must be a finite positive number.") from exc
    if not (np.isfinite(r_max) and r_max > 0.0):
        raise ValueError("r_max must be a finite positive number.")
    r = np.linspace(0.0, r_max, max(20, r_points))
    gamma = np.full_like(r, np.nan, dtype=float)
    transform_normalization = None
    transform_normalization_status = "missing_prerequisite"
    transform_normalization_invalid_reason = "At least six valid q/I(q) points and a finite non-zero q^2 I(q) transform normalization are required."
    if q.size >= 6:
        with np.errstate(over="ignore", invalid="ignore"):
            weighted = q**2 * intensity
        if not np.all(np.isfinite(weighted)):
            transform_normalization_status = "invalid_value"
            transform_normalization_invalid_reason = "q^2 I(q) became non-finite before correlation-transform normalization."
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                denom = float(np.trapezoid(weighted, q))
            if np.isfinite(denom) and denom != 0.0:
                transform_normalization = denom
                transform_normalization_status = "available"
                transform_normalization_invalid_reason = None
                for index, rv in enumerate(r):
                    with np.errstate(over="ignore", invalid="ignore"):
                        gamma_candidate = float(np.trapezoid(weighted * np.cos(q * rv), q) / denom)
                    if np.isfinite(gamma_candidate):
                        gamma[index] = gamma_candidate
            else:
                transform_normalization_status = "invalid_value"
                transform_normalization_invalid_reason = "The q^2 I(q) transform normalization was zero, overflowed, or became non-finite."
    peaks, _ = find_peaks(gamma[1:]) if gamma.size > 3 and np.all(np.isfinite(gamma)) else (np.asarray([], dtype=int), {})
    peaks = peaks + 1
    first_peak_r = float(r[peaks[0]]) if peaks.size else None
    zero_crossings = np.where(np.diff(np.signbit(gamma)))[0] if np.all(np.isfinite(gamma)) else np.asarray([], dtype=int)
    first_zero_r = float(r[zero_crossings[0]]) if zero_crossings.size else None
    damping_length = None
    if gamma.size > 3 and np.isfinite(gamma[0]):
        below = np.where(np.abs(gamma) < 0.1 * max(1e-12, abs(gamma[0])))[0]
        damping_length = float(r[below[0]]) if below.size else None
    checks = [
        validity_check("enough_points", q.size >= 12, severity="error", message="Correlation function needs at least 12 valid q points.", value=int(q.size), threshold=12),
        validity_check("r_max_positive", np.isfinite(r_max) and r_max > 0, severity="error", message="r_max must be a finite positive number.", value=r_max),
        validity_check("finite_transform_normalization", transform_normalization_status == "available", severity="error", message="Correlation transform requires a finite non-zero q^2 I(q) normalization.", value=transform_normalization),
        validity_check("has_positive_peak", first_peak_r is not None, severity="warning", message="No non-zero positive correlation peak was detected."),
    ]
    assumptions = [
        "two_phase_or_lamellar_required",
        "sample_type_not_confirmed",
        "finite_q_transform",
        "extrapolation_sensitive",
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    if label == "high":
        label = "assumption_dependent"
    long_period_status = "assumption_dependent" if first_peak_r is not None else "missing_prerequisite"
    long_period_invalid_reason = (
        "A non-zero correlation peak is reported only as a two-phase or lamellar model-dependent length candidate."
        if first_peak_r is not None
        else "No non-zero positive correlation peak was detected in the finite-q transform."
    )
    interface_thickness_status = "assumption_dependent" if first_zero_r is not None else "missing_prerequisite"
    interface_thickness_invalid_reason = (
        "The first zero crossing is only a model-dependent thickness candidate and is not a direct interface measurement."
        if first_zero_r is not None
        else "No correlation zero crossing was detected in the finite-q transform."
    )
    q_extrapolation_status = "finite_range"
    q_extrapolation_invalid_reason = "The cosine transform uses only the selected measured q range; unmeasured q tails were not extrapolated."
    table = [
        {"r": float(rv), "correlation": float(gv) if np.isfinite(gv) else None}
        for rv, gv in zip(r, gamma)
    ]
    results = {
        "r": r.tolist(),
        "correlation": [float(gv) if np.isfinite(gv) else None for gv in gamma],
        "q_min": float(q.min()) if q.size else None,
        "q_max": float(q.max()) if q.size else None,
        "integration_points": int(q.size),
        "r_max": float(r_max),
        "r_resolution": float(r[1] - r[0]) if r.size > 1 else None,
        "transform_normalization": transform_normalization,
        "transform_normalization_status": transform_normalization_status,
        "transform_normalization_invalid_reason": transform_normalization_invalid_reason,
        "first_peak_r": first_peak_r,
        "long_period_candidate": first_peak_r,
        "long_period": first_peak_r,
        "long_period_status": long_period_status,
        "long_period_invalid_reason": long_period_invalid_reason,
        "first_zero_r": first_zero_r,
        "interface_thickness_candidate": first_zero_r,
        "interface_thickness": first_zero_r,
        "interface_thickness_status": interface_thickness_status,
        "interface_thickness_invalid_reason": interface_thickness_invalid_reason,
        "damping_length_candidate": damping_length,
        "damping_length": damping_length,
        "damping_length_status": "assumption_dependent" if damping_length is not None else "missing_prerequisite",
        "damping_length_invalid_reason": "Damping length is a finite-q transform descriptor, not a standalone morphology measurement." if damping_length is not None else "The correlation function did not decay below the selected threshold.",
        "correlation_length": damping_length,
        "correlation_length_status": "assumption_dependent" if damping_length is not None else "missing_prerequisite",
        "correlation_length_invalid_reason": "Correlation length is a finite-q transform descriptor, not a standalone morphology measurement." if damping_length is not None else "The correlation function did not decay below the selected threshold.",
        "hard_phase_thickness": None,
        "hard_phase_thickness_status": "missing_prerequisite",
        "hard_phase_thickness_invalid_reason": "Hard-phase thickness requires a validated two-phase model and phase-fraction information not available from this normalized transform.",
        "soft_phase_thickness": None,
        "soft_phase_thickness_status": "missing_prerequisite",
        "soft_phase_thickness_invalid_reason": "Soft-phase thickness requires a validated two-phase model and phase-fraction information not available from this normalized transform.",
        "phase_fraction_indicator": None,
        "phase_fraction_indicator_status": "missing_prerequisite",
        "phase_fraction_indicator_invalid_reason": "A phase-fraction indicator requires a validated two-phase interpretation and additional absolute or contrast information.",
        "peak_count": int(peaks.size),
        "q_extrapolation_status": q_extrapolation_status,
        "q_extrapolation_invalid_reason": q_extrapolation_invalid_reason,
        "prerequisites": {
            "sample_type": {
                "status": "assumption_required",
                "reason": "Long-period and thickness interpretation requires a two-phase or lamellar sample model that is not confirmed by this calculation.",
            },
            "absolute_intensity": {
                "status": "not_required",
                "reason": "The reported correlation function is normalized; absolute intensity is not used for this conditional descriptor.",
            },
            "contrast": {
                "status": "not_required",
                "reason": "Contrast is not used for the normalized transform, but is required for absolute two-phase quantities outside this function.",
            },
            "q_extrapolation": {"status": q_extrapolation_status, "reason": q_extrapolation_invalid_reason},
            "porod_plateau": {
                "status": "not_applicable",
                "reason": "No Porod extrapolation is performed by this finite-q correlation transform.",
            },
        },
        "assumption_status": "assumption_dependent",
        "analysis_status": "assumption_dependent",
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_TWO_PHASE,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "This finite-q cosine transform is a candidate correlation function, not a fully extrapolated two-phase invariant analysis.",
            "Long period and interface thickness candidates require lamellar or two-phase assumptions.",
        ],
        export_tables={EXPORT_TABLE_CORRELATION_FUNCTION: table},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="correlation_function",
        q_range=q_range,
        parameters=options,
        results=results,
        warnings=warning_messages_from_checks(checks),
    )
