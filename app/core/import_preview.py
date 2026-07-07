from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.batch_import import infer_curve_columns
from app.core.io import read_table


@dataclass(frozen=True)
class ImportPreview:
    path: str
    status: str
    columns: list[str] = field(default_factory=list)
    preview_rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    q_column: str | None = None
    intensity_column: str | None = None
    error_column: str | None = None
    q_unit: str | None = None
    intensity_unit: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def can_import(self) -> bool:
        return self.status in {"ok", "warning"}


def _find_column_case_insensitive(df: pd.DataFrame, column: str) -> str:
    if column in df.columns:
        return column
    normalized = {str(name).strip().lower(): str(name) for name in df.columns}
    key = str(column).strip().lower()
    if key in normalized:
        return normalized[key]
    raise KeyError(f"Column '{column}' was not found. Available columns: {list(df.columns)}")


def _numeric_column(df: pd.DataFrame, column: str) -> np.ndarray:
    actual = _find_column_case_insensitive(df, column)
    return pd.to_numeric(df[actual], errors="coerce").to_numpy(dtype=float)


def _finite_min_max(values: np.ndarray) -> tuple[float | None, float | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None, None
    return float(np.min(finite)), float(np.max(finite))


def preview_curve_file(
    path: str | Path,
    *,
    q_column: str | None = None,
    intensity_column: str | None = None,
    error_column: str | None = None,
    q_unit: str | None = None,
    intensity_unit: str | None = None,
    max_rows: int = 5,
) -> ImportPreview:
    file_path = Path(path)
    try:
        df = read_table(file_path)
    except Exception as exc:
        return ImportPreview(path=str(file_path), status="error", messages=[f"发生了什么：无法读取表格数据。", f"技术细节：{exc}"])

    columns = [str(column) for column in df.columns]
    preview_rows = df.head(max_rows).replace({np.nan: None}).to_dict(orient="records")
    messages: list[str] = []
    diagnostics: dict[str, Any] = {"row_count": int(len(df)), "column_count": int(len(columns))}

    if df.empty:
        return ImportPreview(
            path=str(file_path),
            status="error",
            columns=columns,
            preview_rows=preview_rows,
            row_count=0,
            diagnostics=diagnostics,
            messages=["文件没有可用数据行。", "row_count=0。"],
        )

    try:
        inferred = None
        if q_column is None or intensity_column is None:
            inferred = infer_curve_columns(columns)
            q_column = inferred.q_column
            intensity_column = inferred.intensity_column
            if error_column is None:
                error_column = inferred.error_column
            messages.extend(inferred.warnings)
        else:
            try:
                inferred = infer_curve_columns(columns)
            except Exception:
                inferred = None

        q_unit = (q_unit.strip() if isinstance(q_unit, str) else q_unit) or None
        intensity_unit = (intensity_unit.strip() if isinstance(intensity_unit, str) else intensity_unit) or None
        if q_unit is None:
            q_unit = inferred.q_unit if inferred is not None else "A^-1"
            if inferred is None:
                messages.append("Warning：q unit 未显式传入且无法从列名推断，预览使用默认值 A^-1。")
        if intensity_unit is None:
            intensity_unit = inferred.intensity_unit if inferred is not None else "a.u."
            if inferred is None:
                messages.append("Warning：intensity unit 未显式传入且无法从列名推断，预览使用默认值 a.u.。")

        if error_column is not None and not str(error_column).strip():
            error_column = None

        q = _numeric_column(df, q_column)
        intensity = _numeric_column(df, intensity_column)
        error = None if error_column is None else _numeric_column(df, error_column)
    except Exception as exc:
        return ImportPreview(
            path=str(file_path),
            status="error",
            columns=columns,
            preview_rows=preview_rows,
            row_count=int(len(df)),
            q_column=q_column,
            intensity_column=intensity_column,
            error_column=error_column,
            diagnostics=diagnostics,
            messages=["当前列映射下无法导入。", f"q_column={q_column}", f"intensity_column={intensity_column}", f"error_column={error_column}", f"技术细节：{exc}"],
        )

    q_min, q_max = _finite_min_max(q)
    i_min, i_max = _finite_min_max(intensity)
    diagnostics.update(
        {
            "q_column": q_column,
            "intensity_column": intensity_column,
            "error_column": error_column,
            "q_unit": q_unit,
            "intensity_unit": intensity_unit,
            "q_min": q_min,
            "q_max": q_max,
            "intensity_min": i_min,
            "intensity_max": i_max,
            "q_nan_count": int(np.sum(~np.isfinite(q))),
            "intensity_nan_count": int(np.sum(~np.isfinite(intensity))),
            "q_non_positive_count": int(np.sum(np.isfinite(q) & (q <= 0))),
            "intensity_non_positive_count": int(np.sum(np.isfinite(intensity) & (intensity <= 0))),
            "intensity_negative_count": int(np.sum(np.isfinite(intensity) & (intensity < 0))),
        }
    )

    finite_q = q[np.isfinite(q)]
    diagnostics["q_duplicate_count"] = int(finite_q.size - np.unique(finite_q).size)
    diagnostics["q_strictly_increasing"] = bool(finite_q.size > 1 and np.all(np.diff(finite_q) > 0))
    diagnostics["finite_q_count"] = int(finite_q.size)
    diagnostics["finite_intensity_count"] = int(np.sum(np.isfinite(intensity)))

    if error is not None:
        diagnostics["error_nan_count"] = int(np.sum(~np.isfinite(error)))
        diagnostics["error_negative_count"] = int(np.sum(np.isfinite(error) & (error < 0)))
    else:
        diagnostics["error_nan_count"] = None
        diagnostics["error_negative_count"] = None

    if diagnostics["finite_q_count"] == 0 or diagnostics["finite_intensity_count"] == 0:
        messages.append("q 或 I(q) 没有可用数值点。")
        messages.append(f"finite_q_count={diagnostics['finite_q_count']}, finite_intensity_count={diagnostics['finite_intensity_count']}")
        status = "error"
    else:
        if diagnostics["q_nan_count"] or diagnostics["intensity_nan_count"]:
            messages.append("Warning：q 或 I(q) 中存在 NaN/非数值，绘图或分析会过滤这些点。")
        if diagnostics["q_duplicate_count"]:
            messages.append("Warning：存在重复 q，部分分析或矩阵导出可能受影响。")
        if not diagnostics["q_strictly_increasing"]:
            messages.append("Warning：q 不是严格递增；软件会在需要时使用排序副本。")
        if diagnostics["q_non_positive_count"]:
            messages.append("Warning：存在 q <= 0，log 图、Guinier、log-q contribution 等会排除这些点。")
        if diagnostics["intensity_non_positive_count"]:
            messages.append("Warning：存在 I(q) <= 0，log 图和 log-based 分析会排除这些点。")
        if error is not None and (diagnostics["error_nan_count"] or diagnostics["error_negative_count"]):
            messages.append("Warning：error/sigma 列存在 NaN 或负值，误差棒或加权拟合可能被禁用。")
        status = "warning" if any(message.startswith("Warning") for message in messages) else "ok"

    if status == "ok":
        messages.insert(0, "OK：当前列映射下可导入。")
    elif status == "warning":
        messages.insert(0, "Warning：当前列映射下可导入，但后续绘图/分析可能受影响。")

    return ImportPreview(
        path=str(file_path),
        status=status,
        columns=columns,
        preview_rows=preview_rows,
        row_count=int(len(df)),
        q_column=q_column,
        intensity_column=intensity_column,
        error_column=error_column,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        diagnostics=diagnostics,
        messages=messages,
    )


def format_import_preview(preview: ImportPreview) -> str:
    lines = [
        f"文件: {preview.path}",
        f"状态: {preview.status.upper()}",
        f"行数: {preview.row_count}",
        f"列: {', '.join(preview.columns) if preview.columns else '无'}",
        "",
        "列映射:",
        f"- q: {preview.q_column or '未识别'}",
        f"- I(q): {preview.intensity_column or '未识别'}",
        f"- error/sigma: {preview.error_column or 'None'}",
        f"- q unit: {preview.q_unit or '未知'}",
        f"- intensity unit: {preview.intensity_unit or '未知'}",
        "",
        "诊断:",
    ]
    for key, value in preview.diagnostics.items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "前几行:"])
    if preview.preview_rows:
        for index, row in enumerate(preview.preview_rows, start=1):
            lines.append(f"{index}. {row}")
    else:
        lines.append("- 无")
    lines.extend(["", "消息:"])
    lines.extend(f"- {message}" for message in preview.messages)
    return "\n".join(lines)
