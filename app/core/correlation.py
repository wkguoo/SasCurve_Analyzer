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
        r_max = float(2.0 * np.pi / np.min(np.diff(q))) if q.size > 2 and np.min(np.diff(q)) > 0 else 200.0
    r = np.linspace(0.0, float(r_max), max(20, r_points))
    gamma = np.zeros_like(r)
    if q.size >= 6:
        weighted = q**2 * intensity
        denom = float(np.trapezoid(weighted, q))
        if denom != 0:
            for index, rv in enumerate(r):
                gamma[index] = float(np.trapezoid(weighted * np.cos(q * rv), q) / denom)
    peaks, _ = find_peaks(gamma[1:]) if gamma.size > 3 else (np.asarray([], dtype=int), {})
    peaks = peaks + 1
    first_peak_r = float(r[peaks[0]]) if peaks.size else None
    zero_crossings = np.where(np.diff(np.signbit(gamma)))[0]
    first_zero_r = float(r[zero_crossings[0]]) if zero_crossings.size else None
    damping_length = None
    if gamma.size > 3:
        below = np.where(np.abs(gamma) < 0.1 * max(1e-12, abs(gamma[0])))[0]
        damping_length = float(r[below[0]]) if below.size else None
    checks = [
        validity_check("enough_points", q.size >= 12, severity="error", message="Correlation function needs at least 12 valid q points.", value=int(q.size), threshold=12),
        validity_check("r_max_positive", float(r_max) > 0, severity="error", message="r_max must be positive.", value=float(r_max)),
        validity_check("has_positive_peak", first_peak_r is not None, severity="warning", message="No non-zero positive correlation peak was detected."),
    ]
    assumptions = ["two_phase_or_lamellar_required", "finite_q_transform", "extrapolation_sensitive"]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    table = [{"r": float(rv), "correlation": float(gv)} for rv, gv in zip(r, gamma)]
    results = {
        "r": r.tolist(),
        "correlation": gamma.tolist(),
        "first_peak_r": first_peak_r,
        "long_period_candidate": first_peak_r,
        "first_zero_r": first_zero_r,
        "interface_thickness_candidate": first_zero_r,
        "damping_length_candidate": damping_length,
        "peak_count": int(peaks.size),
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
