"""Headless figure and exact plotting-source exports for publication bundles."""

from __future__ import annotations

import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from app.core.auto_batch_schema import AutoBatchRun
from app.core.data_model import CurveData
from app.core.derived_data import DerivedDataOptions, build_curve_derived_table
from app.core.plotting import PLOT_DERIVED_MAPPING


_BASE_VIEWS = (
    "linear", "semilog", "loglog", "guinier", "kratky", "invariant", "porod", "local_slope", "dimensionless_kratky",
)
_PLOT_SOURCE_COLUMNS = [
    "sample_id", "series_id", "curve_id", "curve_name", "source_file", "frame_index",
    "frame_label", "sequence_order", "analysis_id", "analysis_type", "model_name",
    "analysis_status", "reliability_status", "reporting_status", "plot_type", "point_index",
    "q", "I", "error", "q_unit", "intensity_unit", "error_unit", "x", "y", "yerr", "x_unit", "y_unit",
]

def _finite_number(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _frame_order(row: dict[str, Any]) -> float:
    sequence_order = _finite_number(row.get("sequence_order"))
    return float(row.get("input_order", 0)) if sequence_order is None else sequence_order

def _status(value: Any) -> str:
    return str(getattr(value, "value", value))


def _envelope_model(envelope: Any) -> str:
    if str(getattr(envelope, "analysis_type", "")) != "shape_models":
        return ""
    parts = str(getattr(envelope, "analysis_id", "")).split(":")
    return parts[-1] if len(parts) > 2 else "unspecified"

def _token(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._-")
    return text[:48] or "unnamed"

def _stable_suffix(*parts: Any) -> str:
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]

def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False, encoding="utf-8-sig", na_rep="", float_format="%.17g")

def _base_labels(plot_type: str, curve: CurveData) -> tuple[str, str]:
    q_unit, i_unit = curve.q_unit, curve.intensity_unit
    return {
        "linear": (f"q ({q_unit})", f"I(q) ({i_unit})"),
        "semilog": (f"q ({q_unit})", f"ln I(q) ({i_unit})"),
        "loglog": (f"lg q ({q_unit})", f"lg I(q) ({i_unit})"),
        "guinier": (f"q² ({q_unit})²", f"ln I(q) ({i_unit})"),
        "kratky": (f"q ({q_unit})", f"q²I(q) ({q_unit})² {i_unit}"),
        "invariant": (f"q ({q_unit})", f"q²I(q) ({q_unit})² {i_unit}"),
        "porod": (f"q ({q_unit})", f"q⁴I(q) ({q_unit})⁴ {i_unit}"),
        "local_slope": (f"q ({q_unit})", "α(q) = -d ln I / d ln q"),
        "dimensionless_kratky": ("qRg", "(qRg)² I(q) / I0"),
    }[plot_type]


def _frame_label(meta: dict[str, Any]) -> str:
    frame = meta.get("frame_label")
    if frame is None:
        frame = meta.get("frame_index")
    if frame is None:
        frame = meta.get("sequence_order", meta.get("input_order"))
    return f"{meta['curve_name']} [frame={frame}]"


def _prepare_base_series(curve: CurveData, meta: dict[str, Any], plot_type: str) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray | None, list[str], str, str]:
    derived = build_curve_derived_table(
        curve, options=DerivedDataOptions(include_optional_parameter_warnings=False), preserve_input_order=False
    )
    table = derived.table
    mapping = PLOT_DERIVED_MAPPING[plot_type]
    x_col, y_col = mapping["x"], mapping["y"]
    x_all = table[x_col].to_numpy(dtype=float)
    y_all = table[y_col].to_numpy(dtype=float)
    q_all = table["q"].to_numpy(dtype=float)
    i_all = table["I"].to_numpy(dtype=float)
    mask = np.isfinite(x_all) & np.isfinite(y_all)
    if plot_type in {"loglog", "guinier"}:
        mask &= q_all > 0
    warnings: list[str] = []
    if not np.any(mask):
        warnings.append(f"{curve.name}: no valid points remain for {plot_type} plot.")
    if plot_type in {"semilog", "loglog", "guinier"}:
        invalid_i = int(np.sum(table["I"].notna().to_numpy() & (i_all <= 0)))
        if invalid_i:
            suffix = " for Guinier plot." if plot_type == "guinier" else "."
            warnings.append(f"{curve.name}: excluded {invalid_i} points with I(q) <= 0{suffix}")
    if plot_type in {"loglog", "guinier"}:
        invalid_q = int(np.sum(table["q"].notna().to_numpy() & (q_all <= 0)))
        if invalid_q:
            suffix = " for Guinier plot." if plot_type == "guinier" else "."
            warnings.append(f"{curve.name}: excluded {invalid_q} points with q <= 0{suffix}")
    x, y = x_all[mask], y_all[mask]
    yerr: np.ndarray | None = None
    error_all = table["error"].to_numpy(dtype=float)
    if curve.error is not None and plot_type != "local_slope" and np.any(mask):
        error = error_all[mask]
        if np.any(~np.isfinite(error)) or np.any(error < 0):
            warnings.append(f"{curve.name}: error bars were hidden because error contains invalid values.")
        elif plot_type in {"semilog", "guinier"}:
            yerr = error / i_all[mask]
        elif plot_type == "loglog":
            yerr = error / (i_all[mask] * np.log(10.0))
        elif plot_type in {"kratky", "invariant"}:
            yerr = (q_all[mask] ** 2) * error
        elif plot_type == "porod":
            yerr = (q_all[mask] ** 4) * error
        else:
            yerr = error
    x_unit = derived.units.get(x_col, curve.q_unit)
    y_unit = derived.units.get(y_col, curve.intensity_unit)
    rows = []
    selected_indices = np.flatnonzero(mask)
    for local_index, source_index in enumerate(selected_indices):
        rows.append({
            **meta,
            "analysis_id": "",
            "analysis_type": "source_curve",
            "model_name": "",
            "analysis_status": "raw_curve",
            "reliability_status": "not_applicable",
            "reporting_status": "not_applicable",
            "plot_type": plot_type,
            "point_index": int(table.iloc[source_index]["row_index"]),
            "q": q_all[source_index],
            "I": i_all[source_index],
            "error": error_all[source_index],
            "x": x[local_index],
            "y": y[local_index],
            "yerr": None if yerr is None else yerr[local_index],
            "x_unit": x_unit,
            "y_unit": y_unit,
        })
    xlabel, ylabel = _base_labels(plot_type, curve)
    return rows, x, y, yerr, warnings, xlabel, ylabel


def _save_figure(figure: Figure, path: Path, fmt: str, dpi: int) -> None:
    FigureCanvasAgg(figure)
    figure.savefig(path, format=fmt, dpi=dpi, bbox_inches="tight")


def _write_figure_set(
    figure: Figure,
    figure_id: str,
    source_rows: list[dict[str, Any]],
    *,
    stage: Path,
    formats: tuple[str, ...],
    dpi: int,
    figure_kind: str,
    sample_id: str,
    view: str,
    page: int | None,
    warnings: list[str],
    analysis_id: str = "",
    table_name: str = "",
) -> list[dict[str, Any]]:
    source_path = stage / "data" / "plot_sources" / f"{figure_id}.csv"
    _write_csv(source_path, source_rows, _PLOT_SOURCE_COLUMNS)
    rows = []
    for fmt in formats:
        image_path = stage / "figures" / f"{figure_id}.{fmt}"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        _save_figure(figure, image_path, fmt, dpi)
        rows.append({
            "figure_id": figure_id,
            "figure_kind": figure_kind,
            "sample_id": sample_id,
            "view": view,
            "page": page,
            "analysis_id": analysis_id,
            "table_name": table_name,
            "status": " | ".join(dict.fromkeys(str(row.get("analysis_status") or "") for row in source_rows if row.get("analysis_status"))),
            "image": image_path.relative_to(stage).as_posix(),
            "format": fmt,
            "source_csv": source_path.relative_to(stage).as_posix(),
            "plotted_rows": len(source_rows),
            "warnings": " | ".join(warnings),
        })
    return rows


def _plot_overview_pages(
    run: AutoBatchRun,
    ordered: list[tuple[CurveData, dict[str, Any], float, str]],
    dimensionless: dict[str, dict[str, Any]],
    *,
    stage: Path,
    formats: tuple[str, ...],
    dpi: int,
    max_overlay_curves: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    figures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    dimensionless_rows: list[dict[str, Any]] = []
    for plot_type in _BASE_VIEWS:
        for page_index, offset in enumerate(range(0, len(ordered), max_overlay_curves), start=1):
            group = ordered[offset : offset + max_overlay_curves]
            fig = Figure(figsize=(8.2, 5.4), dpi=100)
            ax = fig.add_subplot(111)
            source_rows: list[dict[str, Any]] = []
            page_warnings: list[str] = []
            xlabel, ylabel = ("", "")
            for curve, meta, _, _ in group:
                if plot_type != "dimensionless_kratky":
                    rows, x, y, yerr, item_warnings, xlabel, ylabel = _prepare_base_series(curve, meta, plot_type)
                    source_rows.extend(rows)
                    page_warnings.extend(item_warnings)
                    label = _frame_label(meta)
                    if rows:
                        if yerr is None:
                            ax.plot(x, y, marker="o", markersize=2.5, linewidth=0.9, label=label)
                        else:
                            ax.errorbar(x, y, yerr=yerr, marker="o", markersize=2.5, linewidth=0.9, label=label)
                    continue

                xlabel, ylabel = _base_labels(plot_type, curve)
                prereq = dimensionless.get(str(curve.curve_id))
                if prereq is None:
                    page_warnings.append(f"{curve.name}: missing prerequisite: no reliable/reportable positive Rg and I0 with compatible units.")
                    continue
                rg = prereq["Rg"]
                i0 = prereq["I0"]
                derived = build_curve_derived_table(
                    curve, options=DerivedDataOptions(rg=rg, include_optional_parameter_warnings=False), preserve_input_order=False
                )
                table = derived.table
                q = table["q"].to_numpy(dtype=float)
                intensity = table["I"].to_numpy(dtype=float)
                error = table["error"].to_numpy(dtype=float)
                x = table["qRg"].to_numpy(dtype=float)
                y = x ** 2 * intensity / i0
                valid = np.isfinite(q) & (q > 0) & np.isfinite(intensity) & np.isfinite(x) & np.isfinite(y)
                selected_error = error[valid]
                yerr = None
                if curve.error is not None:
                    if np.all(np.isfinite(selected_error)) and np.all(selected_error >= 0):
                        yerr = x[valid] ** 2 * selected_error / i0
                        page_warnings.append(f"{curve.name}: Kratky error bars propagate intensity errors only; fitted Rg/I0 uncertainty and covariance are not included.")
                    else:
                        page_warnings.append(f"{curve.name}: error bars hidden because source errors are invalid.")
                curve_rows = []
                for point, row_index in enumerate(np.flatnonzero(valid)):
                    row = {
                        **meta,
                        "analysis_id": prereq["analysis_id"],
                        "analysis_type": "guinier",
                        "model_name": "",
                        "analysis_status": prereq["analysis_status"],
                        "reliability_status": prereq["reliability_status"],
                        "reporting_status": prereq["reporting_status"],
                        "plot_type": plot_type,
                        "point_index": int(table.iloc[row_index]["row_index"]),
                        "q": q[row_index],
                        "I": intensity[row_index],
                        "error": error[row_index],
                        "x": x[row_index],
                        "y": y[row_index],
                        "yerr": None if yerr is None else yerr[point],
                        "x_unit": "dimensionless",
                        "y_unit": "dimensionless",
                    }
                    curve_rows.append(row)
                    dimensionless_rows.append({**row, "Rg": rg, "Rg_unit": prereq["Rg_unit"], "I0": i0, "I0_unit": prereq["I0_unit"], "formula": "(q*Rg)^2 * I(q) / I0", "valid": True})
                source_rows.extend(curve_rows)
                if curve_rows:
                    coordinates = ([row["x"] for row in curve_rows], [row["y"] for row in curve_rows])
                    if yerr is None:
                        ax.plot(*coordinates, marker="o", markersize=2.5, linewidth=0.9, label=_frame_label(meta))
                    else:
                        ax.errorbar(*coordinates, yerr=yerr, marker="o", markersize=2.5, linewidth=0.9, label=_frame_label(meta))
                else:
                    page_warnings.append(f"{curve.name}: no finite positive-q points for dimensionless Kratky view.")
            if not source_rows:
                ax.text(0.5, 0.5, "No frames passed the plotting prerequisites", ha="center", va="center", transform=ax.transAxes)
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.set_title(f"{run.batch_id} — {plot_type} — page {page_index}")
            if source_rows:
                ax.legend(fontsize=7, ncol=1 if len(group) < 8 else 2)
            fig.tight_layout()
            figure_id = f"overview_{_token(run.batch_id)}_{plot_type}_p{page_index:03d}"
            figures.extend(_write_figure_set(
                fig, figure_id, source_rows, stage=stage, formats=formats, dpi=dpi,
                figure_kind="sample_overview", sample_id=run.batch_id, view=plot_type,
                page=page_index, warnings=page_warnings,
            ))
            for warning in page_warnings:
                warnings.append({"scope": figure_id, "warning": warning})
    return figures, warnings, dimensionless_rows

def _plot_evolution(
    rows: list[dict[str, Any]], *, stage: Path, run: AutoBatchRun,
    formats: tuple[str, ...], dpi: int, exploratory: bool = False,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    if not rows:
        return figures
    keys = sorted({(r["analysis_type"], r["model_name"], r["parameter_name"], r["unit"]) for r in rows})
    for analysis_type, model, parameter, unit in keys:
        track = [r for r in rows if (r["analysis_type"], r["model_name"], r["parameter_name"], r["unit"]) == (analysis_type, model, parameter, unit)]
        if any(_finite_number(row.get("frame_x")) is None for row in track):
            track.sort(key=_frame_order)
        else:
            track.sort(key=lambda row: (_finite_number(row.get("frame_x")), float(row["input_order"])))
        kind = "exploratory_parameter_evolution" if exploratory else "reliable_parameter_evolution"
        def eligible(row):
            if not exploratory:
                return row["reliable_reportable"]
            return (row["reporting_status"] == "exploratory"
                    and row["envelope_status"] in {"success", "assumption_dependent"}
                    and row["parameter_status"] in {"success", "assumption_dependent"}
                    and row["reliability_label"] != "invalid"
                    and row.get("bound_hit") is not True)
        values = [row["value"] if eligible(row) else np.nan for row in track]
        x = [float(row["frame_x"]) if _finite_number(row.get("frame_x")) is not None else np.nan for row in track]
        if not any(math.isfinite(float(value)) and math.isfinite(frame_x) for value, frame_x in zip(values, x) if value is not None):
            continue
        sample = track[0]["sample_id"]
        fig = Figure(figsize=(7.5, 4.6), dpi=100)
        ax = fig.add_subplot(111)
        curve_ids = [row["curve_id"] for row in track if row["curve_id"]]
        multiple_features = len(set(curve_ids)) < len(curve_ids)
        ax.plot(x, values, marker="o", markerfacecolor="none" if exploratory else None,
                linestyle="none" if multiple_features else "--" if exploratory else "-", linewidth=1.2,
                label=f"{analysis_type}{' / ' + model if model else ''} / {parameter}")
        ax.set_xlabel(f"Sequence coordinate ({track[0]['frame_x_source']})")
        ax.set_ylabel(f"{parameter} ({unit})" if unit else parameter)
        qualifier = "Exploratory candidate — " if exploratory else ""
        ax.set_title(f"{qualifier}{sample} — {analysis_type}{' / ' + model if model else ''} — {parameter} evolution")
        ax.legend(fontsize=8)
        fig.tight_layout()
        source_rows = []
        for row, y in zip(track, values):
            source_rows.append({
                "sample_id": row["sample_id"], "series_id": row["series_id"], "curve_id": row["curve_id"],
                "curve_name": row["curve_name"], "source_file": row["source_file"], "frame_index": row["frame_index"],
                "frame_label": row["frame_label"], "sequence_order": row["sequence_order"],
                "analysis_id": row["analysis_id"], "analysis_type": analysis_type, "model_name": model,
                "analysis_status": row["envelope_status"], "reliability_status": row["reliability_status"],
                "reporting_status": row["reporting_status"],
                "plot_type": kind, "point_index": _frame_order(row),
                "q": None, "I": None, "error": None, "x": row["frame_x"], "y": y, "yerr": None,
                "x_unit": row["frame_x_source"], "y_unit": unit,
            })
        figure_id = f"evolution_{_token(sample)}_{_token(analysis_type)}_{_token(model)}_{_token(parameter)}"
        figure_id += f"_{_stable_suffix(sample, analysis_type, model, parameter, unit)}"
        if exploratory:
            figure_id += "_exploratory"
        figures.extend(_write_figure_set(
            fig, figure_id, source_rows, stage=stage, formats=formats, dpi=dpi,
            figure_kind=kind, sample_id=sample,
            view=f"{analysis_type}:{model}:{parameter}", page=None,
            warnings=["Exploratory values retain their method assumptions and quality flags; this plot does not upgrade their reporting status."] if exploratory else [],
        ))
    return figures


def _fit_plot_specs(envelope: Any) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    tables = getattr(envelope, "tables", {})
    if not isinstance(tables, dict):
        return specs
    for table_name, rows in tables.items():
        if not isinstance(rows, list) or not rows:
            continue
        row_dicts = [row for row in rows if isinstance(row, dict)]
        if not row_dicts:
            continue
        columns = set().union(*(row.keys() for row in row_dicts))
        observed = next((key for key in ("I_observed", "observed") if key in columns), None)
        fitted = next((key for key in ("I_fit", "fitted", "I_back_calculated", "back_calculated", "I_backfit", "backfit") if key in columns), None)
        if str(table_name) not in {"residual_rows", "residuals"} and "q" in columns and observed and fitted:
            specs.append({
                "table_name": str(table_name), "rows": row_dicts, "observed": observed, "fitted": fitted,
                "label": "P(r) back-fit" if str(table_name) == "pr_backfit" else "Model fit",
                "x_mode": "q", "coordinate": "measured q versus intensity",
                "transformed": False,
            })
            continue
        if str(table_name) not in {"residual_rows", "residuals"} or not {"q", "observed", "fitted"} <= columns:
            continue
        coordinate = next((str(row.get("fit_coordinate")) for row in row_dicts if row.get("fit_coordinate")), "")
        if not coordinate:
            coordinate = str(getattr(envelope, "fit_quality", {}).get("fit_coordinate", ""))
        if not coordinate:
            coordinate = {"guinier": "ln(I) versus q^2", "power_law": "lg(I) versus lg(q)"}.get(str(envelope.analysis_type), "")
        normalized = coordinate.casefold().replace("²", "^2")
        if "q^2" in normalized:
            x_mode = "q2"
        elif "lg(q)" in normalized or "log10(q)" in normalized:
            x_mode = "log10_q"
        else:
            continue
        is_log = "ln(i)" in normalized or "lg(i)" in normalized or "log10(i)" in normalized
        if not is_log:
            continue
        specs.append({
            "table_name": str(table_name), "rows": row_dicts, "observed": "observed", "fitted": "fitted",
            "label": "Fitted transformed profile", "x_mode": x_mode, "coordinate": coordinate,
            "transformed": True,
        })
    return specs


def _plot_fit_tables(
    run: AutoBatchRun, ordered: list[tuple[CurveData, dict[str, Any], float, str]], *,
    stage: Path, formats: tuple[str, ...], dpi: int,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    meta_by_id = {str(curve.curve_id): (curve, meta) for curve, meta, _, _ in ordered}
    for envelope in run.analyses:
        found = meta_by_id.get(str(getattr(envelope, "curve_id", "")))
        if found is None:
            continue
        curve, meta = found
        for spec in _fit_plot_specs(envelope):
            table_name = spec["table_name"]
            rows = spec["rows"]
            observed_key, fitted_key = spec["observed"], spec["fitted"]
            x_mode = spec["x_mode"]
            coordinate = spec["coordinate"]
            transformed = bool(spec["transformed"])
            fitted_label = spec["label"]
            if x_mode == "q2":
                x_label, x_unit = f"q² ({curve.q_unit})²", f"({curve.q_unit})²"
                log_kind = "ln"
            elif x_mode == "log10_q":
                x_label, x_unit = f"lg q ({curve.q_unit})", f"dimensionless log10(q numeric value in {curve.q_unit})"
                log_kind = "lg"
            else:
                x_label, x_unit = f"q ({curve.q_unit})", curve.q_unit
                log_kind = ""
            y_unit = (
                f"dimensionless {log_kind}(I numeric value in {curve.intensity_unit})"
                if transformed else curve.intensity_unit
            )
            y_label = (
                f"{log_kind} I(q) ({y_unit})" if transformed else f"I(q) ({curve.intensity_unit})"
            )

            def x_for(row: dict[str, Any]) -> tuple[float | None, float | None]:
                q = _finite_number(row.get("q"))
                if x_mode == "q":
                    return q, q
                measured_x = _finite_number(row.get("transformed_x"))
                if measured_x is not None:
                    return measured_x, q
                if q is None:
                    return None, None
                if x_mode == "q2":
                    return q * q, q
                if q <= 0.0:
                    return None, q
                return math.log10(q), q

            data: list[dict[str, Any]] = []
            warnings: list[str] = []
            observed_points = []
            fit_points = []
            residual_points = []
            for point_index, row in enumerate(rows):
                x_value, q = x_for(row)
                obs = _finite_number(row.get(observed_key))
                fitted = _finite_number(row.get(fitted_key))
                residual = _finite_number(row.get("residual"))
                original_index = row.get("original_index", point_index)
                if x_value is not None and obs is not None:
                    observed_points.append((x_value, obs, q, original_index, row))
                if x_value is not None and fitted is not None:
                    fit_points.append((x_value, fitted, q, original_index, row))
                if x_value is not None and residual is not None:
                    residual_points.append((x_value, residual, q, original_index, row))
            fig = Figure(figsize=(8.0, 6.0 if residual_points else 4.8), dpi=100)
            if residual_points:
                ax, residual_ax = fig.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
                residual_ax.axhline(0.0, color="0.35", linewidth=0.8)
                residual_ax.plot([point[0] for point in residual_points], [point[1] for point in residual_points], marker="o", markersize=2.5, linewidth=0.8, label="Residual")
                residual_ax.set_ylabel(f"Residual ({y_unit})")
                residual_ax.set_xlabel(x_label)
            else:
                ax = fig.add_subplot(111)
                ax.set_xlabel(x_label)
            observed_label = "Experimental transformed signal" if transformed else "Experimental I(q)"
            ax.plot([point[0] for point in observed_points], [point[1] for point in observed_points], "o", markersize=3, label=observed_label)
            ax.plot([point[0] for point in fit_points], [point[1] for point in fit_points], "-", linewidth=1.2, label=fitted_label)
            ax.set_ylabel(y_label)
            ax.set_title(f"{curve.name} — {envelope.analysis_type} / {table_name} — {coordinate}")
            ax.legend(fontsize=8)
            fig.tight_layout()
            for series, points in (("experimental", observed_points), ("fit", fit_points), ("residual", residual_points)):
                for x, y, q, point_index, raw_row in points:
                    data.append({
                        **meta, "analysis_id": str(envelope.analysis_id), "analysis_type": str(envelope.analysis_type),
                        "model_name": _envelope_model(envelope), "analysis_status": _status(envelope.status),
                        "reliability_status": str(envelope.reliability_status),
                        "reporting_status": str(envelope.reporting_status),
                        "plot_type": f"{table_name}:{series}",
                        "point_index": point_index, "q": q,
                        "I": _finite_number(raw_row.get("intensity")) if transformed else (y if series == "experimental" else None),
                        "error": _finite_number(raw_row.get("error")),
                        "x": x, "y": y, "yerr": None, "x_unit": x_unit,
                        "y_unit": f"{y_unit} (residual)" if series == "residual" else y_unit,
                    })
            if not observed_points:
                warnings.append("No finite experimental rows were available in the exported fit table.")
            if not fit_points:
                warnings.append("No finite fitted rows were available in the exported fit table.")
            figure_id = f"fit_{_token(curve.name)}_{_token(envelope.analysis_type)}_{_token(table_name)}_{_stable_suffix(curve.curve_id, envelope.analysis_id, table_name)}"
            figures.extend(_write_figure_set(
                fig, figure_id, data, stage=stage, formats=formats, dpi=dpi,
                figure_kind="fit_and_residual", sample_id=meta["sample_id"],
                view=table_name, page=None, warnings=warnings,
                analysis_id=str(envelope.analysis_id), table_name=table_name,
            ))
    return figures


def _distribution_specs(envelope: Any) -> list[tuple[str, list[dict[str, Any]], str, str, str]]:
    result = []
    tables = getattr(envelope, "tables", {})
    if not isinstance(tables, dict):
        return result
    for table_name, x_key, y_candidates, label in (
        ("pr_distribution", "r", ("P(r)", "P_r"), "P(r) candidate from supplied inversion"),
        ("correlation_function", "r", ("correlation",), "Finite-q correlation function"),
    ):
        rows = tables.get(table_name)
        if isinstance(rows, list):
            y_key = next((candidate for candidate in y_candidates if any(isinstance(row, dict) and candidate in row for row in rows)), None)
            matching = [row for row in rows if isinstance(row, dict) and x_key in row and y_key in row] if y_key else []
            if matching:
                result.append((table_name, matching, x_key, y_key, label))
    return result


def _plot_distribution_tables(
    run: AutoBatchRun, ordered: list[tuple[CurveData, dict[str, Any], float, str]], *,
    stage: Path, formats: tuple[str, ...], dpi: int,
) -> list[dict[str, Any]]:
    figures: list[dict[str, Any]] = []
    meta_by_id = {str(curve.curve_id): (curve, meta) for curve, meta, _, _ in ordered}
    for envelope in run.analyses:
        found = meta_by_id.get(str(getattr(envelope, "curve_id", "")))
        if found is None:
            continue
        curve, meta = found
        for table_name, rows, x_key, y_key, label in _distribution_specs(envelope):
            points = [(_finite_number(row.get(x_key)), _finite_number(row.get(y_key)), index) for index, row in enumerate(rows)]
            points = [(x, y, i) for x, y, i in points if x is not None and y is not None]
            fig = Figure(figsize=(7.4, 4.8), dpi=100)
            ax = fig.add_subplot(111)
            ax.plot([p[0] for p in points], [p[1] for p in points], linewidth=1.2, label=label)
            r_unit = str(rows[0].get("r_unit") or f"1/({curve.q_unit})")
            ax.set_xlabel(f"r ({r_unit})")
            ax.set_ylabel("P(r) (candidate distribution)" if table_name == "pr_distribution" else "Correlation function (reported transform)")
            ax.set_title(f"{curve.name} — {label}")
            ax.legend(fontsize=8)
            fig.tight_layout()
            data = []
            for x, y, point_index in points:
                data.append({
                    **meta, "analysis_id": str(envelope.analysis_id), "analysis_type": str(envelope.analysis_type),
                    "model_name": "", "analysis_status": _status(envelope.status),
                    "reliability_status": str(envelope.reliability_status),
                    "reporting_status": str(envelope.reporting_status),
                    "plot_type": table_name, "point_index": point_index,
                    "q": None, "I": None, "error": None, "x": x, "y": y, "yerr": None,
                    "x_unit": r_unit, "y_unit": str(y_key),
                })
            figure_id = f"derived_{_token(curve.name)}_{_token(table_name)}_{_stable_suffix(curve.curve_id, envelope.analysis_id, table_name)}"
            figures.extend(_write_figure_set(
                fig, figure_id, data, stage=stage, formats=formats, dpi=dpi,
                figure_kind="reported_distribution", sample_id=meta["sample_id"],
                view=table_name, page=None, warnings=[], analysis_id=str(envelope.analysis_id),
                table_name=table_name,
            ))
    return figures

def export_bundle_figures(
    run: AutoBatchRun, ordered: list[tuple[CurveData, dict[str, Any], float | None, str]],
    dimensionless: dict[str, dict[str, Any]], evolution_rows: list[dict[str, Any]], *,
    stage: Path, formats: tuple[str, ...], dpi: int, max_overlay_curves: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    overview, warnings, dimensionless_rows = _plot_overview_pages(
        run, ordered, dimensionless, stage=stage, formats=formats, dpi=dpi,
        max_overlay_curves=max_overlay_curves,
    )
    figures = overview
    figures.extend(_plot_evolution(evolution_rows, stage=stage, run=run, formats=formats, dpi=dpi))
    figures.extend(_plot_evolution(evolution_rows, stage=stage, run=run, formats=formats, dpi=dpi, exploratory=True))
    figures.extend(_plot_fit_tables(run, ordered, stage=stage, formats=formats, dpi=dpi))
    figures.extend(_plot_distribution_tables(run, ordered, stage=stage, formats=formats, dpi=dpi))
    return figures, warnings, dimensionless_rows


__all__ = ["export_bundle_figures"]
