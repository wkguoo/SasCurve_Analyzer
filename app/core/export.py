from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.data_model import AnalysisResult, ComparisonResult, CurveData
from app.core.plotting import create_curve_figure


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

