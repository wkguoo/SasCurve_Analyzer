from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.core.data_model import AnalysisResult, CurveData
from app.core.derived_data import DerivedDataOptions, build_curve_derived_table


PLOT_ANALYSIS_TYPES = [
    "linear",
    "semilog",
    "loglog",
    "guinier",
    "kratky",
    "porod",
    "invariant",
    "local_slope",
]

PLOT_ANALYSIS_FORMULAS = {
    "linear": "I(q) vs q",
    "semilog": "ln I(q) vs q",
    "loglog": "lg I(q) = m lg q + b; α = -m; A = 10^b",
    "guinier": "ln I(q) = ln I(0) - Rg²q² / 3",
    "kratky": "q²I(q) vs q; area = ∫ q²I(q) dq",
    "porod": "q⁴I(q) vs q plus lg I vs lg q over the same q range",
    "invariant": "Q_measured = ∫ q²I(q) dq over the measured finite q range",
    "local_slope": "α(q) = -d ln I(q) / d ln q",
}

PRIMARY_METRIC_BY_PLOT = {
    "linear": "finite_point_count",
    "semilog": "valid_lnI_point_count",
    "loglog": "alpha",
    "guinier": "Rg",
    "kratky": "Kratky_curve_area_in_selected_q_range",
    "porod": "Porod_constant_relative",
    "invariant": "Q_measured",
    "local_slope": "average_alpha_in_selected_range",
}

# NumPy 2.x removed ``np.trapz`` and this project requires NumPy >= 2.0.
# Use the supported spelling directly; a fallback expression such as
# ``getattr(np, "trapezoid", np.trapz)`` still evaluates ``np.trapz`` first.
_trapezoid = np.trapezoid


@dataclass(frozen=True)
class _FitResult:
    slope: float
    intercept: float
    r2: float
    residuals: np.ndarray
    standardized_residuals: np.ndarray
    fitted: np.ndarray


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _filter_derived_warnings_for_plot(plot_type: str, warnings: list[str]) -> list[str]:
    """Keep only derived-table warnings that are relevant to this plot analysis.

    The shared derived table intentionally computes many helper columns. Plot
    analyses should not surface helper-column failures unless the current plot
    type actually uses that domain or diagnostic.
    """
    log_q_plots = {"loglog", "guinier", "local_slope"}
    log_i_plots = {"semilog", "loglog", "guinier", "porod", "local_slope"}
    filtered: list[str] = []
    for warning in warnings:
        warning_lower = warning.lower()
        if "local_slope_dlni_dlnq" in warning_lower and plot_type != "local_slope":
            continue
        if "q <= 0" in warning and plot_type not in log_q_plots:
            continue
        if "I <= 0" in warning and plot_type not in log_i_plots:
            continue
        filtered.append(warning)
    return filtered


def _selected_table(curve: CurveData, q_range: tuple[float, float], plot_type: str) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    derived = build_curve_derived_table(
        curve,
        options=DerivedDataOptions(include_optional_parameter_warnings=False),
        preserve_input_order=False,
    )
    table = derived.table
    q_min, q_max = sorted((float(q_range[0]), float(q_range[1])))
    selected = table[(table["q"] >= q_min) & (table["q"] <= q_max)].copy()
    warnings = _filter_derived_warnings_for_plot(plot_type, list(derived.warnings))
    if selected.empty:
        warnings.append(f"No points are inside selected raw q range [{q_min:.6g}, {q_max:.6g}].")
    return table, selected, warnings


def _valid_xy(table: pd.DataFrame, x_column: str, y_column: str) -> pd.DataFrame:
    x = table[x_column].to_numpy(dtype=float)
    y = table[y_column].to_numpy(dtype=float)
    return table.loc[np.isfinite(x) & np.isfinite(y)].copy()


def _linear_fit(x: np.ndarray, y: np.ndarray) -> _FitResult:
    if x.size < 2:
        raise ValueError("At least two valid points are required for a linear fit.")
    slope, intercept = np.polyfit(x, y, deg=1)
    fitted = slope * x + intercept
    residuals = y - fitted
    ss_res = float(np.sum(np.square(residuals)))
    ss_tot = float(np.sum(np.square(y - np.mean(y))))
    r2 = float("nan") if ss_tot == 0 else 1.0 - ss_res / ss_tot
    residual_std = float(np.std(residuals, ddof=1)) if residuals.size > 1 else float("nan")
    if np.isfinite(residual_std) and residual_std > 0:
        standardized = residuals / residual_std
    else:
        standardized = np.full(residuals.shape, np.nan, dtype=float)
    return _FitResult(float(slope), float(intercept), r2, residuals, standardized, fitted)


def _fit_export_rows(
    table: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    fit: _FitResult,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (_row_index, row) in enumerate(table.iterrows()):
        rows.append(
            {
                "row_index": int(row.get("row_index", index)),
                "q": _safe_float(row.get("q")),
                x_column: _safe_float(row.get(x_column)),
                y_column: _safe_float(row.get(y_column)),
                "fitted_y": _safe_float(fit.fitted[index]),
                "residual": _safe_float(fit.residuals[index]),
                "standardized_residual": _safe_float(fit.standardized_residuals[index]),
            }
        )
    return rows


def _filtered_count(selected: pd.DataFrame, valid: pd.DataFrame) -> int:
    return int(max(len(selected) - len(valid), 0))


def _linear_diagnostics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "linear")
    q = selected["q"].to_numpy(dtype=float)
    intensity = selected["I"].to_numpy(dtype=float)
    finite_mask = np.isfinite(q) & np.isfinite(intensity)
    finite_i = intensity[np.isfinite(intensity)]
    tail = finite_i[-max(1, int(np.ceil(finite_i.size * 0.1))) :] if finite_i.size else np.array([])
    results = {
        "plot_type": "linear",
        "analysis_kind": "diagnostic",
        "formula": PLOT_ANALYSIS_FORMULAS["linear"],
        "q_start": _safe_float(np.nanmin(q)) if q.size else None,
        "q_end": _safe_float(np.nanmax(q)) if q.size else None,
        "I_min": _safe_float(np.nanmin(finite_i)) if finite_i.size else None,
        "I_max": _safe_float(np.nanmax(finite_i)) if finite_i.size else None,
        "finite_point_count": int(np.sum(finite_mask)),
        "negative_I_count": int(np.sum(np.isfinite(intensity) & (intensity < 0))),
        "zero_I_count": int(np.sum(np.isfinite(intensity) & (intensity == 0))),
        "nan_or_inf_count": int(len(selected) - np.sum(finite_mask)),
        "rough_noise_floor_estimate": _safe_float(np.median(np.abs(tail))) if tail.size else None,
        "fit_point_count": int(np.sum(finite_mask)),
        "filtered_point_count": int(len(selected) - np.sum(finite_mask)),
        "warnings": warnings,
    }
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:linear", q_range=q_range, results=results, warnings=warnings)


def _semilog_diagnostics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "semilog")
    valid = _valid_xy(selected, "q", "ln_I")
    nonpositive_i = int(np.sum(selected["I"].notna().to_numpy() & (selected["I"].to_numpy(dtype=float) <= 0)))
    nonfinite_i = int(np.sum(~np.isfinite(selected["I"].to_numpy(dtype=float)))) if len(selected) else 0
    if nonpositive_i:
        warnings.append(f"Filtered {nonpositive_i} points with I(q) <= 0; no constant was added.")
    results = {
        "plot_type": "semilog",
        "analysis_kind": "diagnostic",
        "formula": PLOT_ANALYSIS_FORMULAS["semilog"],
        "valid_lnI_point_count": int(len(valid)),
        "filtered_nonpositive_I_count": nonpositive_i,
        "filtered_nonfinite_I_count": nonfinite_i,
        "selected_q_start": _safe_float(valid["q"].min()) if len(valid) else None,
        "selected_q_end": _safe_float(valid["q"].max()) if len(valid) else None,
        "fit_point_count": int(len(valid)),
        "filtered_point_count": _filtered_count(selected, valid),
        "warnings": warnings,
    }
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:semilog", q_range=q_range, results=results, warnings=warnings)


def _loglog_fit(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "loglog")
    valid = _valid_xy(selected, "log10_q", "log10_I")
    if len(valid) < 2:
        warnings.append("Loglog fit needs at least two rows with q > 0 and I > 0.")
        fit = None
    else:
        fit = _linear_fit(valid["log10_q"].to_numpy(dtype=float), valid["log10_I"].to_numpy(dtype=float))
    if _filtered_count(selected, valid):
        warnings.append(f"Filtered {_filtered_count(selected, valid)} rows outside lg-domain; no constant was added.")
    alpha_values = valid["alpha_local"].to_numpy(dtype=float) if "alpha_local" in valid else np.array([])
    alpha_values = alpha_values[np.isfinite(alpha_values)]
    results: dict[str, Any] = {
        "plot_type": "loglog",
        "analysis_kind": "power_law_fit",
        "formula": PLOT_ANALYSIS_FORMULAS["loglog"],
        "q_start": _safe_float(valid["q"].min()) if len(valid) else None,
        "q_end": _safe_float(valid["q"].max()) if len(valid) else None,
        "fit_point_count": int(len(valid)),
        "filtered_point_count": _filtered_count(selected, valid),
        "local_slope_stability": _safe_float(np.std(alpha_values, ddof=1)) if alpha_values.size > 1 else None,
        "warnings": warnings,
    }
    if fit is not None:
        results.update(
            {
                "fit_slope_m": fit.slope,
                "alpha": -fit.slope,
                "intercept_b": fit.intercept,
                "A": float(np.power(10.0, fit.intercept)),
                "R2": fit.r2,
                "export_tables": {"residuals": _fit_export_rows(valid, x_column="log10_q", y_column="log10_I", fit=fit)},
            }
        )
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:loglog", q_range=q_range, results=results, warnings=warnings)


def _guinier_fit(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "guinier")
    valid = _valid_xy(selected, "q2", "ln_I")
    fit = _linear_fit(valid["q2"].to_numpy(dtype=float), valid["ln_I"].to_numpy(dtype=float)) if len(valid) >= 2 else None
    if _filtered_count(selected, valid):
        warnings.append(f"Filtered {_filtered_count(selected, valid)} rows outside Guinier ln-domain; no constant was added.")
    results: dict[str, Any] = {
        "plot_type": "guinier",
        "analysis_kind": "guinier_fit",
        "formula": PLOT_ANALYSIS_FORMULAS["guinier"],
        "q_start": _safe_float(valid["q"].min()) if len(valid) else None,
        "q_end": _safe_float(valid["q"].max()) if len(valid) else None,
        "fit_point_count": int(len(valid)),
        "filtered_point_count": _filtered_count(selected, valid),
        "warnings": warnings,
    }
    if fit is None:
        warnings.append("Guinier fit needs at least two rows with q > 0 and I > 0.")
    else:
        if fit.slope < 0:
            rg = float(np.sqrt(-3.0 * fit.slope))
            qrg = valid["q"].to_numpy(dtype=float) * rg
            qrg_status = "inside_common_low_q_check" if np.nanmax(qrg) <= 1.3 else "outside_common_low_q_check"
        else:
            rg = None
            qrg = np.array([])
            qrg_status = "invalid_positive_slope"
            warnings.append("Guinier slope is >= 0, so a real Rg was not calculated.")
        results.update(
            {
                "Rg": rg,
                "I0": float(np.exp(fit.intercept)),
                "ln_I0": fit.intercept,
                "slope": fit.slope,
                "intercept": fit.intercept,
                "qminRg": _safe_float(np.nanmin(qrg)) if qrg.size else None,
                "qmaxRg": _safe_float(np.nanmax(qrg)) if qrg.size else None,
                "R2": fit.r2,
                "qRg_empirical_range_status": qrg_status,
                "export_tables": {"residuals": _fit_export_rows(valid, x_column="q2", y_column="ln_I", fit=fit)},
            }
        )
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:guinier", q_range=q_range, results=results, warnings=warnings)


def _fwhm(q: np.ndarray, y: np.ndarray) -> tuple[float | None, str | None]:
    if q.size < 3 or not np.all(np.isfinite(y)):
        return None, "FWHM could not be calculated because too few finite points were available."
    peak_index = int(np.argmax(y))
    half = float(y[peak_index] / 2.0)
    left_candidates = np.flatnonzero(y[: peak_index + 1] <= half)
    right_candidates = np.flatnonzero(y[peak_index:] <= half) + peak_index
    if left_candidates.size == 0 or right_candidates.size == 0:
        return None, "FWHM could not be calculated because the half-maximum crossing was outside the selected range."
    left = float(q[left_candidates[-1]])
    right = float(q[right_candidates[0]])
    width = right - left
    return (width if width > 0 else None), None


def _kratky_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "kratky")
    valid = _valid_xy(selected, "q", "q2I")
    q = valid["q"].to_numpy(dtype=float)
    y = valid["q2I"].to_numpy(dtype=float)
    area = float(_trapezoid(y, q)) if q.size >= 2 else None
    peak_q = peak_i = width = None
    if q.size:
        peak_index = int(np.argmax(y))
        peak_q = float(q[peak_index])
        peak_i = float(y[peak_index])
        width, width_warning = _fwhm(q, y)
        if width_warning:
            warnings.append(width_warning)
    fit = _linear_fit(q, y) if q.size >= 2 else None
    trend_slope = None if fit is None else fit.slope
    trend_r2 = None if fit is None else fit.r2
    results = {
        "plot_type": "kratky",
        "analysis_kind": "kratky_metrics",
        "formula": PLOT_ANALYSIS_FORMULAS["kratky"],
        "q_start": _safe_float(q.min()) if q.size else None,
        "q_end": _safe_float(q.max()) if q.size else None,
        "Kratky_peak_q": peak_q,
        "Kratky_peak_intensity": peak_i,
        "Kratky_peak_width": width,
        "Kratky_curve_area_in_selected_q_range": area,
        "Kratky_rising_trend_flag": bool(trend_slope is not None and trend_slope > 0),
        "Kratky_rising_trend_slope": trend_slope,
        "Kratky_rising_trend_R2": trend_r2,
        "fit_point_count": int(len(valid)),
        "filtered_point_count": _filtered_count(selected, valid),
        "warnings": warnings,
    }
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:kratky", q_range=q_range, results=results, warnings=warnings)


def _porod_metrics(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "porod")
    plateau = _valid_xy(selected, "q", "q4I")
    log_valid = _valid_xy(selected, "log10_q", "log10_I")
    values = plateau["q4I"].to_numpy(dtype=float)
    mean = float(np.mean(values)) if values.size else None
    std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0 if values.size == 1 else None
    cv = float(std / abs(mean)) if mean not in (None, 0.0) and std is not None else None
    stability = float(1.0 / (1.0 + cv)) if cv is not None and np.isfinite(cv) else None
    fit = _linear_fit(log_valid["log10_q"].to_numpy(dtype=float), log_valid["log10_I"].to_numpy(dtype=float)) if len(log_valid) >= 2 else None
    results: dict[str, Any] = {
        "plot_type": "porod",
        "analysis_kind": "porod_metrics",
        "formula": PLOT_ANALYSIS_FORMULAS["porod"],
        "q_start": _safe_float(plateau["q"].min()) if len(plateau) else None,
        "q_end": _safe_float(plateau["q"].max()) if len(plateau) else None,
        "q4I_plateau_mean": mean,
        "q4I_plateau_std": std,
        "q4I_plateau_cv": cv,
        "plateau_stability_score": stability,
        "Porod_constant_relative": mean,
        "fit_point_count": int(len(log_valid)),
        "filtered_point_count": _filtered_count(selected, log_valid),
        "warnings": warnings,
    }
    if fit is not None:
        results.update(
            {
                "Porod_slope_on_loglog": fit.slope,
                "Porod_alpha_from_loglog": -fit.slope,
                "R2": fit.r2,
                "export_tables": {"residuals": _fit_export_rows(log_valid, x_column="log10_q", y_column="log10_I", fit=fit)},
            }
        )
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:porod", q_range=q_range, results=results, warnings=warnings)


def _invariant(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "invariant")
    valid = _valid_xy(selected, "q", "q2I")
    q = valid["q"].to_numpy(dtype=float)
    y = valid["q2I"].to_numpy(dtype=float)
    warnings.append("Q_measured is a finite measured q-range integral, not a complete invariant without low-q/high-q extrapolation.")
    results = {
        "plot_type": "invariant",
        "analysis_kind": "finite_invariant_integral",
        "formula": PLOT_ANALYSIS_FORMULAS["invariant"],
        "q_start": _safe_float(q.min()) if q.size else None,
        "q_end": _safe_float(q.max()) if q.size else None,
        "integration_method": "trapezoid",
        "integrand_point_count": int(q.size),
        "Q_measured": float(_trapezoid(y, q)) if q.size >= 2 else None,
        "fraction_warning": "finite_range_only_no_extrapolation",
        "fit_point_count": int(q.size),
        "filtered_point_count": _filtered_count(selected, valid),
        "warnings": warnings,
    }
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:invariant", q_range=q_range, results=results, warnings=warnings)


def _local_slope(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    _table, selected, warnings = _selected_table(curve, q_range, "local_slope")
    valid = _valid_xy(selected, "q", "alpha_local")
    alpha = valid["alpha_local"].to_numpy(dtype=float)
    warnings.append("Automatic local-slope plateau detection is not implemented in this version.")
    warnings.append("Local slope is noise-sensitive; smoothing is not applied to the original or derived q/I table.")
    results = {
        "plot_type": "local_slope",
        "analysis_kind": "local_slope_statistics",
        "formula": PLOT_ANALYSIS_FORMULAS["local_slope"],
        "q_start": _safe_float(valid["q"].min()) if len(valid) else None,
        "q_end": _safe_float(valid["q"].max()) if len(valid) else None,
        "average_alpha_in_selected_range": _safe_float(np.mean(alpha)) if alpha.size else None,
        "alpha_std_in_selected_range": _safe_float(np.std(alpha, ddof=1)) if alpha.size > 1 else None,
        "valid_point_count": int(alpha.size),
        "fit_point_count": int(alpha.size),
        "filtered_point_count": _filtered_count(selected, valid),
        "slope_plateau_regions": "not_implemented",
        "smoothing_window": None,
        "warnings": warnings,
        "export_tables": {
            "local_slope_curve": [
                {
                    "row_index": int(row.get("row_index", index)),
                    "q": _safe_float(row.get("q")),
                    "alpha_local": _safe_float(row.get("alpha_local")),
                    "raw_dlnI_dlnq": _safe_float(row.get("local_slope_dlnI_dlnq")),
                }
                for index, (_row_index, row) in enumerate(valid.iterrows())
            ]
        },
    }
    return AnalysisResult.create(curve=curve, analysis_type="plot_analysis:local_slope", q_range=q_range, results=results, warnings=warnings)


def analyze_curve_plot(curve: CurveData, plot_type: str, q_range: tuple[float, float]) -> AnalysisResult:
    if plot_type == "linear":
        return _linear_diagnostics(curve, q_range)
    if plot_type == "semilog":
        return _semilog_diagnostics(curve, q_range)
    if plot_type == "loglog":
        return _loglog_fit(curve, q_range)
    if plot_type == "guinier":
        return _guinier_fit(curve, q_range)
    if plot_type == "kratky":
        return _kratky_metrics(curve, q_range)
    if plot_type == "porod":
        return _porod_metrics(curve, q_range)
    if plot_type == "invariant":
        return _invariant(curve, q_range)
    if plot_type == "local_slope":
        return _local_slope(curve, q_range)
    raise ValueError(f"Unsupported plot_type for plot analysis: {plot_type}")
