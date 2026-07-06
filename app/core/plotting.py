from __future__ import annotations

from typing import Iterable

import numpy as np
from matplotlib.figure import Figure

from app.core.data_model import CurveData
from app.core.model_free import local_slope


def create_curve_figure(
    curves: CurveData | Iterable[CurveData],
    *,
    plot_type: str = "linear",
    show_error: bool = True,
) -> tuple[Figure, list[str]]:
    if isinstance(curves, CurveData):
        curve_list = [curves]
    else:
        curve_list = list(curves)

    figure = Figure(figsize=(6, 4), dpi=100)
    ax = figure.add_subplot(111)
    warnings: list[str] = []

    for curve in curve_list:
        q = curve.q
        intensity = curve.intensity
        error = curve.error
        mask = np.isfinite(q) & np.isfinite(intensity)

        if plot_type in {"semilog", "loglog"}:
            invalid_i = mask & (intensity <= 0)
            if np.any(invalid_i):
                warnings.append(f"{curve.name}: excluded {int(np.sum(invalid_i))} points with I(q) <= 0.")
            mask &= intensity > 0

        if plot_type == "loglog":
            invalid_q = mask & (q <= 0)
            if np.any(invalid_q):
                warnings.append(f"{curve.name}: excluded {int(np.sum(invalid_q))} points with q <= 0.")
            mask &= q > 0

        x = q[mask]
        y = intensity[mask]
        yerr = error[mask] if show_error and error is not None else None
        if yerr is not None and (np.any(~np.isfinite(yerr)) or np.any(yerr < 0)):
            warnings.append(f"{curve.name}: error bars were hidden because error contains invalid values.")
            yerr = None

        if plot_type == "linear":
            y_plot = y
            x_plot = x
            y_label = f"I(q) ({curve.intensity_unit})"
            x_label = f"q ({curve.q_unit})"
        elif plot_type == "semilog":
            y_plot = np.log(y)
            x_plot = x
            y_label = f"ln I(q) ({curve.intensity_unit})"
            x_label = f"q ({curve.q_unit})"
            if yerr is not None:
                yerr = yerr / y
        elif plot_type == "loglog":
            y_plot = np.log(y)
            x_plot = np.log(x)
            y_label = f"ln I(q) ({curve.intensity_unit})"
            x_label = f"ln q ({curve.q_unit})"
            if yerr is not None:
                yerr = yerr / y
        elif plot_type == "guinier":
            valid = x > 0
            x_plot = x[valid] ** 2
            y_plot = np.log(y[valid])
            y_label = f"ln I(q) ({curve.intensity_unit})"
            x_label = f"q^2 ({curve.q_unit})^2"
            yerr = None if yerr is None else yerr[valid] / y[valid]
        elif plot_type in {"kratky", "invariant"}:
            x_plot = x
            y_plot = x**2 * y
            y_label = f"q^2 I(q) ({curve.q_unit})^2 {curve.intensity_unit}"
            x_label = f"q ({curve.q_unit})"
            yerr = None if yerr is None else (x**2) * yerr
        elif plot_type == "porod":
            x_plot = x
            y_plot = x**4 * y
            y_label = f"q^4 I(q) ({curve.q_unit})^4 {curve.intensity_unit}"
            x_label = f"q ({curve.q_unit})"
            yerr = None if yerr is None else (x**4) * yerr
        elif plot_type == "local_slope":
            result = local_slope(curve, (float(np.nanmin(curve.q)), float(np.nanmax(curve.q))))
            x_plot = np.asarray(result.results["q_mid"], dtype=float)
            y_plot = np.asarray(result.results["alpha"], dtype=float)
            y_label = "alpha(q) = -d ln I / d ln q"
            x_label = f"q ({curve.q_unit})"
            yerr = None
            warnings.extend(result.warnings)
        else:
            raise ValueError(f"Unsupported plot_type: {plot_type}")

        if yerr is not None:
            ax.errorbar(x_plot, y_plot, yerr=yerr, marker="o", markersize=3, linewidth=1, label=curve.name)
        else:
            ax.plot(x_plot, y_plot, marker="o", markersize=3, linewidth=1, label=curve.name)

    ax.set_xlabel(x_label if curve_list else "q")
    ax.set_ylabel(y_label if curve_list else "I(q)")
    if curve_list:
        ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    figure.tight_layout()
    return figure, warnings
