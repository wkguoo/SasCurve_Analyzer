from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.records import create_formal_record


class RecordsTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        mark_button = QPushButton("将当前曲线标记为正式记录")
        mark_button.clicked.connect(self.mark_current_curve)
        refresh_button = QPushButton("刷新记录")
        refresh_button.clicked.connect(self.refresh)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(mark_button)
        layout.addWidget(refresh_button)
        layout.addWidget(self.output, 1)

    def mark_current_curve(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.output.setPlainText("尚未选择曲线。")
            return
        record = create_formal_record("curve", curve.curve_id, f"正式记录 - {curve.name}", q_range=(float(curve.q.min()), float(curve.q.max())))
        self.main_window.project.add_formal_record(record)
        self.refresh()

    def refresh(self) -> None:
        project = self.main_window.project
        lines = ["历史记录:"]
        if project.history_records:
            for record in project.history_records:
                lines.append(f"- {record.timestamp} {record.action_type}: {record.input_ids} -> {record.output_ids}")
        else:
            lines.append("- 暂无")
        lines.append("")
        lines.append("正式记录:")
        if project.formal_records:
            for record in project.formal_records:
                lines.append(f"- {record.title}: {record.source_type} {record.source_id}")
        else:
            lines.append("- 暂无")
        self.output.setPlainText("\n".join(lines))

