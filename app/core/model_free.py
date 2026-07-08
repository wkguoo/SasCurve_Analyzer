from __future__ import annotations

import math

import numpy as np

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import AnalysisResult, CurveData
from app.core.fitting import linear_fit
from app.core.method_warnings import guinier_warnings, invariant_warnings, porod_plateau_warnings, power_law_warnings, warning_to_dict, warning_to_text
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


def _create_result_with_method_warnings(
    *,
    curve: CurveData,
    analysis_type: str,
    q_range: tuple[float, float],
    parameters: dict | None = None,
    results: dict | None = None,
    warnings: list[str] | None = None,
    method_warnings=None,
) -> AnalysisResult:
    structured = [warning_to_dict(warning) for warning in method_warnings or []]
    text_warnings = list(warnings or [])
    text_warnings.extend(warning_to_text(warning) for warning in method_warnings or [])
    return AnalysisResult.create(
        curve=curve,
        analysis_type=analysis_type,
        q_range=q_range,
        parameters=parameters,
        results=results,
        warnings=text_warnings,
        structured_warnings=structured,
    )


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
        method_warnings = guinier_warnings(fit_points=n)
        return _create_result_with_method_warnings(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings, method_warnings=method_warnings)

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
        method_warnings = guinier_warnings(fit_points=n)
        return _create_result_with_method_warnings(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings, method_warnings=method_warnings)

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

    method_warnings = guinier_warnings(
        qrg_max=results["qRg_max"],
        fit_points=n,
        slope=slope,
        r_squared=results["R2"],
        q_range_width=q_range[1] - q_range[0],
    )
    return _create_result_with_method_warnings(curve=curve, analysis_type="guinier", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings, method_warnings=method_warnings)


def power_law_analysis(curve: CurveData, q_range: tuple[float, float], *, min_points: int = 5) -> AnalysisResult:
    mask, warnings = _valid_log_mask(curve, q_range, require_q_positive=True)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    n = int(q.size)
    if n < min_points:
        warnings.append(f"Too few points for power-law analysis: {n} < {min_points}.")

    results = {"alpha": None, "slope": None, "intercept": None, "prefactor": None, "R2": None, "fit_points": n, "q_range": q_range, "residuals": []}
    if n < 2:
        method_warnings = power_law_warnings(fit_points=n)
        return _create_result_with_method_warnings(curve=curve, analysis_type="power_law", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings, method_warnings=method_warnings)

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

    method_warnings = power_law_warnings(alpha=alpha, fit_points=n)
    return _create_result_with_method_warnings(curve=curve, analysis_type="power_law", q_range=q_range, parameters={"min_points": min_points}, results=results, warnings=warnings, method_warnings=method_warnings)


def local_slope(curve: CurveData, q_range: tuple[float, float], *, window_length: int = 5, std_threshold: float = 0.15) -> AnalysisResult:
    mask, warnings = _valid_log_mask(curve, q_range, require_q_positive=True)
    q, intensity = sort_arrays_by_q(curve.q[mask], curve.intensity[mask])
    if q.size:
        unique_q, unique_indices = np.unique(q, return_index=True)
        if unique_q.size != q.size:
            warnings.append(f"Excluded {int(q.size - unique_q.size)} duplicate q points before local-slope calculation.")
            q = q[unique_indices]
            intensity = intensity[unique_indices]
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
    order = np.argsort(curve.q[mask])
    q = curve.q[mask][order]
    intensity = curve.intensity[mask][order]
    warnings: list[str] = []
    integrand = q**2 * intensity
    q_measured = float(np.trapezoid(integrand, q)) if q.size >= 2 else float("nan")
    negative_intensity_points = int(np.sum(intensity < 0))
    negative_contribution_area = 0.0
    positive_contribution_area = 0.0
    if q.size >= 2:
        interval_contributions = 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)
        negative_contribution_area = float(np.sum(interval_contributions[interval_contributions < 0.0]))
        positive_contribution_area = float(np.sum(interval_contributions[interval_contributions > 0.0]))
    negative_fraction = (
        abs(negative_contribution_area) / positive_contribution_area
        if positive_contribution_area > 0.0 and negative_contribution_area < 0.0
        else 0.0
    )
    if negative_intensity_points:
        warnings.append(
            f"Negative intensity affected the measured invariant: {negative_intensity_points} points had I(q) < 0; "
            "do not interpret this finite-range value as a volume fraction without reviewing background subtraction."
        )
    results = {
        "Q_measured": q_measured,
        "q_min": q_range[0],
        "q_max": q_range[1],
        "integration_points": int(q.size),
        "negative_intensity_points": negative_intensity_points,
        "negative_contribution_area": negative_contribution_area,
        "negative_contribution_fraction": negative_fraction,
    }
    return _create_result_with_method_warnings(curve=curve, analysis_type="invariant_measured", q_range=q_range, parameters={"extrapolation": "disabled"}, results=results, warnings=warnings, method_warnings=invariant_warnings())


def _positive_interval_contributions(q: np.ndarray, integrand: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if q.size < 2:
        return np.array([], dtype=float), np.array([], dtype=float)
    interval_q = 0.5 * (q[:-1] + q[1:])
    interval_q_value = 0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)
    return interval_q, np.maximum(interval_q_value, 0.0)


def _contribution_quantile(q: np.ndarray, contributions: np.ndarray, cumulative: np.ndarray, fraction: float) -> float | None:
    total = float(cumulative[-1]) if cumulative.size else 0.0
    if total <= 0.0:
        return None
    target = fraction * total
    index = int(np.searchsorted(cumulative, target, side="left"))
    if index <= 0:
        return float(q[0])
    if index >= cumulative.size:
        return float(q[-1])
    previous = float(cumulative[index - 1])
    segment = float(contributions[index - 1])
    if segment <= 0.0:
        return float(q[index])
    position = (target - previous) / segment
    return float(q[index - 1] + position * (q[index] - q[index - 1]))


def information_budget(curve: CurveData, q_range: tuple[float, float], *, q_bands: tuple[float, float] | None = None) -> AnalysisResult:
    mask = _range_mask(curve, q_range)
    invalid_q = mask & (curve.q <= 0)
    warnings: list[str] = []
    if np.any(invalid_q):
        warnings.append(f"Excluded {int(np.sum(invalid_q))} points with q <= 0.")
    mask &= curve.q > 0
    order = np.argsort(curve.q[mask])
    q = curve.q[mask][order]
    intensity = curve.intensity[mask][order]

    integrand = q**2 * intensity
    q3i = q**3 * intensity
    q_measured = float(np.trapezoid(integrand, q)) if q.size >= 2 else float("nan")
    cumulative_q = np.concatenate(([0.0], np.cumsum(0.5 * (integrand[:-1] + integrand[1:]) * np.diff(q)))) if q.size >= 2 else np.array([], dtype=float)
    interval_q, positive_contributions = _positive_interval_contributions(q, integrand)
    positive_cumulative = np.concatenate(([0.0], np.cumsum(positive_contributions))) if q.size >= 2 else np.array([], dtype=float)
    positive_total = float(positive_cumulative[-1]) if positive_cumulative.size else 0.0

    if q.size < 2:
        warnings.append("Information budget needs at least two valid q > 0 points.")
    if positive_total <= 0.0 and q.size >= 2:
        warnings.append("No positive invariant contribution was available for quantile and fraction metrics.")

    quantiles = {
        "q_Q10": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.10),
        "q_Q50": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.50),
        "q_Q90": _contribution_quantile(q, positive_contributions, positive_cumulative, 0.90),
    }
    d_q50 = float(2.0 * math.pi / quantiles["q_Q50"]) if quantiles["q_Q50"] not in (None, 0.0) else None

    probabilities = positive_contributions / positive_total if positive_total > 0.0 else np.array([], dtype=float)
    if probabilities.size > 1:
        nonzero = probabilities[probabilities > 0.0]
        entropy = float(-np.sum(nonzero * np.log(nonzero)) / math.log(probabilities.size))
    else:
        entropy = 0.0 if probabilities.size == 1 else None

    if q_bands is None and q.size:
        log_min = float(np.log(q[0]))
        log_max = float(np.log(q[-1]))
        low_mid = float(np.exp(log_min + (log_max - log_min) / 3.0))
        mid_high = float(np.exp(log_min + 2.0 * (log_max - log_min) / 3.0))
    elif q_bands is not None:
        low_mid, mid_high = q_bands
    else:
        low_mid, mid_high = (None, None)

    fractions = {"low": None, "mid": None, "high": None}
    if positive_total > 0.0 and low_mid is not None and mid_high is not None:
        low = float(np.sum(positive_contributions[interval_q < low_mid]))
        mid = float(np.sum(positive_contributions[(interval_q >= low_mid) & (interval_q < mid_high)]))
        high = float(np.sum(positive_contributions[interval_q >= mid_high]))
        fractions = {"low": low / positive_total, "mid": mid / positive_total, "high": high / positive_total}

    if q.size:
        peak_index = int(np.nanargmax(q3i))
        q3i_peak_q = float(q[peak_index])
        q3i_peak_d = float(2.0 * math.pi / q3i_peak_q) if q3i_peak_q > 0 else None
    else:
        q3i_peak_q = None
        q3i_peak_d = None

    results = {
        "q": q.tolist(),
        "lnq": np.log(q).tolist() if q.size else [],
        "q3I": q3i.tolist(),
        "Q_cumulative": cumulative_q.tolist(),
        "Q_measured": q_measured,
        "Q_positive_total": positive_total,
        "q3I_peak_q": q3i_peak_q,
        "q3I_peak_d": q3i_peak_d,
        **quantiles,
        "d_Q50": d_q50,
        "Q_entropy": entropy,
        "Q_low_mid_high_fraction": fractions,
        "Q_low_fraction": fractions["low"],
        "Q_mid_fraction": fractions["mid"],
        "Q_high_fraction": fractions["high"],
        "q_band_boundaries": {"low_mid": low_mid, "mid_high": mid_high},
        "d_observable_min": float(2.0 * math.pi / q[-1]) if q.size else None,
        "d_observable_max": float(2.0 * math.pi / q[0]) if q.size else None,
        "integration_points": int(q.size),
    }
    return _create_result_with_method_warnings(
        curve=curve,
        analysis_type="information_budget",
        q_range=q_range,
        parameters={"q_bands": q_bands},
        results=results,
        warnings=warnings,
        method_warnings=invariant_warnings(),
    )


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
    cv = float(std / abs(mean)) if mean not in (None, 0.0) else None
    warnings: list[str] = []
    results = {"q4I_plateau_mean": mean, "q4I_plateau_std": std, "q4I_plateau_cv": cv, "points": int(q.size)}
    return _create_result_with_method_warnings(curve=curve, analysis_type="porod_metrics", q_range=q_range, results=results, warnings=warnings, method_warnings=porod_plateau_warnings(y))

