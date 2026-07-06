from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.advanced_transforms import transform_curve
from app.core.correlation import compute_correlation_function
from app.core.method_warnings import guinier_warnings, invariant_warnings, peak_warnings, porod_plateau_warnings
from app.core.pr_analysis import compute_pr


class AdvancedTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.transform_type = QComboBox()
        self.transform_type.addItems(["q_to_size", "q_squared", "lnI", "log10I", "qI", "q2I", "q3I", "q4I", "normalized_I"])
        transform_button = QPushButton("运行高级变换")
        transform_button.clicked.connect(self.run_transform)
        pr_button = QPushButton("P(r) experimental 预留接口")
        pr_button.clicked.connect(self.run_pr_placeholder)
        corr_button = QPushButton("相关函数预留接口")
        corr_button.clicked.connect(self.run_correlation_placeholder)
        warning_button = QPushButton("显示方法边界 warning 示例")
        warning_button.clicked.connect(self.show_method_warnings)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.transform_type)
        layout.addWidget(transform_button)
        layout.addWidget(pr_button)
        layout.addWidget(corr_button)
        layout.addWidget(warning_button)
        layout.addWidget(self.output, 1)

    def run_transform(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        result = transform_curve(curve, self.transform_type.currentText())
        self.output.setPlainText(
            f"transform_name: {result.transform_name}\nunit: {result.unit}\npoints: {result.output.size}\nwarnings: {result.warnings}"
        )

    def run_pr_placeholder(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        result = compute_pr(curve, (float(curve.q.min()), float(curve.q.max())), dmax=100.0)
        self.main_window.project.add_analysis_result(result)
        self.output.setPlainText(f"{result.analysis_type}\nwarnings:\n- " + "\n- ".join(result.warnings))

    def run_correlation_placeholder(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        try:
            compute_correlation_function(curve, (float(curve.q.min()), float(curve.q.max())), {})
        except NotImplementedError as exc:
            self.output.setPlainText(str(exc))

    def show_method_warnings(self) -> None:
        warnings = []
        warnings.extend(guinier_warnings(qrg_max=1.5))
        warnings.extend(invariant_warnings())
        warnings.extend(peak_warnings())
        warnings.extend(porod_plateau_warnings([1.0, 3.0, 0.5]))
        lines = ["结构化方法 warning 示例:"]
        for warning in warnings:
            lines.append(f"- {warning.warning_code} [{warning.severity}] {warning.message} 建议: {warning.suggested_action}")
        self.output.setPlainText("\n".join(lines))
