from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QListWidget, QTextEdit, QVBoxLayout, QWidget

from app.core.records import create_formal_record
from app.core.records import create_history_record
from app.ui.style import action_button, apply_help


class RecordsTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.source_type = QComboBox()
        for label, key in [
            ("Curve", "curve"),
            ("Analysis result", "analysis_result"),
            ("Comparison result", "comparison_result"),
            ("Figure", "figure"),
        ]:
            self.source_type.addItem(label, key)
        apply_help(
            self.source_type,
            tooltip="选择记录来源类型。",
            status_tip="正式记录可来自曲线、分析结果、比较结果或预留图像入口。",
        )
        self.source_type.currentTextChanged.connect(self.refresh_sources)
        self.source_selector = QComboBox()
        apply_help(
            self.source_selector,
            tooltip="选择要标记的对象。",
            status_tip="选择一个来源对象后，可标记为正式记录并写入报告上下文。",
        )
        mark_button = action_button(
            "标记为正式记录",
            role="success",
            tooltip="加入正式记录。",
            status_tip="重要：把选中对象纳入正式记录，便于报告和复现追踪。",
        )
        mark_button.clicked.connect(self.mark_selected_source)
        unmark_button = action_button(
            "取消选中正式记录",
            role="danger",
            tooltip="移除正式记录。",
            status_tip="危险操作：从正式记录列表中移除当前选中项，并写入历史记录。",
        )
        unmark_button.clicked.connect(self.unmark_selected_formal_record)
        refresh_button = action_button(
            "刷新记录",
            role="secondary",
            tooltip="刷新记录视图。",
            status_tip="同步项目历史记录和正式记录列表。",
        )
        refresh_button.clicked.connect(self.refresh)
        self.formal_list = QListWidget()
        apply_help(
            self.formal_list,
            tooltip="正式记录列表。",
            status_tip="这里显示将进入报告上下文的正式记录；选中后可取消标记。",
        )
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_type)
        source_row.addWidget(self.source_selector, 1)
        source_row.addWidget(mark_button)
        source_row.addWidget(unmark_button)
        source_row.addWidget(refresh_button)
        layout.addLayout(source_row)
        layout.addWidget(self.formal_list)
        layout.addWidget(self.output, 1)
        self.refresh_sources()

    def refresh_sources(self) -> None:
        source_type = self.source_type.currentData()
        self.source_selector.clear()
        if source_type == "curve":
            for curve in self.main_window.project.curves:
                self.source_selector.addItem(curve.name, curve.curve_id)
        elif source_type == "analysis_result":
            for result in self.main_window.project.analysis_results:
                self.source_selector.addItem(f"{result.analysis_type} {result.analysis_id}", result.analysis_id)
        elif source_type == "comparison_result":
            for result in self.main_window.project.comparison_results:
                self.source_selector.addItem(f"{result.comparison_type} {result.comparison_id}", result.comparison_id)
        else:
            self.source_selector.addItem("手动图像路径入口预留", "")

    def mark_selected_source(self) -> None:
        source_type = self.source_type.currentData()
        source_id = self.source_selector.currentData()
        if not source_id:
            self.output.setPlainText("没有可标记的对象。")
            return
        title = f"正式记录 - {self.source_selector.currentText()}"
        kwargs = {}
        if source_type == "curve":
            curve = self.main_window.project.get_curve(source_id)
            if curve is not None:
                kwargs["q_range"] = (float(curve.q.min()), float(curve.q.max()))
        record = create_formal_record(source_type, source_id, title, **kwargs)
        self.main_window.project.add_formal_record(record)
        self.main_window.project.add_history_record(
            create_history_record("mark_formal_record", input_ids=[source_id], output_ids=[record.formal_id], parameters={"source_type": source_type})
        )
        self.refresh()
        self.main_window.mark_project_dirty()

    def unmark_selected_formal_record(self) -> None:
        row = self.formal_list.currentRow()
        if row < 0 or row >= len(self.main_window.project.formal_records):
            self.output.setPlainText("请先选中一个正式记录。")
            return
        record = self.main_window.project.formal_records.pop(row)
        self.main_window.project.add_history_record(
            create_history_record("unmark_formal_record", input_ids=[record.formal_id], parameters={"source_type": record.source_type, "source_id": record.source_id})
        )
        self.refresh()
        self.main_window.mark_project_dirty()

    def refresh(self) -> None:
        project = self.main_window.project
        self.refresh_sources()
        self.formal_list.clear()
        for record in project.formal_records:
            self.formal_list.addItem(f"{record.title}: {record.source_type} {record.source_id}")
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

