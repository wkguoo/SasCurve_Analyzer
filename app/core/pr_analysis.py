from __future__ import annotations

import numpy as np
from scipy.optimize import nnls

from app.core.analysis_schema import EXPORT_TABLE_PR_DISTRIBUTION, RESULT_GROUP_PR, merge_standard_metadata
from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import AnalysisResult, CurveData
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def _range_mask(curve: CurveData, q_range: tuple[float, float]) -> np.ndarray:
    return (
        np.isfinite(curve.q)
        & np.isfinite(curve.intensity)
        & (curve.q > 0)
        & np.isfinite(curve.intensity)
        & (curve.q >= q_range[0])
        & (curve.q <= q_range[1])
    )


def _second_difference_matrix(size: int) -> np.ndarray:
    if size < 3:
        return np.zeros((0, size))
    matrix = np.zeros((size - 2, size))
    for row in range(size - 2):
        matrix[row, row] = 1.0
        matrix[row, row + 1] = -2.0
        matrix[row, row + 2] = 1.0
    return matrix


def compute_pr(
    curve: CurveData,
    q_range: tuple[float, float],
    dmax: float,
    regularization: float | None = None,
    *,
    r_points: int = 80,
) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    q, intensity = sort_arrays_by_q(curve.q[mask], curve.intensity[mask])
    warnings: list[str] = []
    if regularization is None:
        regularization = 1e-2
    if dmax <= 0:
        raise ValueError("dmax must be positive.")
    if r_points < 10:
        raise ValueError("r_points must be at least 10.")

    r = np.linspace(0.0, dmax, r_points)
    pr = np.zeros_like(r)
    fit_i = np.full_like(q, np.nan, dtype=float)
    residuals = np.full_like(q, np.nan, dtype=float)
    negative_fraction = 0.0
    rg_from_pr = None
    i0_from_pr = None
    distribution_peak_r = None
    distribution_width = None

    checks = [
        validity_check("enough_q_points", q.size >= 12, severity="error", message="P(r) needs at least 12 valid q points.", value=int(q.size), threshold=12),
        validity_check("positive_dmax", dmax > 0, severity="error", message="Dmax must be positive.", value=dmax),
        validity_check("dmax_q_coverage", float(q.max() * dmax) >= 6.0 if q.size else False, severity="warning", message="q_max * Dmax is low; real-space resolution is weak.", value=float(q.max() * dmax) if q.size else None, threshold=6.0),
    ]

    if q.size >= 12:
        dr = float(r[1] - r[0])
        qr = np.outer(q, r)
        kernel = np.ones_like(qr)
        nonzero = np.abs(qr) > 1e-12
        kernel[nonzero] = np.sin(qr[nonzero]) / qr[nonzero]
        kernel *= dr
        smooth = _second_difference_matrix(r.size)
        lhs = np.vstack([kernel, np.sqrt(max(0.0, regularization)) * smooth])
        rhs = np.concatenate([intensity, np.zeros(smooth.shape[0])])
        pr, _ = nnls(lhs, rhs)
        fit_i = kernel @ pr
        residuals = intensity - fit_i
        raw_solution, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)
        negative_fraction = float(np.mean(raw_solution < 0)) if raw_solution.size else 0.0
        area = float(np.trapezoid(pr, r))
        if area > 0:
            i0_from_pr = area
            rg_sq = float(np.trapezoid((r**2) * pr, r) / (2.0 * area))
            rg_from_pr = float(np.sqrt(max(0.0, rg_sq)))
            distribution_peak_r = float(r[int(np.argmax(pr))])
            mean_r = float(np.trapezoid(r * pr, r) / area)
            variance = float(np.trapezoid(((r - mean_r) ** 2) * pr, r) / area)
            distribution_width = float(np.sqrt(max(0.0, variance)))
        checks.append(validity_check("nonzero_pr_area", area > 0, severity="error", message="Recovered P(r) area is zero.", value=area))
        checks.append(validity_check("negative_unconstrained_fraction", negative_fraction <= 0.25, severity="warning", message="Unconstrained P(r) has substantial negative fraction; Dmax/regularization may be unstable.", value=negative_fraction, threshold=0.25))

    label, score = reliability_from_checks(
        checks,
        assumptions=["dilute_particle_required", "user_supplied_dmax_required", "regularization_dependent"],
    )
    warnings.extend(warning_messages_from_checks(checks))
    results = {
        "r": r.tolist(),
        "P(r)": pr.tolist(),
        "Dmax": float(dmax),
        "regularization": float(regularization),
        "Rg_from_pr": rg_from_pr,
        "I0_from_pr": i0_from_pr,
        "distribution_peak_r": distribution_peak_r,
        "distribution_width": distribution_width,
        "negative_unconstrained_fraction": negative_fraction,
        "fit_q": q.tolist(),
        "fit_I": fit_i.tolist(),
        "residuals": residuals.tolist(),
    }
    pr_table = [{"r": float(rv), "P(r)": float(pv)} for rv, pv in zip(r, pr)]
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_PR,
        reliability_label=label,
        reliability_score=score,
        assumptions=["dilute_particle_required", "user_supplied_dmax_required", "regularization_dependent"],
        validity_checks=checks,
        interpretation_limits=[
            "P(r) inversion is non-unique and depends on Dmax, background quality, q range, and regularization.",
            "Treat distribution shape as a constrained candidate, not a standalone proof of particle size distribution.",
        ],
        export_tables={EXPORT_TABLE_PR_DISTRIBUTION: pr_table},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="pr",
        q_range=q_range,
        parameters={"dmax": dmax, "regularization": regularization, "r_points": r_points},
        results=results,
        warnings=warnings,
    )

