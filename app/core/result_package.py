"""Non-destructive, audit-friendly result package export for auto batches."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from app.core.auto_batch_schema import AutoBatchRun


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

    payload = asdict(run)
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
        "## 科研解释限制\n\n"
        "数值收敛、R²、AICc/BIC、bootstrap、参数连续、突变标记、PCA 或聚类均不能证明模型、"
        "结构、相变或机理唯一。请结合 q 范围、误差、标定、材料条件和其他表征复核。\n",
        encoding="utf-8",
    )
    staging.rename(target)
    return target


__all__ = ["export_result_package"]
