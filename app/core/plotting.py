from __future__ import annotations

from typing import Iterable

import numpy as np
from matplotlib.figure import Figure

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import CurveData
from app.core.feature_extraction import detect_peaks
from app.core.model_free import local_slope


Q_AXIS_PLOT_TYPES = {"linear", "semilog", "kratky", "porod", "invariant", "local_slope", "peak_spacing"}


def display_unit(unit: str) -> str:
    return (
        unit.replace("^-1", "\u207b\u00b9")
        .replace("^-2", "\u207b\u00b2")
        .replace("^-3", "\u207b\u00b3")
        .replace("^-4", "\u207b\u2074")
        .replace("^2", "\u00b2")
        .replace("^3", "\u00b3")
        .replace("^4", "\u2074")
    )


def transform_x_for_plot(q, plot_type: str):
    q_array = np.asarray(q, dtype=float)
    if plot_type in Q_AXIS_PLOT_TYPES:
        return q_array
    if plot_type in {"loglog", "invariant_contribution"}:
        return np.log(q_array)
    if plot_type == "guinier":
        return q_array**2
    raise ValueError(f"Unsupported plot_type: {plot_type}")


def format_plot_cursor_coordinates(x: float | None, y: float | None, plot_type: str) -> str:
    if x is None or y is None or not np.isfinite(x) or not np.isfinite(y):
        return "Coordinates: -"
    if plot_type == "loglog":
        return f"Coordinates: ln q = {x:.5g}, ln I = {y:.5g}; q \u2248 {np.exp(x):.5g}, I \u2248 {np.exp(y):.5g}"
    if plot_type == "guinier":
        q = np.sqrt(x) if x >= 0 else float("nan")
        return f"Coordinates: q\u00b2 = {x:.5g}, ln I = {y:.5g}; q \u2248 {q:.5g}, I \u2248 {np.exp(y):.5g}"
    if plot_type == "semilog":
        return f"Coordinates: q = {x:.5g}, ln I = {y:.5g}; I \u2248 {np.exp(y):.5g}"
    if plot_type == "local_slope":
        return f"Coordinates: q = {x:.5g}, \u03b1(q) = {y:.5g}"
    return f"Coordinates: x = {x:.5g}, y = {y:.5g}"


def create_curve_figure(
    curves: CurveData | Iterable[CurveData],
    *,
    plot_type: str = "linear",
    show_error: bool = True,
    show_d_axis: bool = False,
    annotate_peaks: bool = False,
) -> tuple[Figure, list[str]]:
    if isinstance(curves, CurveData):
        curve_list = [curves]
    else:
        curve_list = list(curves)

    figure = Figure(figsize=(6, 4), dpi=100)
    ax = figure.add_subplot(111)
    warnings: list[str] = []
    x_label = "q"
    y_label = "I(q)"

    for curve in curve_list:
        if curve.error is None:
            q, intensity = sort_arrays_by_q(curve.q, curve.intensity)
            error = None
        else:
            q, intensity, error = sort_arrays_by_q(curve.q, curve.intensity, curve.error)
        mask = np.isfinite(q) & np.isfinite(intensity)

        if plot_type in {"semilog", "loglog", "guinier"}:
            invalid_i = mask & (intensity <= 0)
            if np.any(invalid_i):
                suffix = " for Guinier plot." if plot_type == "guinier" else "."
                warnings.append(f"{curve.name}: excluded {int(np.sum(invalid_i))} points with I(q) <= 0{suffix}")
            mask &= intensity > 0

        if plot_type in {"loglog", "guinier", "invariant_contribution"}:
            invalid_q = mask & (q <= 0)
            if np.any(invalid_q):
                suffix = " for Guinier plot." if plot_type == "guinier" else "."
                warnings.append(f"{curve.name}: excluded {int(np.sum(invalid_q))} points with q <= 0{suffix}")
            mask &= q > 0
        if not np.any(mask):
            warnings.append(f"{curve.name}: no valid points remain for {plot_type} plot.")

        x = q[mask]
        y = intensity[mask]
        yerr = error[mask] if show_error and error is not None else None
        if yerr is not None and (np.any(~np.isfinite(yerr)) or np.any(yerr < 0)):
            warnings.append(f"{curve.name}: error bars were hidden because error contains invalid values.")
            yerr = None

        q_unit = display_unit(curve.q_unit)
        intensity_unit = display_unit(curve.intensity_unit)
        if plot_type == "linear":
            x_plot = x
            y_plot = y
            x_label = f"q ({q_unit})"
            y_label = f"I(q) ({intensity_unit})"
        elif plot_type == "semilog":
            x_plot = x
            y_plot = np.log(y)
            x_label = f"q ({q_unit})"
            y_label = f"ln I(q) ({intensity_unit})"
            if yerr is not None:
                yerr = yerr / y
        elif plot_type == "loglog":
            x_plot = np.log(x)
            y_plot = np.log(y)
            x_label = f"ln q ({q_unit})"
            y_label = f"ln I(q) ({intensity_unit})"
            if yerr is not None:
                yerr = yerr / y
        elif plot_type == "guinier":
            x_plot = x**2
            y_plot = np.log(y)
            x_label = f"q\u00b2 ({q_unit})\u00b2"
            y_label = f"ln I(q) ({intensity_unit})"
            if yerr is not None:
                yerr = yerr / y
        elif plot_type in {"kratky", "invariant"}:
            x_plot = x
            y_plot = x**2 * y
            x_label = f"q ({q_unit})"
            y_label = f"q\u00b2I(q) ({q_unit})\u00b2 {intensity_unit}"
            if yerr is not None:
                yerr = (x**2) * yerr
        elif plot_type == "invariant_contribution":
            x_plot = np.log(x)
            y_plot = x**3 * y
            x_label = f"ln q ({q_unit})"
            y_label = f"q\u00b3I(q) ({q_unit})\u00b3 {intensity_unit}"
            if yerr is not None:
                yerr = (x**3) * yerr
        elif plot_type == "porod":
            x_plot = x
            y_plot = x**4 * y
            x_label = f"q ({q_unit})"
            y_label = f"q\u2074I(q) ({q_unit})\u2074 {intensity_unit}"
            if yerr is not None:
                yerr = (x**4) * yerr
        elif plot_type == "peak_spacing":
            x_plot = x
            y_plot = y
            x_label = f"q ({q_unit})"
            y_label = f"I(q) ({intensity_unit})"
            peak_result = detect_peaks(curve, (float(np.nanmin(curve.q)), float(np.nanmax(curve.q))))
            if annotate_peaks and peak_result.results["peaks"]:
                first_peak = peak_result.results["peaks"][0]
                ax.axvline(first_peak["peak_q"], color="tab:red", linestyle="--", linewidth=1)
                ax.annotate(
                    f"q*={first_peak['peak_q']:.3g}\nd=2\u03c0/q*={first_peak['d']:.3g}",
                    xy=(first_peak["peak_q"], first_peak["peak_I"]),
                    xytext=(8, 8),
                    textcoords="offset points",
                    fontsize=8,
                    color="tab:red",
                )
            warnings.extend(peak_result.warnings)
        elif plot_type == "local_slope":
            result = local_slope(curve, (float(np.nanmin(curve.q)), float(np.nanmax(curve.q))))
            x_plot = np.asarray(result.results["q_mid"], dtype=float)
            y_plot = np.asarray(result.results["alpha"], dtype=float)
            x_label = f"q ({q_unit})"
            y_label = "\u03b1(q) = -d ln I / d ln q"
            yerr = None
            warnings.extend(result.warnings)
        else:
            raise ValueError(f"Unsupported plot_type: {plot_type}")

        if yerr is not None:
            ax.errorbar(x_plot, y_plot, yerr=yerr, marker="o", markersize=3, linewidth=1, label=curve.name)
        else:
            ax.plot(x_plot, y_plot, marker="o", markersize=3, linewidth=1, label=curve.name)

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    if show_d_axis:
        if plot_type in Q_AXIS_PLOT_TYPES:

            def q_to_d(value):
                value = np.asarray(value, dtype=float)
                return np.divide(2 * np.pi, value, out=np.full_like(value, np.nan), where=value > 0)

            def d_to_q(value):
                value = np.asarray(value, dtype=float)
                return np.divide(2 * np.pi, value, out=np.full_like(value, np.nan), where=value > 0)

            secax = ax.secondary_xaxis("top", functions=(q_to_d, d_to_q))
            secax.set_xlabel("Approx. real-space scale d = 2\u03c0/q")
            warnings.append(
                "d = 2\u03c0/q is a characteristic scale or correlation distance, not an automatic particle diameter."
            )
        else:
            warnings.append(f"d = 2\u03c0/q secondary axis is not enabled for {plot_type} because the x-axis is not raw q.")
    if curve_list:
        ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    figure.tight_layout()
    return figure, warnings
