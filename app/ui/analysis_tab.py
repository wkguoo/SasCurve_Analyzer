from __future__ import annotations

import math

import numpy as np
from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.core.analysis_preflight import check_analysis_preflight, format_analysis_preflight
from app.core.auto_regions import AutoRegionCandidate, detect_auto_regions, region_type_label, run_analysis_for_region
from app.core.export import export_auto_region_candidates_csv
from app.core.method_mapping import plot_for_analysis
from app.core.plot_analysis import analyze_curve_plot
from app.core.plotting import display_x_limits_to_q_range_for_curve, transform_x_for_plot
from app.core.records import create_history_record
from app.core.user_messages import exception_detail, format_user_message, UserMessage
from app.ui.style import action_button, apply_help


ANALYSIS_TYPE_ITEMS = [
    ("线性强度诊断: I(q) vs q", "linear"),
    ("半对数诊断: ln I(q) vs q", "semilog"),
    ("Power-law 拟合: ln I(q) vs ln q", "loglog"),
    ("Guinier 拟合: ln I(q) vs q\u00b2", "guinier"),
    ("Kratky 指标: q\u00b2I(q) vs q", "kratky"),
    ("Porod 指标: q\u2074I(q) vs q", "porod"),
    ("Invariant 有限积分: \u222bq\u00b2I(q)dq", "invariant"),
    ("局部斜率: \u03b1(q)", "local_slope"),
]

PREFLIGHT_ANALYSIS_TYPES = {
    "linear": "linear",
    "semilog": "semilog",
    "loglog": "loglog",
    "guinier": "guinier",
    "kratky": "kratky",
    "porod": "porod",
    "invariant": "invariant",
    "local_slope": "local_slope",
}


class AnalysisTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.range_source = "manual raw q input"

        self.title_label = QLabel("曲线分析")
        self.title_label.setObjectName("curveAnalysisTitle")
        self.analysis_type = QComboBox()
        for label, key in ANALYSIS_TYPE_ITEMS:
            self.analysis_type.addItem(label, key)
        apply_help(
            self.analysis_type,
            tooltip="选择当前曲线图对应的分析输出。",
            status_tip="八种主图对应八类诊断、拟合或积分；log 类分析会过滤数学定义域无效点但不会给数据加常数。",
        )

        self.q_min = QDoubleSpinBox()
        self.q_min.setDecimals(6)
        self.q_min.setRange(0.0, 1_000_000.0)
        self.q_max = QDoubleSpinBox()
        self.q_max.setDecimals(6)
        self.q_max.setRange(0.0, 1_000_000.0)
        self.q_max.setValue(1.0)
        self.q_min.valueChanged.connect(lambda _value: self._set_manual_range_source())
        self.q_max.valueChanged.connect(lambda _value: self._set_manual_range_source())
        apply_help(self.q_min, tooltip="分析 q 下限。", status_tip="输入本次分析使用的 raw q 最小值。")
        apply_help(self.q_max, tooltip="分析 q 上限。", status_tip="输入本次分析使用的 raw q 最大值。")

        run_button = action_button(
            "运行曲线分析",
            role="primary",
            tooltip="运行当前 plot type 对应的分析。",
            status_tip="结果会写入 ProjectState.analysis_results、history 和后续导出表。",
        )
        run_button.clicked.connect(self.run_analysis)
        fill_button = action_button("使用当前曲线 q 范围", role="secondary", tooltip="填入当前曲线完整 raw q 范围。")
        fill_button.clicked.connect(self.fill_current_range)
        preflight_button = action_button(
            "检查当前 q 范围",
            role="secondary",
            tooltip="运行分析前预检当前 raw q 范围。",
            status_tip="检查点数、非有限值、log 可用点、非正 q/强度；不会自动选择最佳区间。",
        )
        preflight_button.clicked.connect(self.check_current_range)
        plot_range_button = action_button(
            "使用曲线绘图区域 x 范围换算为 q",
            role="secondary",
            tooltip="读取曲线绘图区域当前横坐标范围并转换为 raw q。",
            status_tip="适用于 ln q 或 q² 等变换坐标；最终写入 q_min/q_max 的仍是 raw q 范围。",
        )
        plot_range_button.clicked.connect(self.fill_range_from_plot_x_limits)
        linked_plot_button = action_button(
            "查看对应图",
            role="secondary",
            tooltip="切换到当前分析方法对应的绘图类型。",
        )
        linked_plot_button.clicked.connect(self.show_linked_plot)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.auto_region_candidates: list[AutoRegionCandidate] = []
        self.auto_region_detection_result = None
        self._auto_region_filled_candidate_id: str | None = None
        self._auto_region_filled_q_range: tuple[float, float] | None = None
        self.auto_region_group = self._build_auto_region_group()

        form = QFormLayout()
        form.addRow("分析类型", self.analysis_type)
        form.addRow("q_min", self.q_min)
        form.addRow("q_max", self.q_max)

        controls = QHBoxLayout()
        controls.addWidget(fill_button)
        controls.addWidget(preflight_button)
        controls.addWidget(plot_range_button)
        controls.addWidget(linked_plot_button)
        controls.addWidget(run_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addLayout(form)
        layout.addWidget(self.auto_region_group)
        layout.addLayout(controls)
        layout.addWidget(self.output, 1)

    def _build_auto_region_group(self) -> QGroupBox:
        group = QGroupBox("自动识别 q 区间")
        detect_button = action_button(
            "识别区间",
            role="secondary",
            tooltip="基于当前曲线和 raw q 范围生成候选分析区间。",
            status_tip="自动识别只生成候选区，不做结构判定；结果会写入项目历史记录。",
        )
        detect_button.clicked.connect(self.detect_auto_regions_for_current_curve)
        fill_full_range_button = action_button("使用当前曲线完整 q 范围", role="secondary", tooltip="先填入当前曲线完整 raw q 范围。")
        fill_full_range_button.clicked.connect(self.fill_current_range)
        fill_region_button = action_button("将该区间填入 q_min/q_max", role="secondary", tooltip="把当前选中候选区的 raw q 范围填入分析输入框。")
        fill_region_button.clicked.connect(self.fill_selected_auto_region_range)
        run_region_button = action_button("使用该区间拟合/计算", role="primary", tooltip="基于当前选中候选区运行推荐分析。")
        run_region_button.clicked.connect(self.run_selected_auto_region_analysis)
        export_region_button = action_button("导出候选区表", role="secondary", tooltip="把当前候选区列表导出为独立 CSV。")
        export_region_button.clicked.connect(self.export_auto_region_candidates)

        self.auto_region_table = QTableWidget(0, 8)
        self.auto_region_table.setHorizontalHeaderLabels(["类型", "q 范围", "d 范围", "点数", "评分", "等级", "推荐操作", "警告"])
        self.auto_region_table.setAlternatingRowColors(True)
        self.auto_region_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.auto_region_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.auto_region_table.itemSelectionChanged.connect(self._refresh_auto_region_detail)

        self.auto_region_detail = QTextEdit()
        self.auto_region_detail.setReadOnly(True)
        self.auto_region_detail.setMaximumHeight(120)

        button_row = QHBoxLayout()
        button_row.addWidget(fill_full_range_button)
        button_row.addWidget(detect_button)
        button_row.addWidget(fill_region_button)
        button_row.addWidget(run_region_button)
        button_row.addWidget(export_region_button)
        button_row.addStretch(1)

        layout = QVBoxLayout(group)
        layout.addLayout(button_row)
        layout.addWidget(self.auto_region_table)
        layout.addWidget(self.auto_region_detail)
        return group

    def _current_raw_q_range(self) -> tuple[float, float]:
        return (float(self.q_min.value()), float(self.q_max.value()))

    def _finite_curve_q_range(self, curve) -> tuple[float, float] | None:
        finite_q = curve.q[np.isfinite(curve.q)]
        if finite_q.size == 0:
            return None
        return (float(np.nanmin(finite_q)), float(np.nanmax(finite_q)))

    def _set_q_range_without_marking_manual(self, q_range: tuple[float, float], *, range_source: str) -> None:
        self.q_min.blockSignals(True)
        self.q_max.blockSignals(True)
        try:
            self.q_min.setValue(float(q_range[0]))
            self.q_max.setValue(float(q_range[1]))
        finally:
            self.q_min.blockSignals(False)
            self.q_max.blockSignals(False)
        self.range_source = range_source

    def _q_range_for_auto_region_detection(self, curve) -> tuple[tuple[float, float] | None, list[str]]:
        full_range = self._finite_curve_q_range(curve)
        if full_range is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Auto q-region detection cannot run",
                        what_happened="Curve has no finite q data.",
                        facts=(f"curve: {curve.name}",),
                        severity="warning",
                    )
                )
            )
            return None, []

        raw_q_range = self._current_raw_q_range()
        messages: list[str] = []
        default_initial_range = (
            self.range_source == "manual raw q input"
            and math.isclose(raw_q_range[0], 0.0, rel_tol=0.0, abs_tol=1e-12)
            and math.isclose(raw_q_range[1], 1.0, rel_tol=0.0, abs_tol=1e-12)
        )
        if default_initial_range:
            self._set_q_range_without_marking_manual(full_range, range_source="current curve raw q range for auto detection")
            messages.append("完整 raw q 范围: 已自动使用当前曲线完整 raw q 范围，避免默认 0-1 截断自动识别。")
            return full_range, messages

        if raw_q_range[0] >= raw_q_range[1]:
            self._set_q_range_without_marking_manual(full_range, range_source="current curve raw q range after invalid manual range")
            messages.append("自动改用当前曲线完整 raw q 范围: 手工 q_min/q_max 范围无效。")
            return full_range, messages

        q_start, q_end = raw_q_range
        curve_q_min, curve_q_max = full_range
        if q_end < curve_q_min or q_start > curve_q_max:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Auto q-region detection cannot run",
                        what_happened="没有与当前曲线 q 范围重叠: manual q range has no overlap with curve.",
                        facts=(
                            f"manual raw q range: [{q_start:.6g}, {q_end:.6g}]",
                            f"curve raw q range: [{curve_q_min:.6g}, {curve_q_max:.6g}]",
                        ),
                        severity="warning",
                    )
                )
            )
            return None, []

        return raw_q_range, messages

    def detect_auto_regions_for_current_curve(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="自动 q 区域识别无法运行",
                        what_happened="当前没有选中的曲线。",
                        facts=("MainWindow.current_curve() 返回 None。", "请先导入并选中一条 SAS 曲线。"),
                        severity="warning",
                    )
                )
            )
            return
        try:
            q_range, range_messages = self._q_range_for_auto_region_detection(curve)
            if q_range is None:
                return
            result = detect_auto_regions(curve, q_range)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="自动 q 区域识别失败",
                        what_happened="候选区间生成器没有返回可用结果。",
                        facts=(f"curve: {curve.name}", f"raw q range: [{self.q_min.value():.6g}, {self.q_max.value():.6g}]"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return

        self.auto_region_detection_result = result
        self.auto_region_candidates = [AutoRegionCandidate.from_dict(row) for row in result.results.get("candidates", [])]
        self._populate_auto_region_table()
        self.main_window.project.add_analysis_result(result)
        self.main_window.project.add_history_record(
            create_history_record(
                "auto_region_detection",
                input_ids=[curve.curve_id],
                output_ids=[result.analysis_id],
                parameters={"q_range": result.q_range, "candidate_count": len(self.auto_region_candidates)},
                warnings=result.warnings,
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        prefix = ("\n".join(range_messages) + "\n\n") if range_messages else ""
        if self.auto_region_candidates:
            self.output.setPlainText(prefix + self._format_result(result))
        else:
            self.output.setPlainText(
                prefix
                +
                format_user_message(
                    UserMessage(
                        title="自动 q 区域识别未找到候选区",
                        what_happened="自动 q 区域识别未找到满足最低置信度要求的候选区间。",
                        facts=tuple(result.results.get("detection_warnings") or ["没有候选区。"]),
                        severity="warning",
                    )
                )
            )

    def _format_float(self, value: float | None) -> str:
        if value is None:
            return "-"
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return "-"
        if not math.isfinite(parsed):
            return "-"
        return f"{parsed:.6g}"

    def _populate_auto_region_table(self) -> None:
        self.auto_region_table.setRowCount(len(self.auto_region_candidates))
        for row, candidate in enumerate(self.auto_region_candidates):
            d_values = [value for value in (candidate.d_start, candidate.d_end) if value is not None]
            d_range = "-" if not d_values else f"{self._format_float(min(d_values))} - {self._format_float(max(d_values))}"
            values = [
                region_type_label(candidate.region_type),
                f"{self._format_float(candidate.q_start)} - {self._format_float(candidate.q_end)}",
                d_range,
                str(candidate.n_points),
                self._format_float(candidate.score),
                candidate.confidence_label,
                candidate.recommended_analysis or "人工复核",
                " | ".join(candidate.warnings[:2]) if candidate.warnings else "-",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.auto_region_table.setItem(row, column, item)
        if self.auto_region_candidates:
            self.auto_region_table.selectRow(0)
        self.auto_region_table.resizeColumnsToContents()
        self._refresh_auto_region_detail()

    def _selected_auto_region(self) -> AutoRegionCandidate | None:
        row = self.auto_region_table.currentRow()
        if row < 0 or row >= len(self.auto_region_candidates):
            return None
        return self.auto_region_candidates[row]

    def _refresh_auto_region_detail(self) -> None:
        candidate = self._selected_auto_region()
        if candidate is None:
            self.auto_region_detail.setPlainText("尚未选择自动候选区。")
            return
        metric_lines = []
        for key, value in candidate.metrics.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                metric_lines.append(f"- {key}: {value}")
        warning_lines = [f"- {warning}" for warning in candidate.warnings] or ["- 无"]
        self.auto_region_detail.setPlainText(
            "\n".join(
                [
                    f"region_id: {candidate.region_id}",
                    f"类型: {region_type_label(candidate.region_type)}",
                    f"检测方法: {candidate.detection_method}",
                    f"raw q: {self._format_float(candidate.q_start)} - {self._format_float(candidate.q_end)}",
                    f"推荐分析: {candidate.recommended_analysis or '人工复核'}",
                    "关键指标:",
                    *(metric_lines[:8] or ["- 无"]),
                    "warnings:",
                    *warning_lines,
                ]
            )
        )

    def fill_selected_auto_region_range(self) -> None:
        candidate = self._selected_auto_region()
        if candidate is None:
            self.output.setPlainText("尚未选择自动候选区，无法填入 q_min/q_max。")
            return
        self.q_min.setValue(candidate.q_start)
        self.q_max.setValue(candidate.q_end)
        self.range_source = f"auto detected q range ({candidate.region_id})"
        self._auto_region_filled_candidate_id = candidate.region_id
        self._auto_region_filled_q_range = (candidate.q_start, candidate.q_end)
        self.output.setPlainText(f"已填入候选区 raw q 范围: {candidate.q_start:.6g} - {candidate.q_end:.6g}")

    def run_selected_auto_region_analysis(self) -> None:
        curve = self.main_window.current_curve()
        candidate = self._selected_auto_region()
        if curve is None or candidate is None:
            self.output.setPlainText("当前没有可用于一键拟合/计算的曲线或候选区。")
            return
        current_q_range = (
            self._auto_region_filled_q_range
            if self._auto_region_filled_candidate_id == candidate.region_id and self._auto_region_filled_q_range is not None
            else self._current_raw_q_range()
        )
        user_override = None
        if self._auto_region_filled_candidate_id != candidate.region_id and not (
            math.isclose(current_q_range[0], candidate.q_start, rel_tol=1e-9, abs_tol=1e-12)
            and math.isclose(current_q_range[1], candidate.q_end, rel_tol=1e-9, abs_tol=1e-12)
        ):
            user_override = current_q_range
        try:
            result = run_analysis_for_region(curve, candidate, user_overridden_q_range=user_override)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="自动候选区一键分析失败",
                        what_happened="候选区已经选中，但推荐分析函数执行失败。",
                        facts=(f"candidate: {candidate.region_id}", f"region_type: {candidate.region_type}"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_analysis_result(result)
        self.main_window.project.add_history_record(
            create_history_record(
                "auto_region_analysis",
                input_ids=[curve.curve_id, candidate.region_id],
                output_ids=[result.analysis_id],
                parameters={
                    "source": "auto_region",
                    "auto_region_id": candidate.region_id,
                    "region_type": candidate.region_type,
                    "original_q_range": (candidate.q_start, candidate.q_end),
                    "final_q_range": result.q_range,
                    "score": candidate.score,
                    "confidence_label": candidate.confidence_label,
                    "recommended_analysis": candidate.recommended_analysis,
                    "user_overrode_range": user_override is not None,
                    "force": False,
                },
                warnings=result.warnings,
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(self._format_result(result))

    def export_auto_region_candidates(self) -> None:
        if not self.auto_region_candidates:
            self.output.setPlainText("当前没有可导出的自动候选区。")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(self, "导出自动 q 候选区 CSV", "auto_region_candidates.csv", "CSV Files (*.csv)")
        if not path:
            return
        try:
            output_path = export_auto_region_candidates_csv(self.auto_region_candidates, path)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="自动 q 候选区导出失败",
                        what_happened="候选区表没有写入所选 CSV 文件。",
                        facts=(f"target: {path}", f"candidate_count: {len(self.auto_region_candidates)}"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.output.setPlainText(f"已导出自动 q 候选区表: {output_path}")

    def set_plot_type_from_plot(self, plot_type: str) -> None:
        index = self.analysis_type.findData(plot_type)
        if index >= 0 and self.analysis_type.currentIndex() != index:
            self.analysis_type.setCurrentIndex(index)

    def fill_current_range(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        self.q_min.setValue(float(curve.q.min()))
        self.q_max.setValue(float(curve.q.max()))
        self.range_source = "current curve raw q range"

    def _set_manual_range_source(self) -> None:
        self.range_source = "manual raw q input"
        self._auto_region_filled_candidate_id = None
        self._auto_region_filled_q_range = None

    def fill_range_from_plot_x_limits(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="display x 范围无法换算为 raw q",
                        what_happened="当前没有选中的曲线，无法判断绘图 x 范围对应的有效 raw q 范围。",
                        facts=("MainWindow.current_curve() 返回 None。", "raw q 输入框保持当前值。"),
                        severity="warning",
                    )
                )
            )
            return
        x_limits = self.main_window.plotting_tab.current_x_limits()
        if x_limits is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="无法读取曲线绘图区域 x 范围",
                        what_happened="当前没有可用的绘图坐标轴范围。",
                        facts=("PlottingTab.current_x_limits() 返回 None。", "请先绘制当前曲线。"),
                        severity="warning",
                    )
                )
            )
            return

        plot_type = self.main_window.plotting_tab.plot_type.currentData()
        try:
            (q_min, q_max), warnings = display_x_limits_to_q_range_for_curve(curve, x_limits[0], x_limits[1], plot_type)
        except ValueError as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="display x 范围无法换算为 raw q",
                        what_happened="当前图上的横坐标范围没有成功转换成正的物理 q 范围。",
                        facts=(
                            f"plot_type: {plot_type}。",
                            f"display x range: [{x_limits[0]:.6g}, {x_limits[1]:.6g}]。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return

        self.q_min.setValue(q_min)
        self.q_max.setValue(q_max)
        self.range_source = f"converted from plotting display x ({plot_type}), clamped to valid data range"
        clipped_display = transform_x_for_plot([q_min, q_max], plot_type)
        clipped_x_min = float(min(clipped_display))
        clipped_x_max = float(max(clipped_display))
        warning_text = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- 无"
        self.output.setPlainText(
            "已将曲线绘图区域当前 display x 范围 "
            f"[{x_limits[0]:.6g}, {x_limits[1]:.6g}] ({plot_type}) "
            f"转换为 raw q 范围 [{q_min:.6g}, {q_max:.6g}]。\n"
            f"裁剪后的 display x range: [{clipped_x_min:.6g}, {clipped_x_max:.6g}]\n"
            f"warnings:\n{warning_text}"
        )

    def show_linked_plot(self) -> None:
        analysis_type = self.analysis_type.currentData()
        plot_type = plot_for_analysis(analysis_type)
        if plot_type is None:
            self.output.setPlainText("当前分析类型没有对应的绘图视图。")
            return
        self.main_window.set_plot_type(plot_type)
        self.main_window.show_plotting_tab()
        self.main_window.plotting_tab.messages.setPlainText(f"Linked from curve analysis type '{analysis_type}'.")

    def _current_preflight(self):
        analysis_type = PREFLIGHT_ANALYSIS_TYPES.get(self.analysis_type.currentData(), "invariant")
        return check_analysis_preflight(
            self.main_window.current_curve(),
            analysis_type,
            (float(self.q_min.value()), float(self.q_max.value())),
            range_source=self.range_source,
        )

    def check_current_range(self) -> None:
        self.output.setPlainText(format_analysis_preflight(self._current_preflight()))

    def run_analysis(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="无法运行曲线分析",
                        what_happened="当前没有选中的曲线。",
                        facts=("MainWindow.current_curve() 返回 None。", "曲线分析需要一条当前曲线和 raw q 范围。"),
                        severity="warning",
                    )
                )
            )
            return

        q_range = (float(self.q_min.value()), float(self.q_max.value()))
        plot_type = self.analysis_type.currentData()
        preflight = self._current_preflight()
        preflight_text = format_analysis_preflight(preflight)
        if not preflight.can_run:
            self.output.setPlainText(preflight_text)
            return
        try:
            result = analyze_curve_plot(curve, plot_type, q_range)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="曲线分析失败",
                        what_happened="预检允许继续，但八图分析核心没有返回有效结果。",
                        facts=(
                            f"plot_type: {plot_type}。",
                            f"raw q range: [{q_range[0]:.6g}, {q_range[1]:.6g}]。",
                            f"preflight severity: {preflight.severity}。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return

        self.main_window.project.add_analysis_result(result)
        self.main_window.project.add_history_record(
            create_history_record(
                f"plot_analysis:{plot_type}",
                input_ids=[curve.curve_id],
                output_ids=[result.analysis_id],
                parameters={"plot_type": plot_type, "q_range": q_range},
                warnings=result.warnings,
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(preflight_text + "\n\n" + self._format_result(result))

    def refresh_results(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        self.set_plot_type_from_plot(self.main_window.plotting_tab.plot_type.currentData())
        results = self.main_window.project.get_results_for_curve(curve.curve_id)
        if not results:
            self.output.setPlainText("当前曲线尚无分析结果。")
            return
        self.output.setPlainText("\n\n".join(self._format_result(result) for result in results))

    def _format_result(self, result) -> str:
        lines = [
            f"analysis_id: {result.analysis_id}",
            f"analysis_type: {result.analysis_type}",
            f"plot_type: {result.results.get('plot_type')}",
            f"q_range: {result.q_range}",
            "",
            "results:",
        ]
        for key, value in result.results.items():
            if key == "export_tables":
                table_counts = {name: len(rows) if hasattr(rows, "__len__") else 1 for name, rows in value.items()}
                lines.append(f"- export_tables: {table_counts}")
            elif isinstance(value, list):
                lines.append(f"- {key}: list[{len(value)}]")
            elif isinstance(value, dict):
                scalar_items = {
                    item_key: item_value
                    for item_key, item_value in value.items()
                    if isinstance(item_value, (str, int, float, bool)) or item_value is None
                }
                lines.append(f"- {key}: {scalar_items if scalar_items else 'dict'}")
            else:
                lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("warnings:")
        if getattr(result, "structured_warnings", None):
            for warning in result.structured_warnings:
                lines.append(f"- {warning.get('warning_code')} [{warning.get('severity')}]: {warning.get('message')}")
        elif result.warnings:
            lines.extend(f"- {warning}" for warning in result.warnings)
        else:
            lines.append("- 无")
        return "\n".join(lines)
