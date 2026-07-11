from __future__ import annotations

import warnings as warning_module

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
    if isinstance(dmax, bool):
        raise ValueError("dmax must be a finite positive number.")
    try:
        dmax = float(dmax)
    except (TypeError, ValueError) as exc:
        raise ValueError("dmax must be a finite positive number.") from exc
    if not (np.isfinite(dmax) and dmax > 0.0):
        raise ValueError("dmax must be a finite positive number.")
    if regularization is None:
        regularization = 1e-2
    elif isinstance(regularization, bool):
        raise ValueError("regularization must be a finite non-negative number.")
    else:
        try:
            regularization = float(regularization)
        except (TypeError, ValueError) as exc:
            raise ValueError("regularization must be a finite non-negative number.") from exc
    if not (np.isfinite(regularization) and regularization >= 0.0):
        raise ValueError("regularization must be a finite non-negative number.")
    mask = _range_mask(curve, q_range)
    q_selected = curve.q[mask]
    intensity_selected = curve.intensity[mask]
    error_selected = None
    uncertainty_status = "missing_prerequisite"
    uncertainty_reason = "CurveData.error was not supplied for a statistical chi-square diagnostic."
    if curve.error is not None:
        error_array = np.asarray(curve.error, dtype=float)
        if error_array.shape != curve.q.shape:
            uncertainty_reason = "CurveData.error must align one-to-one with CurveData.q before a chi-square diagnostic can be calculated."
        else:
            error_selected = error_array[mask]
            if np.all(np.isfinite(error_selected)) and np.all(error_selected > 0.0):
                uncertainty_status = "available"
                uncertainty_reason = None
            else:
                uncertainty_reason = "Selected CurveData.error values must all be finite and strictly positive for a chi-square diagnostic."
    if error_selected is not None:
        q, intensity, error_selected = sort_arrays_by_q(q_selected, intensity_selected, error_selected)
    else:
        q, intensity = sort_arrays_by_q(q_selected, intensity_selected)
    warnings: list[str] = []
    if r_points < 10:
        raise ValueError("r_points must be at least 10.")

    r = np.asarray([], dtype=float)
    pr = np.asarray([], dtype=float)
    fit_i = np.asarray([], dtype=float)
    residuals = np.asarray([], dtype=float)
    negative_fraction = None
    rg_from_pr = None
    i0_from_pr = None
    distribution_peak_r = None
    distribution_width = None
    peak_height = None
    peak_count = None
    tail_score = None
    smoothness = None
    backfit_rmse = None
    backfit_chi_square = None
    backfit_chi_square_status = "missing_prerequisite"
    backfit_chi_square_invalid_reason = None

    with np.errstate(over="ignore", invalid="ignore"):
        coverage_candidate = float(q.max() * dmax) if q.size else None
    coverage_value = coverage_candidate if coverage_candidate is not None and np.isfinite(coverage_candidate) else None
    checks = [
        validity_check("enough_q_points", q.size >= 12, severity="error", message="P(r) needs at least 12 valid q points.", value=int(q.size), threshold=12),
        validity_check("positive_dmax", dmax > 0, severity="error", message="Dmax must be positive.", value=dmax),
        validity_check("dmax_q_coverage", coverage_value is not None and coverage_value >= 6.0, severity="warning", message="q_max * Dmax must be finite and at least 6 for useful real-space resolution.", value=coverage_value, threshold=6.0),
    ]

    inversion_performed = False
    inversion_invalid_reason = "At least 12 valid q points are required to recover and back-calculate P(r)."
    if q.size >= 12:
        try:
            r_candidate = np.linspace(0.0, dmax, r_points)
            dr = float(r_candidate[1] - r_candidate[0])
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                qr = np.outer(q, r_candidate)
                kernel = np.ones_like(qr)
                nonzero = np.abs(qr) > 1e-12
                kernel[nonzero] = np.sin(qr[nonzero]) / qr[nonzero]
                kernel *= dr
                smooth = _second_difference_matrix(r_candidate.size)
                lhs = np.vstack([kernel, np.sqrt(regularization) * smooth])
                rhs = np.concatenate([intensity, np.zeros(smooth.shape[0])])
            if not (np.all(np.isfinite(r_candidate)) and np.all(np.isfinite(lhs)) and np.all(np.isfinite(rhs))):
                raise FloatingPointError("P(r) inversion matrix contains non-finite values.")
            with warning_module.catch_warnings():
                warning_module.simplefilter("ignore", RuntimeWarning)
                pr_candidate, _ = nnls(lhs, rhs)
                with np.errstate(over="ignore", invalid="ignore"):
                    fit_candidate = kernel @ pr_candidate
                    residual_candidate = intensity - fit_candidate
                    raw_solution, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)
                    area_candidate = float(np.trapezoid(pr_candidate, r_candidate))
            if not (
                np.all(np.isfinite(pr_candidate))
                and np.all(np.isfinite(fit_candidate))
                and np.all(np.isfinite(residual_candidate))
                and np.all(np.isfinite(raw_solution))
                and np.isfinite(area_candidate)
            ):
                raise FloatingPointError("P(r) inversion or its reductions became non-finite.")
        except (FloatingPointError, ValueError, np.linalg.LinAlgError):
            inversion_invalid_reason = "P(r) inversion produced a non-finite matrix, solution, back-fit, or reduction."
            checks.append(validity_check("finite_pr_solution", False, severity="error", message=inversion_invalid_reason))
        else:
            r = r_candidate
            pr = pr_candidate
            fit_i = fit_candidate
            residuals = residual_candidate
            inversion_performed = True
            negative_fraction = float(np.mean(raw_solution < 0)) if raw_solution.size else None
            area = area_candidate
            if area > 0.0:
                i0_from_pr = area
                with np.errstate(over="ignore", invalid="ignore"):
                    rg_sq_candidate = float(np.trapezoid((r**2) * pr, r) / (2.0 * area))
                    mean_r_candidate = float(np.trapezoid(r * pr, r) / area)
                    variance_candidate = float(np.trapezoid(((r - mean_r_candidate) ** 2) * pr, r) / area)
                rg_from_pr = float(np.sqrt(max(0.0, rg_sq_candidate))) if np.isfinite(rg_sq_candidate) else None
                distribution_peak_r = float(r[int(np.argmax(pr))])
                distribution_width = float(np.sqrt(max(0.0, variance_candidate))) if np.isfinite(variance_candidate) else None
                peak_height = float(np.max(pr))
                if pr.size > 2:
                    peak_indices = np.where(
                        (pr[1:-1] > pr[:-2]) & (pr[1:-1] >= pr[2:]) & (pr[1:-1] > 0.0)
                    )[0] + 1
                    peak_count = int(peak_indices.size)
                if peak_height > 0.0:
                    tail_points = max(1, min(5, pr.size // 10))
                    tail_candidate = float(np.mean(pr[-tail_points:]) / peak_height)
                    tail_score = tail_candidate if np.isfinite(tail_candidate) else None
            second_differences = np.diff(pr, n=2)
            if second_differences.size:
                smoothness_candidate = float(np.sqrt(np.mean(second_differences**2)))
                smoothness = smoothness_candidate if np.isfinite(smoothness_candidate) else None
            with np.errstate(over="ignore", invalid="ignore"):
                rmse_candidate = float(np.sqrt(np.mean(residuals**2)))
            backfit_rmse = rmse_candidate if np.isfinite(rmse_candidate) else None
            checks.append(validity_check("nonzero_pr_area", area > 0.0, severity="error", message="Recovered P(r) area is zero.", value=area))
            checks.append(validity_check("negative_unconstrained_fraction", negative_fraction is not None and negative_fraction <= 0.25, severity="warning", message="Unconstrained P(r) has substantial negative fraction; Dmax/regularization may be unstable.", value=negative_fraction, threshold=0.25))

    if not inversion_performed:
        backfit_chi_square_invalid_reason = inversion_invalid_reason
    elif uncertainty_status != "available" or error_selected is None:
        backfit_chi_square_invalid_reason = uncertainty_reason
    else:
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            standardized_residuals = residuals / error_selected
            chi_square_candidate = float(np.sum(standardized_residuals**2))
        if np.all(np.isfinite(standardized_residuals)) and np.isfinite(chi_square_candidate):
            backfit_chi_square = chi_square_candidate
            backfit_chi_square_status = "available"
            backfit_chi_square_invalid_reason = None
        else:
            backfit_chi_square_status = "invalid_value"
            backfit_chi_square_invalid_reason = "Aligned CurveData.error values produced a non-finite standardized-residual reduction."

    assumptions = [
        "dilute_particle_required",
        "user_supplied_dmax_required",
        "regularization_dependent",
        "finite_q_coverage",
    ]
    label, score = reliability_from_checks(
        checks,
        assumptions=assumptions,
    )
    if label == "high":
        label = "assumption_dependent"
    warnings.extend(warning_messages_from_checks(checks))
    pr_table = [{"r": float(rv), "P(r)": float(pv)} for rv, pv in zip(r, pr)] if inversion_performed else []
    backfit_table = [
        {
            "q": float(qv),
            "I_observed": float(observed),
            "I_back_calculated": float(backfit),
            "residual": float(residual),
        }
        for qv, observed, backfit, residual in zip(q, intensity, fit_i, residuals)
        if np.isfinite(qv) and np.isfinite(observed) and np.isfinite(backfit) and np.isfinite(residual)
    ]
    scalar_status = "assumption_dependent" if inversion_performed else "missing_prerequisite"
    scalar_reason = (
        "P(r) inversion remains conditional on Dmax, regularization, and the selected finite q range."
        if inversion_performed
        else inversion_invalid_reason
    )
    results = {
        "r": r.tolist(),
        "P(r)": pr.tolist(),
        "Dmax": float(dmax),
        "regularization": float(regularization),
        "Rg_from_pr": rg_from_pr,
        "Rg_pr": rg_from_pr,
        "Rg_pr_status": scalar_status if rg_from_pr is not None else "missing_prerequisite",
        "Rg_pr_invalid_reason": scalar_reason if rg_from_pr is not None else inversion_invalid_reason,
        "I0_from_pr": i0_from_pr,
        "distribution_peak_r": distribution_peak_r,
        "peak_r": distribution_peak_r,
        "peak_r_status": scalar_status if distribution_peak_r is not None else "missing_prerequisite",
        "peak_r_invalid_reason": scalar_reason if distribution_peak_r is not None else inversion_invalid_reason,
        "peak_height": peak_height,
        "peak_height_status": scalar_status if peak_height is not None else "missing_prerequisite",
        "peak_height_invalid_reason": scalar_reason if peak_height is not None else inversion_invalid_reason,
        "peak_count": peak_count,
        "peak_count_status": scalar_status if peak_count is not None else "missing_prerequisite",
        "peak_count_invalid_reason": scalar_reason if peak_count is not None else inversion_invalid_reason,
        "distribution_width": distribution_width,
        "negative_unconstrained_fraction": negative_fraction,
        "negative_fraction": negative_fraction,
        "negative_fraction_status": scalar_status if negative_fraction is not None else "missing_prerequisite",
        "negative_fraction_invalid_reason": scalar_reason if negative_fraction is not None else inversion_invalid_reason,
        "tail_score": tail_score,
        "tail_score_status": scalar_status if tail_score is not None else "missing_prerequisite",
        "tail_score_invalid_reason": scalar_reason if tail_score is not None else inversion_invalid_reason,
        "smoothness": smoothness,
        "smoothness_status": scalar_status if smoothness is not None else "missing_prerequisite",
        "smoothness_invalid_reason": scalar_reason if smoothness is not None else inversion_invalid_reason,
        "fit_q": q.tolist() if inversion_performed else [],
        "fit_I": fit_i.tolist(),
        "residuals": residuals.tolist(),
        "backfit_rmse": backfit_rmse,
        "backfit_rmse_status": scalar_status if backfit_rmse is not None else "missing_prerequisite",
        "backfit_rmse_invalid_reason": scalar_reason if backfit_rmse is not None else inversion_invalid_reason,
        "backfit_chi_square": backfit_chi_square,
        "backfit_chi_square_status": backfit_chi_square_status,
        "backfit_chi_square_invalid_reason": backfit_chi_square_invalid_reason,
        "backfit_status": "available" if backfit_rmse is not None else "missing_prerequisite",
        "backfit_invalid_reason": None if backfit_rmse is not None else inversion_invalid_reason,
        "q_extrapolation_status": "finite_range_assumption",
        "q_extrapolation_invalid_reason": "The inversion uses only the selected measured q range; unmeasured low-q and high-q behaviour remains model-dependent.",
        "prerequisites": {
            "sample_type": {
                "status": "assumption_required",
                "reason": "P(r) interpretation assumes dilute, non-interacting particle scattering.",
            },
            "absolute_intensity": {
                "status": "not_required",
                "reason": "The normalized P(r) inversion does not calculate an absolute two-phase quantity.",
            },
            "contrast": {
                "status": "not_required",
                "reason": "Scattering contrast is not used by this normalized P(r) inversion.",
            },
            "q_coverage": {
                "status": "satisfied" if q.size >= 12 else "missing_prerequisite",
                "reason": None if q.size >= 12 else "At least 12 valid q points are required.",
            },
            "q_extrapolation": {
                "status": "finite_range_assumption",
                "reason": "The inversion uses only the selected measured q range.",
            },
            "porod_plateau": {
                "status": "not_applicable",
                "reason": "No Porod tail extrapolation is performed by P(r) inversion.",
            },
            "dmax": {"status": "supplied", "reason": "Dmax is a user-supplied inversion constraint."},
            "regularization": {"status": "supplied", "reason": "Regularization controls the non-unique inversion."},
            "intensity_uncertainty": {
                "status": uncertainty_status,
                "reason": uncertainty_reason,
            },
        },
        "assumption_status": "assumption_dependent",
        "analysis_status": "assumption_dependent",
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_PR,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "P(r) inversion is non-unique and depends on Dmax, background quality, q range, and regularization.",
            "Treat distribution shape as a constrained candidate, not a standalone proof of particle size distribution.",
        ],
        export_tables={EXPORT_TABLE_PR_DISTRIBUTION: pr_table, "pr_backfit": backfit_table},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="pr",
        q_range=q_range,
        parameters={"dmax": dmax, "regularization": regularization, "r_points": r_points},
        results=results,
        warnings=warnings,
    )

