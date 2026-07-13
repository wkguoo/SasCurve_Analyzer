"""Non-destructive, audit-friendly result package export for auto batches."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict
from enum import Enum
from hashlib import sha1
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import numpy as np
import pandas as pd

from app.core.auto_batch_schema import AnalysisStatus, AutoBatchRun
from app.core.batch_cache import load_run_checkpoint
from app.core.data_model import CurveData

DetailLevel = Literal["slim", "usable", "all", "none"]

_USABLE_DETAIL_STATUSES = {
    AnalysisStatus.SUCCESS,
    AnalysisStatus.ASSUMPTION_DEPENDENT,
}

_EMPTY_DETAIL_COLUMNS = {
    "crossovers": ["crossover_q", "crossover_d", "slope_difference", "confidence"],
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


def _detail_filename(envelope: Any, table_name: str) -> str:
    """Build a short, collision-resistant detail filename.

    Full UUID-based analysis IDs made Windows staging paths unnecessarily long
    and could fail near the legacy MAX_PATH boundary. The CSV index retains the
    complete analysis ID; the filename only needs readable method/table tokens
    plus a short deterministic suffix.
    """

    identity = f"{envelope.curve_id}|{envelope.analysis_id}|{table_name}"
    digest = sha1(identity.encode("utf-8")).hexdigest()[:8]
    return (
        f"{_safe_name(envelope.curve_name)}__{_safe_name(envelope.analysis_type)}__"
        f"{_safe_name(table_name)}__{digest}.csv"
    )


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


def _valid_q_range(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    try:
        q_low = float(value[0])
        q_high = float(value[1])
    except (TypeError, ValueError, OverflowError):
        return None
    if not np.isfinite(q_low) or not np.isfinite(q_high) or q_low >= q_high:
        return None
    return q_low, q_high


def _effective_q_range_for_run(run: AutoBatchRun) -> tuple[float, float] | None:
    return _valid_q_range(run.config_snapshot.get("effective_q_range"))


def _selected_q_values(values: Any, q_range: tuple[float, float] | None) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return np.asarray([], dtype=float)
    finite = array[np.isfinite(array)]
    if q_range is None:
        return finite
    return finite[(finite >= q_range[0]) & (finite <= q_range[1])]


def _curve_summary_for_export(
    curve: Any,
    effective_q_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Metadata-only curve record for run_summary.json (no q/I arrays)."""

    if isinstance(curve, CurveData):
        selected_q = _selected_q_values(curve.q, effective_q_range)
        summary = {
            "curve_id": curve.curve_id,
            "name": curve.name,
            "q_unit": curve.q_unit,
            "intensity_unit": curve.intensity_unit,
            "source_file": curve.source_file,
            "parent_id": curve.parent_id,
            "created_at": curve.created_at,
            "n_points": int(selected_q.size),
            "q_min": None if selected_q.size == 0 else float(np.min(selected_q)),
            "q_max": None if selected_q.size == 0 else float(np.max(selected_q)),
            "has_error": curve.error is not None,
        }
        if effective_q_range is not None:
            summary["effective_q_range"] = list(effective_q_range)
        return summary
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
        if "q" in curve:
            selected_q = _selected_q_values(curve.get("q"), effective_q_range)
            summary["n_points"] = int(selected_q.size)
            summary["q_min"] = None if selected_q.size == 0 else float(np.min(selected_q))
            summary["q_max"] = None if selected_q.size == 0 else float(np.max(selected_q))
            summary["has_error"] = curve.get("error") is not None
        if effective_q_range is not None:
            summary["effective_q_range"] = list(effective_q_range)
        return summary
    return {"repr": str(curve)}


def _filter_detail_rows(
    table_name: str,
    rows: object,
    q_range: tuple[float, float] | None,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    normalized = [row for row in rows if isinstance(row, dict)]
    if q_range is None:
        return normalized
    filtered: list[dict[str, Any]] = []
    for row in normalized:
        if "q" in row:
            try:
                q_value = float(row.get("q"))
            except (TypeError, ValueError):
                continue
            if np.isfinite(q_value) and q_range[0] <= q_value <= q_range[1]:
                filtered.append(row)
            continue
        interval_start = row.get("q_start", row.get("q_min"))
        interval_end = row.get("q_end", row.get("q_max"))
        if interval_start is not None or interval_end is not None:
            try:
                start_value = float(interval_start)
                end_value = float(interval_end)
            except (TypeError, ValueError):
                continue
            if (
                np.isfinite(start_value)
                and np.isfinite(end_value)
                and q_range[0] <= start_value <= end_value <= q_range[1]
            ):
                filtered.append(row)
            continue
        # Rows without a q-bearing field are metadata/status rows rather
        # than data coordinates, so retaining them does not introduce an
        # out-of-range q value.
        filtered.append(row)
    return filtered


def _analysis_summary_for_export(
    analysis: dict[str, Any],
    effective_q_range: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Drop full table bodies from run_summary; keep row counts only."""

    payload = dict(analysis)
    tables = payload.get("tables") or {}
    if isinstance(tables, dict):
        payload["tables"] = {
            str(name): {
                "row_count": len(
                    _filter_detail_rows(
                        str(name),
                        rows,
                        effective_q_range,
                    )
                )
            }
            for name, rows in tables.items()
        }
        payload["tables_exported"] = True
    return payload


def _run_summary_payload(run: AutoBatchRun) -> dict[str, Any]:
    """Build a compact run_summary that does not embed full curve arrays or fit tables."""

    payload = asdict(run)
    effective_q_range = _effective_q_range_for_run(run)
    payload["curves"] = [
        _curve_summary_for_export(curve, effective_q_range) for curve in run.curves
    ]
    analyses = payload.get("analyses") or []
    if isinstance(analyses, list):
        payload["analyses"] = [
            _analysis_summary_for_export(item, effective_q_range)
            if isinstance(item, dict)
            else item
            for item in analyses
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
                "execution_status": envelope.execution_status,
                "candidate_status": envelope.candidate_status,
                "consensus_status": envelope.consensus_status,
                "detection_status": envelope.detection_status,
                "reliability_status": envelope.reliability_status,
                "reporting_status": envelope.reporting_status,
                "reporting_reason_codes": " | ".join(envelope.reporting_reason_codes),
                "related_analysis_ids": " | ".join(envelope.related_analysis_ids),
                "feature_relation": envelope.feature_relation,
                "range_source": envelope.range_source,
                "range_reason_codes": " | ".join(envelope.range_reason_codes),
                "q_selection_basis": envelope.q_selection_basis,
                "q_selection_evidence": envelope.q_selection_evidence,
                "detection_reason_codes": " | ".join(envelope.detection_reason_codes),
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
            "execution_status": item.execution_status,
            "candidate_status": item.candidate_status,
            "consensus_status": item.consensus_status,
            "detection_status": item.detection_status,
            "reliability_status": item.reliability_status,
            "reporting_status": item.reporting_status,
            "reporting_reason_codes": " | ".join(item.reporting_reason_codes),
            "related_analysis_ids": " | ".join(item.related_analysis_ids),
            "feature_relation": item.feature_relation,
            "range_source": item.range_source,
            "range_reason_codes": " | ".join(item.range_reason_codes),
            "q_selection_basis": item.q_selection_basis,
            "q_selection_evidence": item.q_selection_evidence,
            "detection_reason_codes": " | ".join(item.detection_reason_codes),
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


def _reliable_scalar(value: Any) -> str | bool | int | float | None:
    """Return a CSV-safe scalar, rejecting containers and non-finite numbers."""

    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and np.isfinite(value):
        return value
    return None


def _reliable_parameter_rows(run: AutoBatchRun) -> list[dict[str, Any]]:
    rows = []
    for row in _parameter_rows(run):
        if row.get("analysis_status") not in {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}:
            continue
        if row.get("status") not in {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}:
            continue
        reporting_status = str(row.get("reporting_status") or "")
        if reporting_status not in {"", "not_evaluated", "reportable"}:
            continue
        scalar_value = _reliable_scalar(row.get("value"))
        if scalar_value is None:
            continue
        label = str(row.get("reliability_label") or "")
        score = row.get("reliability_score")
        try:
            numeric_score = float(score) if score is not None else None
        except (TypeError, ValueError):
            numeric_score = None
        if label in {"invalid", "low"}:
            continue
        if numeric_score is None or numeric_score < 0.5:
            continue
        row["value"] = scalar_value
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

    if detail_level not in {"slim", "usable", "all", "none"}:
        raise ValueError("detail_level must be slim, usable, all, or none")

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
    effective_q_range = _effective_q_range_for_run(run)
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
    _write_csv(audit_dir / "range_audit.csv", run.range_audit)
    consensus_rows = []
    for region_name, detail in (run.consensus_region_details or {}).items():
        row = {"region_type": region_name}
        if isinstance(detail, dict):
            row.update(detail)
        consensus_rows.append(row)
    _write_csv(audit_dir / "consensus_regions.csv", consensus_rows)
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
                if detail_level == "slim" and table_name != "invariant_integrand":
                    continue
                filtered_rows = _filter_detail_rows(table_name, rows, effective_q_range)
                if not filtered_rows:
                    continue
                filename = _detail_filename(envelope, table_name)
                _write_csv(tables_dir / filename, filtered_rows)
                table_index.append(
                    {
                        "curve_id": envelope.curve_id,
                        "analysis_id": envelope.analysis_id,
                        "analysis_type": envelope.analysis_type,
                        "analysis_status": envelope.status.value,
                        "table_name": table_name,
                        "file": f"details/analysis_tables/{filename}",
                        "row_count": len(filtered_rows),
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
        "- `range_audit.csv` / `consensus_regions.csv`：逐任务区间来源、候选/共识状态及证据\n"
        "- `warnings.csv` / `failed_inputs.csv`\n"
        "- `analysis_tables_index.csv`：明细表索引\n"
        "- 非空 `sequence_*.csv`：原位序列审计\n",
        encoding="utf-8",
    )
    (details_dir / "README.md").write_text(
        "# details — 方法明细（残差、拟合点等）\n\n"
        f"- detail_level: `{detail_level}`\n"
        "- `slim`：仅导出非空、有效 q 范围内的不变量积分明细。\n"
        "- `usable`：导出 success / assumption_dependent 的非空明细表。\n"
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


def export_details_archive(
    run: AutoBatchRun,
    output_zip: str | Path,
) -> Path:
    """Write every method detail table to a separate q-filtered ZIP archive.

    Empty tables are retained as zero-row CSVs so the archive preserves the
    complete per-frame table inventory (including methods that had no usable
    crossover rows).  Data-bearing rows are filtered against the run-level
    effective q interval before they are written.
    """

    target = Path(output_zip)
    if target.exists():
        raise FileExistsError(f"Detail archive target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    effective_q_range = _effective_q_range_for_run(run)
    table_index: list[dict[str, Any]] = []
    with zipfile.ZipFile(target, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for envelope in run.analyses:
            for table_name, rows in envelope.tables.items():
                filtered_rows = _filter_detail_rows(table_name, rows, effective_q_range)
                filename = _detail_filename(envelope, table_name)
                columns = None if filtered_rows else _EMPTY_DETAIL_COLUMNS.get(table_name)
                csv_text = pd.DataFrame(filtered_rows, columns=columns).to_csv(index=False)
                archive.writestr(
                    f"analysis_tables/{filename}",
                    "\ufeff" + csv_text,
                )
                table_index.append(
                    {
                        "curve_id": envelope.curve_id,
                        "analysis_id": envelope.analysis_id,
                        "analysis_type": envelope.analysis_type,
                        "analysis_status": envelope.status.value,
                        "table_name": table_name,
                        "file": f"analysis_tables/{filename}",
                        "row_count": len(filtered_rows),
                    }
                )
        archive.writestr(
            "details_index.csv",
            "\ufeff" + pd.DataFrame(table_index).to_csv(index=False),
        )
        q_text = "not configured" if effective_q_range is None else (
            f"{effective_q_range[0]:.12g}–{effective_q_range[1]:.12g} Å⁻¹"
        )
        archive.writestr(
            "README_details_full.md",
            "# Full SAXS detail archive\n\n"
            f"- Effective q range: `{q_text}`\n"
            f"- Analysis envelopes: `{len(run.analyses)}`\n"
            f"- Detail CSV tables: `{len(table_index)}`\n"
            "- Every data-bearing q row is restricted to the effective q range.\n"
            "- Zero-row tables are retained to preserve the complete per-frame inventory.\n"
            "- Original source CSV files are not included.\n",
        )
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


__all__ = [
    "export_result_package",
    "export_result_package_from_checkpoint",
    "export_details_archive",
]
