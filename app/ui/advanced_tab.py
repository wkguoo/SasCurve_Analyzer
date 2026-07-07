from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QTextEdit, QVBoxLayout, QWidget

from app.core.advanced_transforms import transform_curve
from app.core.correlation import compute_correlation_function
from app.core.method_warnings import guinier_warnings, invariant_warnings, peak_warnings, porod_plateau_warnings
from app.core.pr_analysis import compute_pr
from app.ui.style import action_button, apply_help


class AdvancedTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.transform_type = QComboBox()
        for label, key in [
            ("Real-space scale 2\u03c0/q", "q_to_size"),
            ("q\u00b2", "q_squared"),
            ("Natural log intensity", "lnI"),
            ("Log10 intensity", "log10I"),
            ("q I(q)", "qI"),
            ("q\u00b2I(q)", "q2I"),
            ("q\u00b3I(q)", "q3I"),
            ("q\u2074I(q)", "q4I"),
            ("Normalize by I max", "normalized_I"),
        ]:
            self.transform_type.addItem(label, key)
        apply_help(
            self.transform_type,
            tooltip="选择高级变换。",
            status_tip="这些变换用于快速检查曲线表现形式，不替代正式模型拟合。",
        )
        transform_button = action_button(
            "运行高级变换",
            role="primary",
            tooltip="运行曲线变换。",
            status_tip="主操作：对当前曲线生成选定变换结果，原始曲线不被修改。",
        )
        transform_button.clicked.connect(self.run_transform)
        self.pr_button = action_button(
            "P(r) experimental 预留接口",
            role="warning",
            tooltip="运行实验性 P(r)。",
            status_tip="谨慎：P(r) 接口为实验性结果，不应直接作为正式物理结论。",
        )
        self.pr_button.setEnabled(False)
        self.pr_button.clicked.connect(self.run_pr_placeholder)
        self.corr_button = action_button(
            "相关函数分析",
            role="warning",
            tooltip="运行相关函数分析。",
            status_tip="谨慎：相关函数结果依赖 q 范围和数据质量，需结合方法警告解释。",
        )
        self.corr_button.setEnabled(False)
        self.corr_button.clicked.connect(self.run_correlation_placeholder)
        warning_button = action_button(
            "显示方法边界 warning 示例",
            role="warning",
            tooltip="查看 warning 示例。",
            status_tip="显示常见方法边界提示，帮助理解分析结果中的 warning 严重程度。",
        )
        warning_button.clicked.connect(self.show_method_warnings)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.transform_type)
        layout.addWidget(transform_button)
        layout.addWidget(self.pr_button)
        layout.addWidget(self.corr_button)
        layout.addWidget(warning_button)
        layout.addWidget(self.output, 1)

    def run_transform(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        result = transform_curve(curve, self.transform_type.currentData())
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
        result = compute_correlation_function(curve, (float(curve.q.min()), float(curve.q.max())), {})
        self.main_window.project.add_analysis_result(result)
        self.output.setPlainText(f"{result.analysis_type}\nwarnings:\n- " + "\n- ".join(result.warnings))

    def show_method_warnings(self) -> None:
        warnings = []
        warnings.extend(guinier_warnings(qrg_max=1.5))
        warnings.extend(invariant_warnings())
        warnings.extend(peak_warnings())
        warnings.extend(porod_plateau_warnings([1.0, 3.0, 0.5]))
        lines = ["结构化方法 warning 示例:"]
        for warning in warnings:
            lines.append(f"- {warning.warning_code} [{warning.severity}] {warning.message}")
        self.output.setPlainText("\n".join(lines))
