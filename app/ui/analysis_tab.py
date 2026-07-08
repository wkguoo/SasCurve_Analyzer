from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget

from app.core.analysis_preflight import check_analysis_preflight, format_analysis_preflight
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
        layout.addLayout(controls)
        layout.addWidget(self.output, 1)

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
