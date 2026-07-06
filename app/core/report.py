from __future__ import annotations

from pathlib import Path

from app.core.analysis_schema import scalar_result_items
from app.core.data_model import AnalysisResult, CurveData, FormalRecord, HistoryRecord, utc_now_iso


def generate_markdown_report(
    path: str | Path,
    *,
    project_name: str,
    curves: list[CurveData],
    analyses: list[AnalysisResult],
    history: list[HistoryRecord],
    formal_records: list[FormalRecord],
    figure_paths: list[str] | None = None,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {project_name}",
        "",
        f"- Export time: {utc_now_iso()}",
        "- Software version: 0.1.0",
        "",
        "## Curves",
    ]
    for curve in curves:
        lines.extend(
            [
                f"### {curve.name}",
                f"- curve_id: `{curve.curve_id}`",
                f"- source_file: `{curve.source_file}`",
                f"- q range: {float(curve.q.min())} to {float(curve.q.max())} {curve.q_unit}",
                f"- points: {curve.q.size}",
                "",
            ]
        )

    lines.append("## Analysis Results")
    for result in analyses:
        lines.extend([f"### {result.analysis_type}", f"- analysis_id: `{result.analysis_id}`", f"- curve_id: `{result.curve_id}`", f"- q_range: {result.q_range}", "- key results:"])
        for key, value in scalar_result_items(result.results).items():
            lines.append(f"  - {key}: {value}")
        assumptions = result.results.get("assumptions", [])
        if assumptions:
            lines.append("- assumptions / 前提条件:")
            for assumption in assumptions:
                lines.append(f"  - {assumption}")
        limits = result.results.get("interpretation_limits", [])
        if limits:
            lines.append("- interpretation limits / 解释边界:")
            for limit in limits:
                lines.append(f"  - {limit}")
        export_tables = result.results.get("export_tables", {})
        if export_tables:
            lines.append("- export tables / 可展开导出表:")
            for table_name, rows in export_tables.items():
                count = len(rows) if hasattr(rows, "__len__") else 1
                lines.append(f"  - {table_name}: {count} rows")
        if result.warnings:
            lines.append("- warnings:")
            for warning in result.warnings:
                lines.append(f"  - {warning}")
        if result.structured_warnings:
            lines.append("- structured warnings:")
            for warning in result.structured_warnings:
                lines.append(f"  - {warning.get('warning_code')}: {warning.get('message')}")
        lines.append("")

    lines.append("## Processing History")
    for record in history:
        lines.append(f"- {record.timestamp}: {record.action_type} input={record.input_ids} output={record.output_ids}")
    lines.append("")

    lines.append("## Formal Records")
    for record in formal_records:
        lines.append(f"- {record.title}: {record.source_type} `{record.source_id}`")
    lines.append("")

    lines.append("## Figures")
    for figure_path in figure_paths or []:
        lines.append(f"- `{figure_path}`")
    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target

