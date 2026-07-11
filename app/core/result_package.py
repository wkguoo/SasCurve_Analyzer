"""Non-destructive, audit-friendly result package export for auto batches."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from app.core.auto_batch_schema import AutoBatchRun
from app.core.data_model import CurveData


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _safe_name(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return text[:100] or "unnamed"


def _finite_minmax(values: Any) -> tuple[float | None, float | None]:
    try:
        array = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return None, None
    if array.size == 0:
        return None, None
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return None, None
    return float(np.min(finite)), float(np.max(finite))


def _curve_summary_for_export(curve: Any) -> dict[str, Any]:
    """Metadata-only curve record for run_summary.json (no q/I arrays)."""

    if isinstance(curve, CurveData):
        q_min, q_max = _finite_minmax(curve.q)
        n_points = int(np.asarray(curve.q).size)
        return {
            "curve_id": curve.curve_id,
            "name": curve.name,
            "q_unit": curve.q_unit,
            "intensity_unit": curve.intensity_unit,
            "source_file": curve.source_file,
            "parent_id": curve.parent_id,
            "created_at": curve.created_at,
            "n_points": n_points,
            "q_min": q_min,
            "q_max": q_max,
            "has_error": curve.error is not None,
        }
    if isinstance(curve, dict):
        summary = {
            key: curve.get(key)
            for key in (
                "curve_id",
                "name",
                "q_unit",
                "intensity_unit",
                "source_file",
                "parent_id",
                "created_at",
            )
            if key in curve
        }
        q_min, q_max = _finite_minmax(curve.get("q"))
        if "q" in curve:
            try:
                summary["n_points"] = int(np.asarray(curve.get("q")).size)
            except (TypeError, ValueError):
                summary["n_points"] = None
        summary["q_min"] = q_min
        summary["q_max"] = q_max
        summary["has_error"] = curve.get("error") is not None
        return summary
    return {"repr": str(curve)}


def _analysis_summary_for_export(analysis: dict[str, Any]) -> dict[str, Any]:
    """Drop full table bodies from run_summary; keep row counts only."""

    payload = dict(analysis)
    tables = payload.get("tables") or {}
    if isinstance(tables, dict):
        payload["tables"] = {
            str(name): {"row_count": len(rows) if isinstance(rows, list) else 0}
            for name, rows in tables.items()
        }
        payload["tables_exported"] = True
    return payload


def _run_summary_payload(run: AutoBatchRun) -> dict[str, Any]:
    """Build a compact run_summary that does not embed full curve arrays or fit tables."""

    payload = asdict(run)
    payload["curves"] = [_curve_summary_for_export(curve) for curve in run.curves]
    analyses = payload.get("analyses") or []
    if isinstance(analyses, list):
        payload["analyses"] = [
            _analysis_summary_for_export(item) if isinstance(item, dict) else item for item in analyses
        ]
    return payload


def _parameter_rows(run: AutoBatchRun) -> list[dict[str, Any]]:
    rows = []
    for envelope in run.analyses:
        for parameter in envelope.parameters:
            row = {
                "curve_id": envelope.curve_id,
                "curve_name": envelope.curve_name,
                "analysis_id": envelope.analysis_id,
                "analysis_type": envelope.analysis_type,
                "analysis_status": envelope.status.value,
                "q_start": None if envelope.q_range is None else envelope.q_range[0],
                "q_end": None if envelope.q_range is None else envelope.q_range[1],
                "reliability_label": envelope.reliability_label,
                "reliability_score": envelope.reliability_score,
            }
            row.update(asdict(parameter))
            row["status"] = parameter.status.value
            rows.append(row)
    return rows


def _fit_quality_rows(run: AutoBatchRun) -> list[dict[str, Any]]:
    return [
        {
            "curve_id": item.curve_id,
            "curve_name": item.curve_name,
            "analysis_id": item.analysis_id,
            "analysis_type": item.analysis_type,
            "status": item.status.value,
            "q_start": None if item.q_range is None else item.q_range[0],
            "q_end": None if item.q_range is None else item.q_range[1],
            "reliability_label": item.reliability_label,
            "reliability_score": item.reliability_score,
            "invalid_reason": item.invalid_reason,
            "warnings": " | ".join(item.warnings),
            **item.fit_quality,
        }
        for item in run.analyses
    ]


def _write_csv(path: Path, rows: Any) -> None:
    pd.DataFrame(rows if isinstance(rows, list) else []).to_csv(path, index=False, encoding="utf-8-sig")


def export_result_package(run: AutoBatchRun, output_dir: str | Path) -> Path:
    """Write a new result folder; cancelled runs receive an explicit incomplete suffix."""

    requested_target = Path(output_dir)
    target = (
        requested_target.with_name(f"{requested_target.name}_incomplete")
        if run.status == "cancelled"
        else requested_target
    )
    if target.exists():
        raise FileExistsError(f"Result package target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.incomplete-{uuid4().hex[:8]}")
    staging.mkdir()

    payload = _run_summary_payload(run)
    (staging / "run_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
    )
    _write_csv(staging / "parameters.csv", _parameter_rows(run))
    _write_csv(staging / "fit_quality.csv", _fit_quality_rows(run))
    _write_csv(staging / "model_rankings.csv", run.rankings)
    _write_csv(staging / "input_manifest.csv", run.input_manifest)
    _write_csv(staging / "failed_inputs.csv", run.failed_inputs)
    _write_csv(staging / "warnings.csv", [{"warning": warning} for warning in run.warnings])

    sequence = run.sequence_results or {}
    for key in ("frame_table", "parameter_trajectories", "reference_comparisons", "change_flags", "linear_trends"):
        _write_csv(staging / f"sequence_{key}.csv", sequence.get(key, []))
    exploratory = sequence.get("exploratory_statistics", {})
    _write_csv(
        staging / "sequence_pca_clusters.csv",
        exploratory.get("scores", []) if isinstance(exploratory, dict) else [],
    )

    tables_dir = staging / "analysis_tables"
    tables_dir.mkdir()
    table_index = []
    for envelope in run.analyses:
        for table_name, rows in envelope.tables.items():
            filename = (
                f"{_safe_name(envelope.curve_name)}__{_safe_name(envelope.analysis_id)}__"
                f"{_safe_name(table_name)}.csv"
            )
            _write_csv(tables_dir / filename, rows)
            table_index.append(
                {
                    "curve_id": envelope.curve_id,
                    "analysis_id": envelope.analysis_id,
                    "analysis_type": envelope.analysis_type,
                    "table_name": table_name,
                    "file": f"analysis_tables/{filename}",
                    "row_count": len(rows),
                }
            )
    _write_csv(staging / "analysis_tables_index.csv", table_index)

    (staging / "README.md").write_text(
        "# SAS 自动分析结果包\n\n"
        f"- batch_id: `{run.batch_id}`\n- run_id: `{run.run_id}`\n- status: `{run.status}`\n"
        f"- curves: {len(run.curves)}\n- analysis envelopes: {len(run.analyses)}\n\n"
        "`parameters.csv` 汇总所有方法和模型参数；`fit_quality.csv` 保存拟合质量；"
        "`sequence_*.csv` 保存原位时序结果；`analysis_tables/` 保存拟合点、残差及方法明细。\n\n"
        "`run_summary.json` 仅含运行元数据、曲线摘要（不含完整 q/I 数组）与分析信封摘要"
        "（tables 仅保留行数）；完整曲线点请使用输入源文件与 `analysis_tables/`。\n\n"
        "## 批处理 status 含义\n\n"
        f"- 当前 status: `{run.status}`\n"
        "- `completed`：全部分析信封为 success。\n"
        "- `completed_with_limitations`：已有可用结果，但存在 missing_prerequisite / "
        "assumption_dependent / not_applicable。\n"
        "- `partial_success`：存在 fit_failed/invalid 等硬失败，同时仍有可用结果。\n"
        "- `failed`：没有 success 或 assumption_dependent 可用结果。\n"
        "- `cancelled`：用户取消（结果目录名可带 incomplete）。\n\n"
        "## 科研解释限制\n\n"
        "数值收敛、R²、AICc/BIC、bootstrap、参数连续、突变标记、PCA 或聚类均不能证明模型、"
        "结构、相变或机理唯一。请结合 q 范围、误差、标定、材料条件和其他表征复核。\n",
        encoding="utf-8",
    )
    staging.rename(target)
    return target


__all__ = ["export_result_package"]
