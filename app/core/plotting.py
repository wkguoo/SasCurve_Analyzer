from __future__ import annotations

from typing import Iterable

import numpy as np
from matplotlib.figure import Figure

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import CurveData
from app.core.derived_data import build_curve_derived_table
from app.core.feature_extraction import detect_peaks


Q_AXIS_PLOT_TYPES = {"linear", "semilog", "kratky", "porod", "invariant", "local_slope"}
PLOT_DERIVED_MAPPING = {
    "linear": {"x": "q", "y": "I"},
    "semilog": {"x": "q", "y": "ln_I"},
    "loglog": {"x": "log10_q", "y": "log10_I"},
    "guinier": {"x": "q2", "y": "ln_I"},
    "kratky": {"x": "q", "y": "q2I"},
    "invariant": {"x": "q", "y": "q2I"},
    "porod": {"x": "q", "y": "q4I"},
    "local_slope": {"x": "q", "y": "alpha_local"},
}


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
    if plot_type == "loglog":
        return np.log10(q_array)
    if plot_type == "guinier":
        return q_array**2
    raise ValueError(f"Unsupported plot_type: {plot_type}")


def display_x_range_to_q_range(x_min: float, x_max: float, plot_type: str) -> tuple[float, float]:
    x0 = float(x_min)
    x1 = float(x_max)
    if not np.isfinite(x0) or not np.isfinite(x1):
        raise ValueError("Display x range must contain finite values.")

    if plot_type in Q_AXIS_PLOT_TYPES:
        q_values = [x0, x1]
    elif plot_type == "loglog":
        q_values = [float(np.power(10.0, x0)), float(np.power(10.0, x1))]
    elif plot_type == "guinier":
        if x0 < 0 or x1 < 0:
            raise ValueError("Guinier display x is q², so it cannot be negative.")
        q_values = [float(np.sqrt(x0)), float(np.sqrt(x1))]
    else:
        raise ValueError(f"Unsupported plot type for q-range conversion: {plot_type}")

    q0, q1 = sorted(q_values)
    if q0 <= 0 or q1 <= 0 or q0 >= q1:
        raise ValueError("Converted raw q range must be positive and increasing.")
    return q0, q1


def display_x_limits_to_q_range_for_curve(
    curve: CurveData,
    x_min: float,
    x_max: float,
    plot_type: str,
) -> tuple[tuple[float, float], list[str]]:
    display_limits = np.asarray([x_min, x_max], dtype=float)
    if not np.all(np.isfinite(display_limits)):
        raise ValueError("Display x limits must contain finite values.")

    q = np.asarray(curve.q, dtype=float)
    intensity = np.asarray(curve.intensity, dtype=float)
    mask = np.isfinite(q) & np.isfinite(intensity) & (q > 0)
    if plot_type in {"semilog", "loglog", "guinier"}:
        mask &= intensity > 0
    valid_q = q[mask]
    if valid_q.size == 0:
        raise ValueError("Current curve has no positive finite raw q values available for this plot type.")

    display_x = np.asarray(transform_x_for_plot(valid_q, plot_type), dtype=float)
    display_x = display_x[np.isfinite(display_x)]
    if display_x.size == 0:
        raise ValueError("Current curve has no finite display x values available for this plot type.")

    requested_min, requested_max = sorted((float(display_limits[0]), float(display_limits[1])))
    valid_min = float(np.min(display_x))
    valid_max = float(np.max(display_x))
    clipped_min = max(requested_min, valid_min)
    clipped_max = min(requested_max, valid_max)
    if clipped_min >= clipped_max:
        raise ValueError(
            "Display x limits do not overlap the current curve's valid data range "
            f"for plot_type={plot_type}: requested=[{requested_min:.6g}, {requested_max:.6g}], "
            f"valid=[{valid_min:.6g}, {valid_max:.6g}]."
        )

    warnings: list[str] = []
    if clipped_min != requested_min or clipped_max != requested_max:
        warnings.append("Display x range was clipped to the current curve's valid data range before conversion.")
    return display_x_range_to_q_range(clipped_min, clipped_max, plot_type), warnings


def format_plot_cursor_coordinates(x: float | None, y: float | None, plot_type: str) -> str:
    if x is None or y is None or not np.isfinite(x) or not np.isfinite(y):
        return "Coordinates: -"
    if plot_type == "loglog":
        return f"Coordinates: lg q = {x:.5g}, lg I = {y:.5g}; q \u2248 {np.power(10.0, x):.5g}, I \u2248 {np.power(10.0, y):.5g}"
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
        derived = build_curve_derived_table(curve, preserve_input_order=False)
        table = derived.table
        mapping = PLOT_DERIVED_MAPPING.get(plot_type)
        if mapping is None:
            raise ValueError(f"Unsupported plot_type: {plot_type}")
        q_unit = display_unit(curve.q_unit)
        intensity_unit = display_unit(curve.intensity_unit)
        x_column = mapping["x"]
        y_column = mapping["y"]
        x_values = table[x_column].to_numpy(dtype=float)
        y_values = table[y_column].to_numpy(dtype=float)
        mask = np.isfinite(x_values) & np.isfinite(y_values)
        if plot_type in {"loglog", "guinier"}:
            mask &= table["q"].to_numpy(dtype=float) > 0
        if not np.any(mask):
            warnings.append(f"{curve.name}: no valid points remain for {plot_type} plot.")
        if plot_type in {"semilog", "loglog", "guinier"}:
            invalid_i_count = int(np.sum(table["I"].notna().to_numpy() & (table["I"].to_numpy(dtype=float) <= 0)))
            if invalid_i_count:
                suffix = " for Guinier plot." if plot_type == "guinier" else "."
                warnings.append(f"{curve.name}: excluded {invalid_i_count} points with I(q) <= 0{suffix}")
        if plot_type in {"loglog", "guinier"}:
            invalid_q_count = int(np.sum(table["q"].notna().to_numpy() & (table["q"].to_numpy(dtype=float) <= 0)))
            if invalid_q_count:
                suffix = " for Guinier plot." if plot_type == "guinier" else "."
                warnings.append(f"{curve.name}: excluded {invalid_q_count} points with q <= 0{suffix}")

        x_plot = table.loc[mask, x_column].to_numpy(dtype=float)
        y_plot = table.loc[mask, y_column].to_numpy(dtype=float)
        yerr = None
        if show_error and curve.error is not None and "error" in table:
            error_values = table.loc[mask, "error"].to_numpy(dtype=float)
            if np.any(~np.isfinite(error_values)) or np.any(error_values < 0):
                warnings.append(f"{curve.name}: error bars were hidden because error contains invalid values.")
            elif plot_type in {"semilog", "guinier"}:
                intensity_values = table.loc[mask, "I"].to_numpy(dtype=float)
                yerr = error_values / intensity_values
            elif plot_type == "loglog":
                intensity_values = table.loc[mask, "I"].to_numpy(dtype=float)
                yerr = error_values / (intensity_values * np.log(10.0))
            elif plot_type in {"kratky", "invariant"}:
                q_values = table.loc[mask, "q"].to_numpy(dtype=float)
                yerr = (q_values**2) * error_values
            elif plot_type == "porod":
                q_values = table.loc[mask, "q"].to_numpy(dtype=float)
                yerr = (q_values**4) * error_values
            elif plot_type != "local_slope":
                yerr = error_values

        if plot_type == "linear":
            x_label = f"q ({q_unit})"
            y_label = f"I(q) ({intensity_unit})"
        elif plot_type == "semilog":
            x_label = f"q ({q_unit})"
            y_label = f"ln I(q) ({intensity_unit})"
        elif plot_type == "loglog":
            x_label = f"lg q ({q_unit})"
            y_label = f"lg I(q) ({intensity_unit})"
        elif plot_type == "guinier":
            x_label = f"q\u00b2 ({q_unit})\u00b2"
            y_label = f"ln I(q) ({intensity_unit})"
        elif plot_type in {"kratky", "invariant"}:
            x_label = f"q ({q_unit})"
            y_label = f"q\u00b2I(q) ({q_unit})\u00b2 {intensity_unit}"
        elif plot_type == "porod":
            x_label = f"q ({q_unit})"
            y_label = f"q\u2074I(q) ({q_unit})\u2074 {intensity_unit}"
        elif plot_type == "local_slope":
            x_label = f"q ({q_unit})"
            y_label = "\u03b1(q) = -d ln I / d ln q"
            yerr = None

        if plot_type == "linear" and annotate_peaks:
            peak_result = detect_peaks(curve, (float(np.nanmin(curve.q)), float(np.nanmax(curve.q))))
            if peak_result.results["peaks"]:
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
        elif plot_type not in PLOT_DERIVED_MAPPING:
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
