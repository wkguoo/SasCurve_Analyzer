from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.deep_analysis import DeepAnalysisOptions, SAMPLE_TYPES, SHAPE_MODELS, run_deep_analysis
from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, information_budget, invariant_measured, kratky_metrics, local_slope, porod_metrics, power_law_analysis
from app.core.records import create_history_record
from app.ui.style import action_button, apply_help


class AnalysisTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.analysis_type = QComboBox()
        for label, key in [
            ("Guinier analysis: ln I(q) vs q\u00b2", "guinier"),
            ("Power-law slope: ln I(q) vs ln q", "power_law"),
            ("Local slope: \u03b1(q)", "local_slope"),
            ("Peak detection: q* and d = 2\u03c0/q*", "peak_detection"),
            ("Finite invariant: \u222bq\u00b2I(q)dq", "invariant"),
            ("Information budget: q\u00b3I(q) over ln q", "information_budget"),
            ("Kratky metrics: q\u00b2I(q)", "kratky_metrics"),
            ("Porod metrics: q\u2074I(q)", "porod_metrics"),
        ]:
            self.analysis_type.addItem(label, key)
        apply_help(
            self.analysis_type,
            tooltip="选择无模型分析。",
            status_tip="选择 Guinier、幂律、局部斜率、峰识别、不变量、尺度贡献谱、Kratky 或 Porod 指标。",
        )
        self.sample_type = QComboBox()
        self.sample_type.addItems(SAMPLE_TYPES)
        apply_help(
            self.sample_type,
            tooltip="样品类型提示。",
            status_tip="用于深度分析的解释标签，帮助选择更合适的后处理参数。",
        )
        self.shape_model = QComboBox()
        self.shape_model.addItems(SHAPE_MODELS)
        apply_help(
            self.shape_model,
            tooltip="形状/模型假设。",
            status_tip="深度分析的模型假设；结果应结合样品体系和方法警告判断。",
        )

        self.q_min = QDoubleSpinBox()
        self.q_min.setDecimals(6)
        self.q_min.setRange(0.0, 1_000_000.0)
        self.q_max = QDoubleSpinBox()
        self.q_max.setDecimals(6)
        self.q_max.setRange(0.0, 1_000_000.0)
        self.q_max.setValue(1.0)
        apply_help(
            self.q_min,
            tooltip="分析 q 下限。",
            status_tip="输入本次分析使用的最小 q；不同方法对 q 范围敏感。",
        )
        apply_help(
            self.q_max,
            tooltip="分析 q 上限。",
            status_tip="输入本次分析使用的最大 q；可用当前曲线范围按钮快速填充。",
        )
        self.dmax = QDoubleSpinBox()
        self.dmax.setDecimals(3)
        self.dmax.setRange(0.001, 1_000_000.0)
        self.dmax.setValue(100.0)
        apply_help(
            self.dmax,
            tooltip="P(r) 最大尺寸。",
            status_tip="深度分析参数；Dmax 过小或过大会影响 P(r) 解释。",
        )
        self.regularization = QDoubleSpinBox()
        self.regularization.setDecimals(6)
        self.regularization.setRange(0.0, 1_000.0)
        self.regularization.setValue(0.01)
        apply_help(
            self.regularization,
            tooltip="正则化强度。",
            status_tip="深度分析参数；更高值通常更平滑，但可能抹去真实结构特征。",
        )
        self.contrast = QDoubleSpinBox()
        self.contrast.setDecimals(6)
        self.contrast.setRange(0.0, 1_000_000.0)
        apply_help(
            self.contrast,
            tooltip="散射 contrast。",
            status_tip="启用 contrast 后用于绝对强度相关估算；未知时保持未启用。",
        )
        self.volume_fraction = QDoubleSpinBox()
        self.volume_fraction.setDecimals(6)
        self.volume_fraction.setRange(0.0, 1.0)
        apply_help(
            self.volume_fraction,
            tooltip="体积分数初值。",
            status_tip="模型相关初值；不应替代独立校准或物理约束。",
        )
        self.use_contrast = QCheckBox("使用 contrast")
        apply_help(
            self.use_contrast,
            tooltip="启用 contrast 参数。",
            status_tip="只有在 contrast 可靠时启用，否则相关绝对量可能误导。",
        )
        self.absolute_intensity = QCheckBox("绝对强度")
        apply_help(
            self.absolute_intensity,
            tooltip="按绝对强度解释。",
            status_tip="仅适用于已经完成绝对强度校准的数据。",
        )
        self.fit_background = QCheckBox("拟合背景")
        self.fit_background.setChecked(True)
        apply_help(
            self.fit_background,
            tooltip="拟合背景项。",
            status_tip="深度分析时允许背景项吸收平缓偏移；过度拟合会影响结构参数。",
        )

        run_button = action_button(
            "运行分析",
            role="primary",
            tooltip="运行所选分析。",
            status_tip="主操作：对当前曲线和 q 范围运行分析，并记录结果与方法警告。",
        )
        run_button.clicked.connect(self.run_analysis)
        deep_button = action_button(
            "一键深度分析",
            role="success",
            tooltip="运行深度分析组合。",
            status_tip="重要：一次性运行多项派生分析；结果需结合警告和样品知识判断。",
        )
        deep_button.clicked.connect(self.run_deep_analysis)
        fill_button = action_button(
            "使用当前曲线 q 范围",
            role="secondary",
            tooltip="填入曲线 q 范围。",
            status_tip="将 q_min/q_max 设置为当前曲线的完整 q 范围，之后仍可手动收窄。",
        )
        fill_button.clicked.connect(self.fill_current_range)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        form = QFormLayout()
        form.addRow("分析类型", self.analysis_type)
        form.addRow("q_min", self.q_min)
        form.addRow("q_max", self.q_max)

        deep_group = QGroupBox("深度分析参数")
        deep_form = QFormLayout(deep_group)
        deep_form.addRow("样品类型", self.sample_type)
        deep_form.addRow("形状/模型", self.shape_model)
        deep_form.addRow("Dmax", self.dmax)
        deep_form.addRow("正则化", self.regularization)
        deep_form.addRow("contrast", self.contrast)
        deep_form.addRow("体积分数初值", self.volume_fraction)
        deep_form.addRow(self.use_contrast)
        deep_form.addRow(self.absolute_intensity)
        deep_form.addRow(self.fit_background)

        controls = QHBoxLayout()
        controls.addWidget(fill_button)
        controls.addWidget(run_button)
        controls.addWidget(deep_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(deep_group)
        layout.addLayout(controls)
        layout.addWidget(self.output, 1)

    def fill_current_range(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        self.q_min.setValue(float(curve.q.min()))
        self.q_max.setValue(float(curve.q.max()))

    def run_analysis(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("请先选择一条已导入曲线。")
            return

        q_range = (float(self.q_min.value()), float(self.q_max.value()))
        analysis_type = self.analysis_type.currentData()
        try:
            if analysis_type == "guinier":
                result = guinier_analysis(curve, q_range)
            elif analysis_type == "power_law":
                result = power_law_analysis(curve, q_range)
            elif analysis_type == "local_slope":
                result = local_slope(curve, q_range)
            elif analysis_type == "peak_detection":
                result = detect_peaks(curve, q_range)
            elif analysis_type == "invariant":
                result = invariant_measured(curve, q_range)
            elif analysis_type == "information_budget":
                result = information_budget(curve, q_range)
            elif analysis_type == "kratky_metrics":
                result = kratky_metrics(curve, q_range)
            elif analysis_type == "porod_metrics":
                result = porod_metrics(curve, q_range)
            else:
                raise ValueError(f"Unknown analysis type: {analysis_type}")
        except Exception as exc:
            self.output.setPlainText(f"分析失败: {exc}")
            return

        self.main_window.project.add_analysis_result(result)
        self.main_window.project.add_history_record(
            create_history_record(
                f"analysis:{analysis_type}",
                input_ids=[curve.curve_id],
                output_ids=[result.analysis_id],
                parameters={"analysis_type": analysis_type, "q_range": q_range},
                warnings=result.warnings,
            )
        )
        self.main_window.records_tab.refresh()
        self.output.setPlainText(self._format_result(result))

    def run_deep_analysis(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("请先选择一条已导入曲线。")
            return

        q_range = (float(self.q_min.value()), float(self.q_max.value()))
        contrast = float(self.contrast.value()) if self.use_contrast.isChecked() else None
        options = DeepAnalysisOptions(
            sample_type=self.sample_type.currentText(),
            shape_model=self.shape_model.currentText(),
            q_range=q_range,
            dmax=float(self.dmax.value()),
            regularization=float(self.regularization.value()),
            contrast=contrast,
            volume_fraction=float(self.volume_fraction.value()),
            absolute_intensity=self.absolute_intensity.isChecked(),
            fit_background=self.fit_background.isChecked(),
            low_q_method="guinier",
            high_q_method="porod_q^-4",
        )
        try:
            results = run_deep_analysis(curve, options)
        except Exception as exc:
            self.output.setPlainText(f"深度分析失败: {exc}")
            return

        for result in results:
            self.main_window.project.add_analysis_result(result)
        self.main_window.project.add_history_record(
            create_history_record(
                "analysis:deep_analysis",
                input_ids=[curve.curve_id],
                output_ids=[result.analysis_id for result in results],
                parameters={
                    "sample_type": options.sample_type,
                    "shape_model": options.shape_model,
                    "q_range": q_range,
                    "dmax": options.dmax,
                    "regularization": options.regularization,
                    "contrast": contrast,
                    "absolute_intensity": options.absolute_intensity,
                },
                warnings=[warning for result in results for warning in result.warnings],
            )
        )
        self.main_window.records_tab.refresh()
        self.output.setPlainText("\n\n".join(self._format_result(result) for result in results))

    def refresh_results(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        results = self.main_window.project.get_results_for_curve(curve.curve_id)
        if not results:
            self.output.setPlainText("当前曲线尚无分析结果。")
            return
        self.output.setPlainText("\n\n".join(self._format_result(result) for result in results))

    def _format_result(self, result) -> str:
        lines = [
            f"analysis_id: {result.analysis_id}",
            f"analysis_type: {result.analysis_type}",
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
                lines.append(
                    f"- {warning.get('warning_code')} [{warning.get('severity')}]: {warning.get('message')} 建议: {warning.get('suggested_action')}"
                )
        elif result.warnings:
            for warning in result.warnings:
                lines.append(f"- {warning}")
        else:
            lines.append("- 无")
        return "\n".join(lines)

