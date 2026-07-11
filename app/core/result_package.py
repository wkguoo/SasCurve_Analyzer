"""Non-destructive, audit-friendly result package export for auto batches."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import numpy as np
import pandas as pd

from app.core.auto_batch_schema import AnalysisStatus, AutoBatchRun
from app.core.batch_cache import load_run_checkpoint
from app.core.data_model import CurveData

DetailLevel = Literal["usable", "all", "none"]

_USABLE_DETAIL_STATUSES = {
    AnalysisStatus.SUCCESS,
    AnalysisStatus.ASSUMPTION_DEPENDENT,
}


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
                "n_points",
                "q_min",
                "q_max",
                "has_error",
            )
            if key in curve
        }
        if "n_points" not in summary and "q" in curve:
            try:
                summary["n_points"] = int(np.asarray(curve.get("q")).size)
            except (TypeError, ValueError):
                summary["n_points"] = None
            q_min, q_max = _finite_minmax(curve.get("q"))
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


def _is_usable_envelope(status: AnalysisStatus | str) -> bool:
    value = status.value if isinstance(status, AnalysisStatus) else str(status)
    return value in {item.value for item in _USABLE_DETAIL_STATUSES}


def _reliable_parameter_rows(run: AutoBatchRun) -> list[dict[str, Any]]:
    rows = []
    for row in _parameter_rows(run):
        if row.get("analysis_status") not in {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}:
            continue
        if row.get("value") is None:
            continue
        label = str(row.get("reliability_label") or "")
        score = row.get("reliability_score")
        try:
            numeric_score = float(score) if score is not None else None
        except (TypeError, ValueError):
            numeric_score = None
        if label in {"invalid", "low"}:
            continue
        if numeric_score is not None and numeric_score < 0.5:
            continue
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows if isinstance(rows, list) else []).to_csv(path, index=False, encoding="utf-8-sig")


def _write_csv_if_rows(path: Path, rows: Any) -> bool:
    if not isinstance(rows, list) or not rows:
        return False
    _write_csv(path, rows)
    return True


def export_result_package(
    run: AutoBatchRun,
    output_dir: str | Path,
    *,
    detail_level: DetailLevel = "usable",
) -> Path:
    """Write a tiered result package: summary/, audit/, details/.

    ``detail_level`` controls method detail tables:
    - ``usable`` (default): only success / assumption_dependent envelopes
    - ``all``: every envelope with tables
    - ``none``: skip details/analysis_tables
    """

    if detail_level not in {"usable", "all", "none"}:
        raise ValueError("detail_level must be usable, all, or none")

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

    summary_dir = staging / "summary"
    audit_dir = staging / "audit"
    details_dir = staging / "details"
    summary_dir.mkdir()
    audit_dir.mkdir()
    details_dir.mkdir()

    payload = _run_summary_payload(run)
    (summary_dir / "run_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8"
    )
    _write_csv(summary_dir / "model_rankings.csv", run.rankings)
    _write_csv(summary_dir / "input_manifest.csv", run.input_manifest)
    _write_csv(summary_dir / "reliable_parameters.csv", _reliable_parameter_rows(run))
    _write_csv(
        summary_dir / "fit_quality_usable.csv",
        [row for row in _fit_quality_rows(run) if _is_usable_envelope(str(row.get("status")))],
    )
    if run.main_model is not None:
        (summary_dir / "main_model.txt").write_text(f"{run.main_model}\n", encoding="utf-8")

    _write_csv(audit_dir / "parameters.csv", _parameter_rows(run))
    _write_csv(audit_dir / "fit_quality.csv", _fit_quality_rows(run))
    _write_csv(audit_dir / "failed_inputs.csv", run.failed_inputs)
    _write_csv(audit_dir / "warnings.csv", [{"warning": warning} for warning in run.warnings])
    if run.transition_flags:
        _write_csv(audit_dir / "model_transition_flags.csv", run.transition_flags)

    sequence = run.sequence_results or {}
    for key in ("frame_table", "parameter_trajectories", "reference_comparisons", "change_flags", "linear_trends"):
        rows = sequence.get(key, [])
        if key == "frame_table":
            _write_csv_if_rows(summary_dir / f"sequence_{key}.csv", rows)
        _write_csv_if_rows(audit_dir / f"sequence_{key}.csv", rows)
    exploratory = sequence.get("exploratory_statistics", {})
    scores = exploratory.get("scores", []) if isinstance(exploratory, dict) else []
    _write_csv_if_rows(audit_dir / "sequence_pca_clusters.csv", scores)

    tables_dir = details_dir / "analysis_tables"
    tables_dir.mkdir()
    table_index = []
    if detail_level != "none":
        for envelope in run.analyses:
            if detail_level == "usable" and not _is_usable_envelope(envelope.status):
                continue
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
                        "analysis_status": envelope.status.value,
                        "table_name": table_name,
                        "file": f"details/analysis_tables/{filename}",
                        "row_count": len(rows),
                    }
                )
    _write_csv(audit_dir / "analysis_tables_index.csv", table_index)

    (summary_dir / "README.md").write_text(
        "# summary — 建议首先阅读\n\n"
        f"- batch_id: `{run.batch_id}`\n"
        f"- run_id: `{run.run_id}`\n"
        f"- status: `{run.status}`\n"
        f"- main_model: `{run.main_model}`\n"
        f"- curves: {len(run.curves)}\n"
        f"- analysis envelopes: {len(run.analyses)}\n\n"
        "本目录只保留最终结论相关文件：\n"
        "- `run_summary.json`：运行元数据与曲线摘要（不含完整 q/I）\n"
        "- `reliable_parameters.csv`：较可靠的标量参数\n"
        "- `fit_quality_usable.csv`：可用状态的拟合质量\n"
        "- `model_rankings.csv` / `main_model.txt`：模型排序与主模型\n"
        "- `input_manifest.csv`：输入溯源\n",
        encoding="utf-8",
    )
    (audit_dir / "README.md").write_text(
        "# audit — 质量检查与完整审计\n\n"
        "- `parameters.csv` / `fit_quality.csv`：全部方法与状态\n"
        "- `warnings.csv` / `failed_inputs.csv`\n"
        "- `analysis_tables_index.csv`：明细表索引\n"
        "- 非空 `sequence_*.csv`：原位序列审计\n",
        encoding="utf-8",
    )
    (details_dir / "README.md").write_text(
        "# details — 方法明细（残差、拟合点等）\n\n"
        f"- detail_level: `{detail_level}`\n"
        "- 默认 `usable`：仅导出 success / assumption_dependent 的明细表。\n"
        "- 使用 `detail_level='all'` 可导出全部方法明细。\n",
        encoding="utf-8",
    )
    (staging / "README.md").write_text(
        "# SAS 自动分析结果包（三级结构）\n\n"
        f"- batch_id: `{run.batch_id}`\n- run_id: `{run.run_id}`\n- status: `{run.status}`\n"
        f"- curves: {len(run.curves)}\n- analysis envelopes: {len(run.analyses)}\n\n"
        "## 目录\n\n"
        "1. **`summary/`** — 最终报告入口、可靠参数、核心排名（请先看这里）\n"
        "2. **`audit/`** — 质量检查、全部参数/警告、表索引\n"
        "3. **`details/`** — 模型点、残差与方法明细 CSV\n\n"
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


def export_result_package_from_checkpoint(
    cache_dir: str | Path,
    output_dir: str | Path,
    *,
    detail_level: DetailLevel = "usable",
) -> Path:
    """Re-export a result package from a compute checkpoint without recomputing."""

    run = load_run_checkpoint(cache_dir)
    return export_result_package(run, output_dir, detail_level=detail_level)


__all__ = ["export_result_package", "export_result_package_from_checkpoint"]
