from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, invariant_measured, kratky_metrics, local_slope, porod_metrics, power_law_analysis


class AnalysisTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.analysis_type = QComboBox()
        self.analysis_type.addItems(["guinier", "power_law", "local_slope", "peak_detection", "invariant", "kratky_metrics", "porod_metrics"])

        self.q_min = QDoubleSpinBox()
        self.q_min.setDecimals(6)
        self.q_min.setRange(0.0, 1_000_000.0)
        self.q_max = QDoubleSpinBox()
        self.q_max.setDecimals(6)
        self.q_max.setRange(0.0, 1_000_000.0)
        self.q_max.setValue(1.0)

        run_button = QPushButton("运行分析")
        run_button.clicked.connect(self.run_analysis)
        fill_button = QPushButton("使用当前曲线 q 范围")
        fill_button.clicked.connect(self.fill_current_range)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        form = QFormLayout()
        form.addRow("分析类型", self.analysis_type)
        form.addRow("q_min", self.q_min)
        form.addRow("q_max", self.q_max)

        controls = QHBoxLayout()
        controls.addWidget(fill_button)
        controls.addWidget(run_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
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

    def run_analysis(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("请先选择一条已导入曲线。")
            return

        q_range = (float(self.q_min.value()), float(self.q_max.value()))
        analysis_type = self.analysis_type.currentText()
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
        self.output.setPlainText(self._format_result(result))

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
            lines.append(f"- {key}: {value}")
        lines.append("")
        lines.append("warnings:")
        if result.warnings:
            for warning in result.warnings:
                lines.append(f"- {warning}")
        else:
            lines.append("- 无")
        return "\n".join(lines)

