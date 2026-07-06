from __future__ import annotations

from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from app.core.validation import validate_curve
from app.ui.style import action_button


class CheckTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        run_button = action_button(
            "检查当前曲线",
            role="primary",
            tooltip="检查当前曲线。",
            status_tip="主操作：检查 q、I(q)、误差列、重复值和无效数值等数据质量问题。",
        )
        run_button.clicked.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(run_button)
        layout.addWidget(self.output, 1)

    def refresh(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return

        report = validate_curve(curve)
        lines = [
            f"曲线: {curve.name}",
            f"curve_id: {curve.curve_id}",
            "",
            "基本信息:",
        ]
        for key, value in report.summary.items():
            lines.append(f"- {key}: {value}")

        lines.append("")
        lines.append("检查结果:")
        if not report.issues:
            lines.append("- 未发现明显数据质量警告。")
        else:
            for issue in report.issues:
                lines.append(f"- [{issue.severity}] {issue.code}: {issue.message} count={issue.count}")

        self.output.setPlainText("\n".join(lines))

