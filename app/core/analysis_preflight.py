from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.core.data_model import CurveData


LOG_INTENSITY_ANALYSES = {"guinier", "power_law", "local_slope"}
POSITIVE_Q_ANALYSES = {"guinier", "power_law", "local_slope", "information_budget", "kratky_metrics", "porod_metrics"}
MIN_POINTS = {
    "guinier": 3,
    "power_law": 3,
    "local_slope": 4,
    "peak_detection": 3,
    "invariant": 2,
    "information_budget": 2,
    "kratky_metrics": 2,
    "porod_metrics": 2,
}


@dataclass(frozen=True)
class AnalysisPreflight:
    analysis_type: str
    q_range: tuple[float, float]
    total_points: int
    points_in_range: int
    finite_points_in_range: int
    positive_q_points: int
    positive_intensity_points: int
    log_usable_points: int
    excluded_points: int
    severity: str
    messages: list[str] = field(default_factory=list)
    range_source: str = "manual raw q input"

    @property
    def can_run(self) -> bool:
        return self.severity in {"ok", "warning"}


def check_analysis_preflight(
    curve: CurveData | None,
    analysis_type: str,
    q_range: tuple[float, float],
    *,
    range_source: str = "manual raw q input",
) -> AnalysisPreflight:
    q_min, q_max = float(q_range[0]), float(q_range[1])
    if curve is None:
        return AnalysisPreflight(
            analysis_type=analysis_type,
            q_range=(q_min, q_max),
            total_points=0,
            points_in_range=0,
            finite_points_in_range=0,
            positive_q_points=0,
            positive_intensity_points=0,
            log_usable_points=0,
            excluded_points=0,
            severity="error",
            messages=["当前没有选中的曲线。"],
            range_source=range_source,
        )

    q = np.asarray(curve.q, dtype=float)
    intensity = np.asarray(curve.intensity, dtype=float)
    total_points = int(q.size)
    messages: list[str] = []

    if not np.isfinite(q_min) or not np.isfinite(q_max):
        messages.append("q_min/q_max 必须是有限数值。")
        severity = "error"
        return _result(analysis_type, (q_min, q_max), total_points, severity, messages, range_source)

    if q_min < 0 or q_max < 0:
        messages.append("raw q 范围不能为负。")
        messages.append("ln q 或 q² 是 display x 坐标；分析接口只接收 raw q。")
        severity = "error"
        return _result(analysis_type, (q_min, q_max), total_points, severity, messages, range_source)

    if q_min >= q_max:
        messages.append("q_min 必须小于 q_max。")
        severity = "error"
        return _result(analysis_type, (q_min, q_max), total_points, severity, messages, range_source)

    in_range = (q >= q_min) & (q <= q_max)
    finite = in_range & np.isfinite(q) & np.isfinite(intensity)
    positive_q = finite & (q > 0)
    positive_i = finite & (intensity > 0)
    log_usable = finite & (q > 0) & (intensity > 0)

    points_in_range = int(np.sum(in_range))
    finite_points = int(np.sum(finite))
    positive_q_points = int(np.sum(positive_q))
    positive_i_points = int(np.sum(positive_i))
    log_usable_points = int(np.sum(log_usable))
    excluded_points = points_in_range - finite_points
    min_points = MIN_POINTS.get(analysis_type, 2)
    severity = "ok"

    if points_in_range == 0:
        messages.append("当前 q 范围内没有数据点。")
        severity = "error"
    elif finite_points < min_points:
        messages.append(f"当前 q 范围内有限数值点不足：需要至少 {min_points} 个，当前 {finite_points} 个。")
        severity = "error"

    if analysis_type in LOG_INTENSITY_ANALYSES and log_usable_points < min_points:
        messages.append(
            f"{analysis_type} 需要 q > 0 且 I(q) > 0 的 log 可用点；需要至少 {min_points} 个，当前 {log_usable_points} 个。"
        )
        severity = "error"
    elif analysis_type in POSITIVE_Q_ANALYSES and positive_q_points < min_points:
        messages.append(f"{analysis_type} 需要正 q 点；当前正 q 点不足。")
        severity = "error"

    if severity != "error":
        if excluded_points:
            messages.append(f"范围内有 {excluded_points} 个 NaN/非有限点会被排除。")
            severity = "warning"
        if analysis_type in LOG_INTENSITY_ANALYSES and log_usable_points < finite_points:
            filtered = finite_points - log_usable_points
            messages.append(f"log 分析会排除 {filtered} 个 q <= 0 或 I(q) <= 0 的点。")
            severity = "warning"
        if analysis_type == "peak_detection" and finite_points < 5:
            messages.append("峰识别范围内点数较少，峰宽和面积可能不稳定。")
            severity = "warning"
        if analysis_type in {"invariant", "information_budget"}:
            messages.append("当前检查只覆盖 finite q-range；不包含低 q 或高 q 外推。")
        if analysis_type in {"kratky_metrics", "porod_metrics"}:
            messages.append("当前指标是描述性指标，不自动证明构象或界面机制。")

    if not messages:
        messages.append("预检通过：当前 raw q 范围有足够可用点。")

    return AnalysisPreflight(
        analysis_type=analysis_type,
        q_range=(q_min, q_max),
        total_points=total_points,
        points_in_range=points_in_range,
        finite_points_in_range=finite_points,
        positive_q_points=positive_q_points,
        positive_intensity_points=positive_i_points,
        log_usable_points=log_usable_points,
        excluded_points=excluded_points,
        severity=severity,
        messages=messages,
        range_source=range_source,
    )


def _result(
    analysis_type: str,
    q_range: tuple[float, float],
    total_points: int,
    severity: str,
    messages: list[str],
    range_source: str,
) -> AnalysisPreflight:
    return AnalysisPreflight(
        analysis_type=analysis_type,
        q_range=q_range,
        total_points=total_points,
        points_in_range=0,
        finite_points_in_range=0,
        positive_q_points=0,
        positive_intensity_points=0,
        log_usable_points=0,
        excluded_points=0,
        severity=severity,
        messages=messages,
        range_source=range_source,
    )


def format_analysis_preflight(preflight: AnalysisPreflight) -> str:
    lines = [
        "分析前 q 范围预检",
        f"severity: {preflight.severity}",
        f"analysis_type: {preflight.analysis_type}",
        f"range_source: {preflight.range_source}",
        f"raw q_range: [{preflight.q_range[0]:.6g}, {preflight.q_range[1]:.6g}]",
        f"total_points: {preflight.total_points}",
        f"points_in_range: {preflight.points_in_range}",
        f"finite_points_in_range: {preflight.finite_points_in_range}",
        f"positive_q_points: {preflight.positive_q_points}",
        f"positive_intensity_points: {preflight.positive_intensity_points}",
        f"log_usable_points: {preflight.log_usable_points}",
        f"excluded_points: {preflight.excluded_points}",
        "",
        "messages:",
    ]
    lines.extend(f"- {message}" for message in preflight.messages)
    return "\n".join(lines)
