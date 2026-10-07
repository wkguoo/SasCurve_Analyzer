from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel, QListWidget, QTextEdit, QVBoxLayout, QWidget

from app.core.records import create_formal_record
from app.core.records import create_history_record
from app.ui.style import action_button, apply_help
from app.ui.widgets import FlowLayout, configure_combo


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
        configure_combo(self.source_type)
        configure_combo(self.source_selector)
        self.source_selector.setPlaceholderText("当前项目暂无可选对象")
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
        self.output.setPlaceholderText("项目操作历史和正式记录将在这里显示。")
        self.output.setMinimumHeight(160)
        self.output.setMaximumHeight(280)
        self.formal_list.setMinimumHeight(100)
        self.formal_list.setMaximumHeight(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        source_group = QGroupBox("选择正式记录来源")
        source_layout = QVBoxLayout(source_group)
        source_form = QFormLayout()
        source_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        source_form.addRow("来源类型", self.source_type)
        source_form.addRow("来源对象", self.source_selector)
        source_layout.addLayout(source_form)
        source_note = QLabel("曲线选项显示单位和 ID，便于区分同名曲线；正式记录将进入报告上下文。")
        source_note.setWordWrap(True)
        source_layout.addWidget(source_note)
        source_actions = FlowLayout()
        source_actions.addWidget(mark_button)
        source_actions.addWidget(refresh_button)
        source_layout.addLayout(source_actions)

        formal_group = QGroupBox("已标记的正式记录")
        formal_layout = QVBoxLayout(formal_group)
        formal_layout.addWidget(self.formal_list)
        formal_layout.addWidget(unmark_button)
        layout.addWidget(source_group)
        layout.addWidget(formal_group)
        layout.addWidget(QLabel("历史记录与正式记录详情"))
        layout.addWidget(self.output)
        layout.addStretch()
        self.refresh_sources()

    def refresh_sources(self) -> None:
        source_type = self.source_type.currentData()
        selected_id = self.source_selector.currentData()
        self.source_selector.clear()
        if source_type == "curve":
            curves = self.main_window.project.curves
            prefix_ids: dict[str, list[str]] = {}
            for curve in curves:
                prefix_ids.setdefault(curve.curve_id[:8], []).append(curve.curve_id)
            for curve in curves:
                id_length = 8
                while id_length < len(curve.curve_id) and any(
                    other_id != curve.curve_id
                    and other_id[:id_length] == curve.curve_id[:id_length]
                    for other_id in prefix_ids[curve.curve_id[:8]]
                ):
                    id_length += 1
                label = f"{curve.name} · q: {curve.q_unit} · I: {curve.intensity_unit} · ID: {curve.curve_id[:id_length]}"
                self.source_selector.addItem(label, curve.curve_id)
                self.source_selector.setItemData(
                    self.source_selector.count() - 1,
                    f"{label}\n完整 ID: {curve.curve_id}\n源文件: {curve.source_file or '无'}",
                    Qt.ToolTipRole,
                )
        elif source_type == "analysis_result":
            for result in self.main_window.project.analysis_results:
                self.source_selector.addItem(f"{result.analysis_type} {result.analysis_id}", result.analysis_id)
        elif source_type == "comparison_result":
            for result in self.main_window.project.comparison_results:
                self.source_selector.addItem(f"{result.comparison_type} {result.comparison_id}", result.comparison_id)
        else:
            self.source_selector.addItem("手动图像路径入口预留", "")
        selected_index = self.source_selector.findData(selected_id)
        if selected_index >= 0:
            self.source_selector.setCurrentIndex(selected_index)

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

