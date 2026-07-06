from __future__ import annotations

import math

import numpy as np

from app.core.data_model import AnalysisResult, CurveData
from app.core.fitting import linear_fit
from app.core.uncertainty import log_intensity_sigma


def _range_mask(curve: CurveData, q_range: tuple[float, float]) -> np.ndarray:
    q_min, q_max = q_range
    if q_min > q_max:
        raise ValueError("q_min must be less than or equal to q_max.")
    return np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q >= q_min) & (curve.q <= q_max)


def _valid_log_mask(curve: CurveData, q_range: tuple[float, float], *, require_q_positive: bool = True) -> tuple[np.ndarray, list[str]]:
    mask = _range_mask(curve, q_range)
    warnings: list[str] = []
    invalid_i = mask & (curve.intensity <= 0)
    if np.any(invalid_i):
        warnings.append(f"Excluded {int(np.sum(invalid_i))} points with I(q) <= 0.")
    mask &= curve.intensity > 0
    if require_q_positive:
        invalid_q = mask & (curve.q <= 0)
        if np.any(invalid_q):
            warnings.append(f"Excluded {int(np.sum(invalid_q))} points with q <= 0.")
        mask &= curve.q > 0
    return mask, warnings


def guinier_analysis(curve: CurveData, q_range: tuple[float, float], *, min_points: int = 5) -> AnalysisResult:
    mask, warnings = _valid_log_mask(curve, q_range, require_q_positive=True)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    n = int(q.size)
    if n < min_points:
        warnings.append(f"Too few points for Guinier analysis: {n} < {min_points}.")

    results = {
        "Rg": None,
        "I0": None,
        "lnI0": None,
        "slope": None,
        "intercept": None,
        "R2": None,
        "adjusted_R2": None,
        "reduced_chi_square": None,
        "fit_points": n,
        "q_min": q_range[0],
        "q_max": q_range[1],
        "qRg_min": None,
        "qRg_max": None,
        "residuals": [],
        "standardized_residuals": [],
    }

    if n < 2:
        return AnalysisResult.create(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings)

    x = q**2
    y = np.log(intensity)
    sigma = None
    if curve.error is not None:
        sigma_all = log_intensity_sigma(curve.intensity, curve.error)
        sigma = sigma_all[mask]
        valid_sigma = np.isfinite(sigma) & (sigma > 0)
        if not np.all(valid_sigma):
            warnings.append("Invalid propagated log-intensity errors were excluded from weighted fit.")
            x = x[valid_sigma]
            y = y[valid_sigma]
            q = q[valid_sigma]
            sigma = sigma[valid_sigma]
            n = int(q.size)
    else:
        warnings.append("No error column found; ordinary least squares was used.")

    if n < 2:
        warnings.append("Not enough valid points after filtering for Guinier fit.")
        results["fit_points"] = n
        return AnalysisResult.create(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings)

    fit = linear_fit(x, y, sigma=sigma)
    slope = fit["slope"]
    intercept = fit["intercept"]
    results.update(
        {
            "slope": slope,
            "intercept": intercept,
            "lnI0": intercept,
            "I0": float(math.exp(intercept)),
            "R2": fit["r_squared"],
            "adjusted_R2": fit["adjusted_r_squared"],
            "reduced_chi_square": fit["reduced_chi_square"],
            "fit_points": n,
            "residuals": fit["residuals"].tolist(),
            "standardized_residuals": [] if fit["standardized_residuals"] is None else fit["standardized_residuals"].tolist(),
        }
    )

    if slope >= 0:
        warnings.append("Guinier slope is non-negative; Rg is not physically valid for this interval.")
    else:
        rg = float(math.sqrt(-3.0 * slope))
        results["Rg"] = rg
        results["qRg_min"] = float(np.min(q) * rg)
        results["qRg_max"] = float(np.max(q) * rg)
        if results["qRg_max"] > 1.3:
            warnings.append("Guinier interval may be too high because qRg_max > 1.3.")

    return AnalysisResult.create(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings)


def power_law_analysis(curve: CurveData, q_range: tuple[float, float], *, min_points: int = 5) -> AnalysisResult:
    mask, warnings = _valid_log_mask(curve, q_range, require_q_positive=True)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    n = int(q.size)
    if n < min_points:
        warnings.append(f"Too few points for power-law analysis: {n} < {min_points}.")

    results = {"alpha": None, "slope": None, "intercept": None, "prefactor": None, "R2": None, "fit_points": n, "q_range": q_range, "residuals": []}
    if n < 2:
        return AnalysisResult.create(curve=curve, analysis_type="power_law", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings)

    fit = linear_fit(np.log(q), np.log(intensity))
    slope = fit["slope"]
    alpha = float(-slope)
    results.update(
        {
            "alpha": alpha,
            "slope": slope,
            "intercept": fit["intercept"],
            "prefactor": float(math.exp(fit["intercept"])),
            "R2": fit["r_squared"],
            "fit_points": n,
            "residuals": fit["residuals"].tolist(),
        }
    )

    if abs(alpha - 4.0) <= 0.3:
        warnings.append("alpha is close to 4; this may be Porod-like behavior, but it is not a unique structural conclusion.")
    elif 1.0 < alpha < 3.0:
        warnings.append("alpha is between 1 and 3; it may relate to mass-fractal or multiscale structure, but material context and q range are required.")
    elif 3.0 < alpha < 4.0:
        warnings.append("alpha is between 3 and 4; it may relate to surface-fractal or rough-interface behavior, but this is not unique.")

    return AnalysisResult.create(curve=curve, analysis_type="power_law", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings)


def local_slope(curve: CurveData, q_range: tuple[float, float], *, window_length: int = 5, std_threshold: float = 0.15) -> AnalysisResult:
    mask, warnings = _valid_log_mask(curve, q_range, require_q_positive=True)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if window_length % 2 == 0:
        raise ValueError("window_length must be odd.")
    if q.size <= window_length:
        warnings.append("window_length must be smaller than the number of valid points.")

    alpha = -np.gradient(np.log(intensity), np.log(q)) if q.size >= 2 else np.array([])
    plateau_ranges: list[tuple[float, float]] = []
    if alpha.size >= window_length and window_length > 1:
        half = window_length // 2
        for start in range(0, alpha.size - window_length + 1):
            segment = alpha[start : start + window_length]
            if float(np.std(segment)) <= std_threshold:
                plateau_ranges.append((float(q[start + half]), float(q[start + window_length - half - 1])))

    results = {
        "q_mid": q.tolist(),
        "alpha": alpha.tolist(),
        "plateau_candidate_ranges": plateau_ranges,
        "alpha_mean": float(np.mean(alpha)) if alpha.size else None,
        "alpha_std": float(np.std(alpha)) if alpha.size else None,
    }
    return AnalysisResult.create(
        curve=curve,
        analysis_type="local_slope",
        q_range=q_range,
        parameters={"window_length": window_length, "std_threshold": std_threshold},
        results=results,
        warnings=warnings,
    )


def invariant_measured(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    warnings = ["This is a finite measured q-range integral, not a strict 0-to-infinity invariant."]
    integrand = q**2 * intensity
    q_measured = float(np.trapezoid(integrand, q)) if q.size >= 2 else float("nan")
    results = {"Q_measured": q_measured, "q_min": q_range[0], "q_max": q_range[1], "integration_points": int(q.size)}
    return AnalysisResult.create(curve=curve, analysis_type="invariant_measured", q_range=q_range, parameters={"extrapolation": "disabled"}, results=results, warnings=warnings)


def kratky_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    q = curve.q[mask]
    y = q**2 * curve.intensity[mask]
    results = {"q_K": None, "q2I_max": None, "d_K": None}
    if q.size:
        idx = int(np.nanargmax(y))
        q_k = float(q[idx])
        results = {"q_K": q_k, "q2I_max": float(y[idx]), "d_K": float(2.0 * math.pi / q_k) if q_k > 0 else None}
    return AnalysisResult.create(curve=curve, analysis_type="kratky_metrics", q_range=q_range, results=results, warnings=[])


def porod_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    q = curve.q[mask]
    y = q**4 * curve.intensity[mask]
    mean = float(np.mean(y)) if y.size else None
    std = float(np.std(y)) if y.size else None
    cv = float(std / mean) if mean not in (None, 0.0) else None
    warnings = ["q^4I(q) plateau should not be interpreted as absolute specific surface area without additional contrast and phase information."]
    results = {"q4I_plateau_mean": mean, "q4I_plateau_std": std, "q4I_plateau_cv": cv, "points": int(q.size)}
    return AnalysisResult.create(curve=curve, analysis_type="porod_metrics", q_range=q_range, results=results, warnings=warnings)

