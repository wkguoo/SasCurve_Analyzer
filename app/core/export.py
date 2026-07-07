from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.array_utils import sort_arrays_by_q
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

ORIGIN_LONG_COLUMNS = ["series_id", "frame_index", "sequence_order", "curve_id", "curve_name", "source_stem", "q", "I", "error", "q_unit", "intensity_unit"]
ORIGIN_LONG_COLUMN_GUIDE = [
    (
        "series_id",
        "样品或批次序列标识",
        "用于把同一组原位、批量或时间序列曲线归为一组。来自文件名解析；为空时通常表示单条曲线或未识别批次。",
        "在 Origin 中可作为分组列，用来按样品、实验批次或处理条件筛选曲线。",
    ),
    (
        "frame_index",
        "帧号或文件序号",
        "表示同一序列中的原始帧编号，通常来自文件名中的数字。",
        "做原位/时间序列图时，可把它作为时间或过程进程的替代坐标；也可用于热图的纵轴。",
    ),
    (
        "sequence_order",
        "导入后的自然排序序号",
        "表示软件按文件名自然排序后的顺序，从 0 开始；当文件名帧号不连续时仍能保留导入顺序。",
        "适合做动画、瀑布图或批量比较的稳定排序键。",
    ),
    (
        "curve_id",
        "软件内部曲线 ID",
        "用于追踪项目中的唯一曲线对象，不依赖曲线显示名。",
        "一般不作为物理分析变量；用于回溯数据来源、排查重复命名或关联项目记录。",
    ),
    (
        "curve_name",
        "曲线显示名称",
        "导入后在界面中看到的曲线名，通常来自文件名。",
        "适合作为图例标签、筛选条件或 Origin 分组绘图的曲线名称。",
    ),
    (
        "source_stem",
        "源文件名去扩展名",
        "记录原始数据文件名的主体部分，帮助从导出表回到原始文件。",
        "用于审稿、复核和批量排错；当某条曲线异常时，先用它定位原始文件。",
    ),
    (
        "q",
        "散射矢量模长",
        "横坐标，单位见 q_unit。q 越小对应越大的结构尺度，q 越大对应越小的结构尺度；常用近似尺度 d = 2π/q。",
        "常作为 X 轴。log-log 图看幂律区，Guinier 图看低 q 尺度，峰位 q* 可换算特征间距 d = 2π/q*。",
    ),
    (
        "I",
        "散射强度 I(q)",
        "纵坐标，单位见 intensity_unit。它描述不同 q 尺度上的散射信号强弱。",
        "常作为 Y 轴。比较强度前确认背景扣除、厚度/透过率归一化和单位一致；log 轴只适合正强度。",
    ),
    (
        "error",
        "强度不确定度",
        "每个 I(q) 点的标准不确定度或误差估计；空值表示原始数据没有提供误差列。",
        "可在 Origin 中设置为 Y error bar，也可作为拟合权重。没有误差列时，拟合结论应更保守。",
    ),
    (
        "q_unit",
        "q 的单位",
        "常见为 A^-1 或 nm^-1。不同 q 单位会直接改变换算得到的 d、Rg 和峰间距。",
        "合并或比较曲线前必须确认 q_unit 一致；若单位不同，先做单位转换再分析。",
    ),
    (
        "intensity_unit",
        "强度单位",
        "常见为 cm^-1、a.u. 或计数强度。绝对强度和任意强度的物理含义不同。",
        "只有同一归一化和同一单位下的 I(q) 才能直接比较绝对强度、积分不变量或体积分数相关指标。",
    ),
]


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


def _metadata_sort_value(value: Any) -> tuple[int, Any]:
    if value is None:
        return (1, "")
    return (0, value)


def _origin_curve_sort_key(curve: CurveData) -> tuple:
    metadata = curve.metadata or {}
    sequence_order = metadata.get("sequence_order")
    frame_index = metadata.get("frame_index")
    return (
        str(metadata.get("series_id") or ""),
        _metadata_sort_value(sequence_order if sequence_order is not None else frame_index),
        _metadata_sort_value(frame_index),
        curve.name,
        curve.curve_id,
    )


def _origin_column_name(curve: CurveData) -> str:
    frame_label = (curve.metadata or {}).get("frame_label")
    if frame_label is not None:
        return f"frame_{frame_label}"
    return curve.name


def _curve_by_id(curves: list[CurveData]) -> dict[str, CurveData]:
    return {curve.curve_id: curve for curve in curves}


def _length_unit_for_curve(curve: CurveData | None) -> str | None:
    return None if curve is None else f"1/({curve.q_unit})"


def _invariant_unit_for_curve(curve: CurveData | None) -> str | None:
    return None if curve is None else f"({curve.q_unit})^3 {curve.intensity_unit}"


def _unique_column_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        count = seen.get(name, 0)
        unique.append(name if count == 0 else f"{name}_{count + 1}")
        seen[name] = count + 1
    return unique


def build_origin_long_table(curves: list[CurveData]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for curve in sorted(curves, key=_origin_curve_sort_key):
        metadata = curve.metadata or {}
        order = curve.q.argsort()
        error_values = [pd.NA] * curve.q.size if curve.error is None else curve.error[order]
        for q_value, intensity_value, error_value in zip(curve.q[order], curve.intensity[order], error_values):
            rows.append(
                {
                    "series_id": metadata.get("series_id"),
                    "frame_index": metadata.get("frame_index"),
                    "sequence_order": metadata.get("sequence_order"),
                    "curve_id": curve.curve_id,
                    "curve_name": curve.name,
                    "source_stem": metadata.get("source_stem"),
                    "q": float(q_value),
                    "I": float(intensity_value),
                    "error": error_value if error_value is pd.NA else float(error_value),
                    "q_unit": curve.q_unit,
                    "intensity_unit": curve.intensity_unit,
                }
            )
    return pd.DataFrame(rows, columns=ORIGIN_LONG_COLUMNS)


def origin_long_guide_path(csv_path: str | Path) -> Path:
    target = Path(csv_path)
    return target.with_name(f"{target.stem}_guide.md")


def build_origin_long_guide_markdown(csv_filename: str = "curves_long.csv") -> str:
    lines = [
        "# Origin 长表字段说明与新手分析指南",
        "",
        f"配套数据文件: `{csv_filename}`",
        "",
        "这份长表是一行一个 q-I 数据点的原始/导入曲线汇总。它适合在 Origin、Excel、Python 或其他绘图软件中做分组曲线、误差棒、瀑布图和原位序列热图。长表不会插值、平滑或改写原始曲线点；它只是把多条曲线按统一列名堆叠在一起。",
        "",
        "## 字段逐列解释",
        "",
        "| 参数 | 代表什么 | 怎么理解 | 怎么使用 |",
        "| --- | --- | --- | --- |",
    ]
    for column, meaning, interpretation, usage in ORIGIN_LONG_COLUMN_GUIDE:
        lines.append(f"| `{column}` | {meaning} | {interpretation} | {usage} |")
    lines.extend(
        [
            "",
            "## 最常用的作图方式",
            "",
            "1. 普通散射曲线: X 轴选 `q`，Y 轴选 `I`，按 `curve_name`、`frame_index` 或 `sequence_order` 分组。初看数据时建议同时看线性坐标和 log-log 坐标。",
            "2. log-log 图: X 轴和 Y 轴都取对数，用来观察幂律斜率、低 q 上翘、Porod 区和高 q 噪声。注意 `q` 和 `I` 必须为正值。",
            "3. Guinier 图: 低 q 区用 `q²` 作 X 轴、`ln(I)` 作 Y 轴。若出现近似直线，可用于估计 Rg；只应在满足 qRg 经验范围且残差合理时解释。",
            "4. 峰位/特征间距图: 找到峰位 `q*` 后，用 `d = 2π/q*` 估计实空间特征间距。峰位移动通常表示平均距离变化，峰变宽通常表示有序度或尺寸分布变化。",
            "5. 原位或批量 heatmap: X 轴选 `q`，Y 轴选 `frame_index` 或 `sequence_order`，颜色选 `log10(I)` 或 `I`。这能快速看到峰位、强度和背景随过程的变化。",
            "6. 误差棒图: 若 `error` 非空，在 Origin 中把 `error` 设为 YErr。拟合时可用 `error` 作为权重；没有误差列时不要把拟合置信区间解读得过重。",
            "",
            "## 分析时先看什么",
            "",
            "1. 检查单位: 先确认 `q_unit` 和 `intensity_unit` 是否一致。A^-1 与 nm^-1 混用会让 d、Rg 和峰间距差 10 倍。",
            "2. 检查数据范围: 记录 q_min 和 q_max。SAS 只能解释被测 q 范围对应的结构尺度，低 q 缺失会影响大尺度结构判断，高 q 缺失会影响界面/背景判断。",
            "3. 检查正值: log-log、Guinier、Porod 和很多拟合都要求 `q > 0` 且 `I > 0`。背景扣除后的负值要单独标记和解释。",
            "4. 看低 q: 低 q 上翘可能来自大颗粒、聚集、孔洞、束流挡板附近背景或多重散射，不能只凭上翘断定一个结构模型。",
            "5. 看中 q 峰: 峰位给出平均相关距离，峰强和峰宽反映有序度、对比度和分布宽度。比较峰位前先确认校准和单位。",
            "6. 看高 q: 高 q 幂律斜率可提示界面粗糙度、 Porod 行为或分形特征，但需要足够宽且稳定的 q 区间。",
            "7. 看序列趋势: 对批量/原位数据，优先画 `frame_index` 或 `sequence_order` 对峰位、峰强、积分面积、Rg 或斜率的趋势图。",
            "",
            "## Origin 操作建议",
            "",
            "1. 导入 CSV 后，把 `q` 设置为 X，把 `I` 设置为 Y，把 `error` 设置为 YErr。`curve_name`、`frame_index` 和 `sequence_order` 保持为分组/标签列。",
            "2. 多曲线叠图时，用 `curve_name` 或 `frame_index` 分组；原位数据建议按 `sequence_order` 排序，避免字符串排序把 10 排到 2 前面。",
            "3. 做 heatmap 前，若每条曲线 q 网格一致，可优先使用 `curves_matrix.csv`；若 q 网格不一致，使用长表并显式选择插值方法，记录插值参数。",
            "4. 导出论文图前，标注坐标单位，例如 q (A^-1) 和 I(q) (cm^-1)，并说明是否做过背景扣除、归一化、平滑或插值。",
            "",
            "## 解释边界",
            "",
            "- 长表保留导入曲线点，不自动做背景扣除、绝对强度校准、平滑、插值或模型拟合。",
            "- 任何 Rg、粒径、层间距、分形维数或体积分数解释都依赖模型假设、q 范围、样品状态和误差质量。",
            "- `error` 为空不代表没有误差，只代表导入文件没有提供逐点误差列。",
            "- 对不同批次或不同仪器数据做定量比较前，必须确认单位、校准、厚度/浓度归一化和背景处理一致。",
            "",
        ]
    )
    return "\n".join(lines)


def export_origin_long_guide_markdown(path: str | Path, *, csv_filename: str = "curves_long.csv") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_origin_long_guide_markdown(csv_filename), encoding="utf-8")
    return target


def export_origin_long_csv(curves: list[CurveData], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    build_origin_long_table(curves).to_csv(target, index=False)
    export_origin_long_guide_markdown(origin_long_guide_path(target), csv_filename=target.name)
    return target


def _q_grids_match(curves: list[CurveData]) -> bool:
    if not curves:
        return True
    reference = sort_arrays_by_q(curves[0].q)[0]
    return all(curve.q.shape == reference.shape and np.allclose(sort_arrays_by_q(curve.q)[0], reference) for curve in curves[1:])


def export_origin_matrix_csv(curves: list[CurveData], path: str | Path) -> tuple[Path | None, list[str]]:
    ordered_curves = sorted(curves, key=_origin_curve_sort_key)
    target = Path(path)
    if not _q_grids_match(ordered_curves):
        return None, ["Origin matrix export skipped because q grids differ; export the long table or align/interpolate q grids explicitly first."]

    target.parent.mkdir(parents=True, exist_ok=True)
    if not ordered_curves:
        pd.DataFrame({"q": []}).to_csv(target, index=False)
        return target, []

    column_names = _unique_column_names([_origin_column_name(curve) for curve in ordered_curves])
    data: dict[str, Any] = {"q": sort_arrays_by_q(ordered_curves[0].q)[0]}
    for column_name, curve in zip(column_names, ordered_curves):
        _q, intensity = sort_arrays_by_q(curve.q, curve.intensity)
        data[column_name] = intensity
    pd.DataFrame(data).to_csv(target, index=False)
    return target, []


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
            "q_unit": curve.q_unit,
            "intensity_unit": curve.intensity_unit,
            "length_unit": _length_unit_for_curve(curve),
            "Q_unit": _invariant_unit_for_curve(curve),
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


def _analysis_summary_rows(analyses: list[AnalysisResult], curves: list[CurveData] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    curves_by_id = _curve_by_id(curves or [])
    for result in analyses:
        curve = curves_by_id.get(result.curve_id)
        row = {
            "analysis_id": result.analysis_id,
            "curve_id": result.curve_id,
            "curve_name": None if curve is None else curve.name,
            "analysis_type": result.analysis_type,
            "q_min": result.q_range[0],
            "q_max": result.q_range[1],
            "q_unit": None if curve is None else curve.q_unit,
            "intensity_unit": None if curve is None else curve.intensity_unit,
            "length_unit": _length_unit_for_curve(curve),
            "Q_unit": _invariant_unit_for_curve(curve),
            "parameters_json": json.dumps(result.parameters, ensure_ascii=False, default=_json_default),
            "warnings": " | ".join(result.warnings),
        }
        row.update(scalar_result_items(result.results))
        row["assumptions"] = " | ".join(result.results.get("assumptions", []))
        row["interpretation_limits"] = " | ".join(result.results.get("interpretation_limits", []))
        rows.append(row)
    return rows


def _fit_parameter_rows(analyses: list[AnalysisResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in analyses:
        parameters = result.results.get("parameters")
        if not isinstance(parameters, dict):
            continue
        for name, payload in parameters.items():
            if not isinstance(payload, dict) or "value" not in payload:
                continue
            ci95 = payload.get("ci95")
            row = {
                "analysis_id": result.analysis_id,
                "curve_id": result.curve_id,
                "analysis_type": result.analysis_type,
                "parameter": name,
                "value": payload.get("value"),
                "stderr": payload.get("stderr"),
                "ci95_low": ci95[0] if isinstance(ci95, list) and len(ci95) == 2 else None,
                "ci95_high": ci95[1] if isinstance(ci95, list) and len(ci95) == 2 else None,
                "unit": payload.get("unit"),
            }
            rows.append(row)
    return rows


FIT_PARAMETER_COLUMNS = ["analysis_id", "curve_id", "analysis_type", "parameter", "value", "stderr", "ci95_low", "ci95_high", "unit"]


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
    pd.DataFrame(_analysis_summary_rows(analyses, curves)).to_csv(summary_csv, index=False)
    outputs["analysis_summary"] = summary_csv

    feature_csv = export_feature_table(curves, analyses, target / "feature_table.csv")
    outputs["feature_table"] = feature_csv

    fit_parameters_csv = target / "fit_parameters.csv"
    pd.DataFrame(_fit_parameter_rows(analyses), columns=FIT_PARAMETER_COLUMNS).to_csv(fit_parameters_csv, index=False)
    outputs["fit_parameters"] = fit_parameters_csv

    curves_long_csv = export_origin_long_csv(curves, target / "curves_long.csv")
    outputs["curves_long"] = curves_long_csv
    outputs["curves_long_guide"] = origin_long_guide_path(curves_long_csv)

    curves_matrix_csv, _matrix_warnings = export_origin_matrix_csv(curves, target / "curves_matrix.csv")
    if curves_matrix_csv is not None:
        outputs["curves_matrix"] = curves_matrix_csv
    if _matrix_warnings:
        warning_path = target / "bundle_warnings.txt"
        warning_path.write_text("\n".join(_matrix_warnings) + "\n", encoding="utf-8")
        outputs["bundle_warnings"] = warning_path

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

