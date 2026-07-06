from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.analysis_schema import (
    EXPORT_TABLE_CORRELATION_FUNCTION,
    EXPORT_TABLE_FIT_CURVES,
    EXPORT_TABLE_GUINIER_CANDIDATES,
    EXPORT_TABLE_PEAKS,
    EXPORT_TABLE_POWER_LAW_CANDIDATES,
    EXPORT_TABLE_PR_DISTRIBUTION,
    scalar_result_items,
)
from app.core.data_model import AnalysisResult, ComparisonResult, CurveData
from app.core.plotting import create_curve_figure
from app.core.report import generate_markdown_report


def _json_default(value: Any):
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def export_curve_csv(curve: CurveData, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"q": curve.q, "I": curve.intensity}
    if curve.error is not None:
        data["error"] = curve.error
    pd.DataFrame(data).to_csv(target, index=False)
    return target


def export_analysis_json(result: AnalysisResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return target


def export_analysis_csv(results: list[AnalysisResult], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for result in results:
        row = {
            "analysis_id": result.analysis_id,
            "curve_id": result.curve_id,
            "analysis_type": result.analysis_type,
            "q_min": result.q_range[0],
            "q_max": result.q_range[1],
            "warnings": " | ".join(result.warnings),
            "structured_warnings": json.dumps(result.structured_warnings, ensure_ascii=False, default=_json_default),
        }
        for key, value in result.results.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                row[key] = value
            else:
                row[key] = json.dumps(value, ensure_ascii=False, default=_json_default)
        rows.append(row)
    pd.DataFrame(rows).to_csv(target, index=False)
    return target


def export_comparison_csv(result: ComparisonResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"q": result.q, result.comparison_type: result.values}).to_csv(target, index=False)
    return target


def export_figure(curves, path: str | Path, *, plot_type: str = "linear") -> tuple[Path, list[str]]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure, warnings = create_curve_figure(curves, plot_type=plot_type)
    figure.savefig(target)
    return target, warnings


def build_feature_table(curves: list[CurveData], analyses: list[AnalysisResult]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    by_curve: dict[str, list[AnalysisResult]] = {}
    for result in analyses:
        by_curve.setdefault(result.curve_id, []).append(result)

    for curve in curves:
        row: dict[str, Any] = {
            "curve_id": curve.curve_id,
            "name": curve.name,
            "q_min": float(curve.q.min()) if curve.q.size else None,
            "q_max": float(curve.q.max()) if curve.q.size else None,
            "I_min": float(curve.intensity.min()) if curve.intensity.size else None,
            "I_max": float(curve.intensity.max()) if curve.intensity.size else None,
            "data_points": int(curve.q.size),
            "dynamic_range": float(curve.intensity.max() / curve.intensity.min()) if curve.intensity.size and curve.intensity.min() > 0 else None,
        }
        for result in by_curve.get(curve.curve_id, []):
            prefix = result.analysis_type
            for key, value in result.results.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    row[f"{prefix}_{key}"] = value
                    row[f"{prefix}_{key}_analysis_id"] = result.analysis_id
                    row[f"{prefix}_{key}_q_range"] = f"{result.q_range[0]}:{result.q_range[1]}"
        rows.append(row)
    return pd.DataFrame(rows)


def export_feature_table(curves: list[CurveData], analyses: list[AnalysisResult], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    build_feature_table(curves, analyses).to_csv(target, index=False)
    return target


def _analysis_summary_rows(analyses: list[AnalysisResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in analyses:
        row = {
            "analysis_id": result.analysis_id,
            "curve_id": result.curve_id,
            "analysis_type": result.analysis_type,
            "q_min": result.q_range[0],
            "q_max": result.q_range[1],
            "warnings": " | ".join(result.warnings),
        }
        row.update(scalar_result_items(result.results))
        row["assumptions"] = " | ".join(result.results.get("assumptions", []))
        row["interpretation_limits"] = " | ".join(result.results.get("interpretation_limits", []))
        rows.append(row)
    return rows


def _table_rows(analyses: list[AnalysisResult], table_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in analyses:
        tables = result.results.get("export_tables", {})
        table = tables.get(table_name)
        if table is None:
            if table_name == EXPORT_TABLE_PEAKS:
                table = result.results.get("peaks") or result.results.get("indexed_peaks")
            elif table_name == EXPORT_TABLE_PR_DISTRIBUTION and "r" in result.results and "P(r)" in result.results:
                table = [{"r": r, "P(r)": p} for r, p in zip(result.results["r"], result.results["P(r)"])]
            elif table_name == EXPORT_TABLE_CORRELATION_FUNCTION and "r" in result.results and "correlation" in result.results:
                table = [{"r": r, "correlation": c} for r, c in zip(result.results["r"], result.results["correlation"])]
        if table is None:
            continue
        if isinstance(table, dict):
            table = [table]
        for item in table:
            if not isinstance(item, dict):
                item = {"value": item}
            row = {
                "analysis_id": result.analysis_id,
                "curve_id": result.curve_id,
                "analysis_type": result.analysis_type,
            }
            row.update(item)
            rows.append(row)
    return rows


def export_analysis_bundle(
    curves: list[CurveData],
    analyses: list[AnalysisResult],
    folder: str | Path,
    *,
    project_name: str = "sas_curve_analyzer",
    history=None,
    formal_records=None,
) -> dict[str, Path]:
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}

    full_json = target / "analysis_full.json"
    full_json.write_text(json.dumps([asdict(result) for result in analyses], ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    outputs["analysis_full"] = full_json

    summary_csv = target / "analysis_summary.csv"
    pd.DataFrame(_analysis_summary_rows(analyses)).to_csv(summary_csv, index=False)
    outputs["analysis_summary"] = summary_csv

    feature_csv = export_feature_table(curves, analyses, target / "feature_table.csv")
    outputs["feature_table"] = feature_csv

    table_specs = {
        "fit_curves": EXPORT_TABLE_FIT_CURVES,
        "peaks": EXPORT_TABLE_PEAKS,
        "guinier_candidates": EXPORT_TABLE_GUINIER_CANDIDATES,
        "power_law_candidates": EXPORT_TABLE_POWER_LAW_CANDIDATES,
        "pr_distribution": EXPORT_TABLE_PR_DISTRIBUTION,
        "correlation_function": EXPORT_TABLE_CORRELATION_FUNCTION,
    }
    for file_stem, table_name in table_specs.items():
        rows = _table_rows(analyses, table_name)
        path = target / f"{file_stem}.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        outputs[file_stem] = path

    report_path = generate_markdown_report(
        target / "report.md",
        project_name=project_name,
        curves=curves,
        analyses=analyses,
        history=list(history or []),
        formal_records=list(formal_records or []),
    )
    outputs["report"] = report_path
    return outputs

