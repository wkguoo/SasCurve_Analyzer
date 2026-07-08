from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QTextEdit, QVBoxLayout, QWidget

from app.core.deep_analysis import DeepAnalysisOptions, SAMPLE_TYPES, SHAPE_MODELS, run_deep_analysis
from app.core.records import create_history_record
from app.core.user_messages import exception_detail, format_user_message, UserMessage
from app.ui.style import action_button, apply_help


class DeepAnalysisTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window

        self.q_min = QDoubleSpinBox()
        self.q_min.setDecimals(6)
        self.q_min.setRange(0.0, 1_000_000.0)
        self.q_max = QDoubleSpinBox()
        self.q_max.setDecimals(6)
        self.q_max.setRange(0.0, 1_000_000.0)
        self.q_max.setValue(1.0)

        self.sample_type = QComboBox()
        self.sample_type.addItems(SAMPLE_TYPES)
        self.shape_model = QComboBox()
        self.shape_model.addItems(SHAPE_MODELS)
        self.dmax = QDoubleSpinBox()
        self.dmax.setDecimals(3)
        self.dmax.setRange(0.001, 1_000_000.0)
        self.dmax.setValue(100.0)
        self.regularization = QDoubleSpinBox()
        self.regularization.setDecimals(6)
        self.regularization.setRange(0.0, 1_000.0)
        self.regularization.setValue(0.01)
        self.contrast = QDoubleSpinBox()
        self.contrast.setDecimals(6)
        self.contrast.setRange(0.0, 1_000_000.0)
        self.volume_fraction = QDoubleSpinBox()
        self.volume_fraction.setDecimals(6)
        self.volume_fraction.setRange(0.0, 1.0)
        self.use_contrast = QCheckBox("使用 contrast")
        self.absolute_intensity = QCheckBox("绝对强度")
        self.fit_background = QCheckBox("拟合背景")
        self.fit_background.setChecked(True)

        apply_help(
            self.sample_type,
            tooltip="样品类型提示。",
            status_tip="用于深度分析的解释标签；结果仍需结合样品体系和数据质量判断。",
        )
        apply_help(
            self.shape_model,
            tooltip="形状/模型假设。",
            status_tip="深度分析的模型假设；不作为自动结构判定。",
        )

        fill_button = action_button("使用当前曲线 q 范围", role="secondary", tooltip="填入当前曲线完整 raw q 范围。")
        fill_button.clicked.connect(self.fill_current_range)
        run_button = action_button(
            "一键深度分析",
            role="success",
            tooltip="运行深度分析组合。",
            status_tip="高级功能：一次运行多项派生分析；解释依赖样品体系、模型假设和数据质量。",
        )
        run_button.clicked.connect(self.run_deep_analysis)

        form = QFormLayout()
        form.addRow("q_min", self.q_min)
        form.addRow("q_max", self.q_max)
        form.addRow("样品类型", self.sample_type)
        form.addRow("形状/模型", self.shape_model)
        form.addRow("Dmax", self.dmax)
        form.addRow("regularization", self.regularization)
        form.addRow("contrast", self.contrast)
        form.addRow("体积分数初值", self.volume_fraction)
        form.addRow(self.use_contrast)
        form.addRow(self.absolute_intensity)
        form.addRow(self.fit_background)

        controls = QHBoxLayout()
        controls.addWidget(fill_button)
        controls.addWidget(run_button)
        controls.addStretch(1)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addLayout(controls)
        layout.addWidget(self.output, 1)

    def fill_current_range(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        self.q_min.setValue(float(curve.q.min()))
        self.q_max.setValue(float(curve.q.max()))

    def run_deep_analysis(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="无法运行深度分析",
                        what_happened="当前没有选中的曲线。",
                        facts=(
                            "MainWindow.current_curve() 返回 None。",
                            "深度分析需要一条当前曲线和 DeepAnalysisOptions。",
                        ),
                        severity="warning",
                    )
                )
            )
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
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="深度分析失败",
                        what_happened="深度分析组合没有成功生成结果。",
                        facts=(
                            f"raw q range: [{q_range[0]:.6g}, {q_range[1]:.6g}]。",
                            f"Dmax: {options.dmax}。",
                            f"regularization: {options.regularization}。",
                            f"contrast enabled: {contrast is not None}。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
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
        self.main_window.mark_project_dirty()
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
        if result.warnings:
            lines.extend(f"- {warning}" for warning in result.warnings)
        else:
            lines.append("- 无")
        return "\n".join(lines)

