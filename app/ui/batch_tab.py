from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.batch import SEQUENCE_INDEX_COLUMNS, average_replicates, build_sequence_index, create_curve_group, export_sequence_index_csv
from app.core.comparison import compare_curves
from app.core.records import create_history_record
from app.core.user_messages import UserMessage, exception_detail, format_user_message
from app.ui.style import action_button, apply_help


class BatchTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.group_name = QLineEdit("in_situ_series")
        apply_help(
            self.group_name,
            tooltip="曲线组名称。",
            status_tip="用于选中曲线建组和平均曲线命名；建议使用样品或序列名。",
        )
        self.curve_list = QListWidget()
        self.curve_list.setSelectionMode(QAbstractItemView.MultiSelection)
        apply_help(
            self.curve_list,
            tooltip="多选曲线列表。",
            status_tip="按 Ctrl 或 Shift 多选曲线，用于建组或平均；A/B 比较请使用下方下拉框。",
        )
        self.curve_a = QComboBox()
        self.curve_b = QComboBox()
        self.comparison_type = QComboBox()
        self.sequence_rows: list[dict] = []
        self.sequence_table = QTableWidget(0, len(SEQUENCE_INDEX_COLUMNS))
        self.sequence_table.setHorizontalHeaderLabels(SEQUENCE_INDEX_COLUMNS)
        self.sequence_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.sequence_table.setSelectionMode(QAbstractItemView.MultiSelection)
        self.sequence_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        apply_help(
            self.sequence_table,
            tooltip="序列管理表。",
            status_tip="显示当前项目曲线的序列顺序、frame、q 范围、点数和 warning；只读，不修改曲线数据。",
        )
        for label, key in [
            ("Difference B - A", "difference"),
            ("Ratio B / A", "ratio"),
            ("Relative difference (B - A) / A", "relative_difference"),
        ]:
            self.comparison_type.addItem(label, key)
        apply_help(
            self.curve_a,
            tooltip="选择曲线 A。",
            status_tip="A/B 比较中的第一条曲线，作为差值或比值的左侧输入。",
        )
        apply_help(
            self.curve_b,
            tooltip="选择曲线 B。",
            status_tip="A/B 比较中的第二条曲线，不能与曲线 A 相同。",
        )
        apply_help(
            self.comparison_type,
            tooltip="选择比较方式。",
            status_tip="difference 为差值，ratio 为比值，relative_difference 为相对差异。",
        )

        refresh_button = action_button(
            "刷新曲线列表",
            role="secondary",
            tooltip="刷新可选曲线。",
            status_tip="同步左侧项目曲线列表中的最新导入或派生曲线。",
        )
        refresh_button.clicked.connect(self.refresh_curves)
        refresh_sequence_button = action_button(
            "刷新序列表",
            role="secondary",
            tooltip="刷新序列管理表。",
            status_tip="根据当前项目曲线和 metadata 重新生成序列索引表。",
        )
        refresh_sequence_button.clicked.connect(self.refresh_sequence_table)
        select_sequence_button = action_button(
            "按序列顺序选择全部",
            role="secondary",
            tooltip="按序列顺序选中曲线。",
            status_tip="同步选择序列表和多选曲线列表，方便建组或平均。",
        )
        select_sequence_button.clicked.connect(self.select_all_by_sequence_order)
        group_sequence_button = action_button(
            "从选中行建组",
            role="success",
            tooltip="用序列表选中行创建曲线组。",
            status_tip="按序列表当前顺序创建曲线组，不自动解释相变或动力学。",
        )
        group_sequence_button.clicked.connect(self.create_group_from_selected_sequence_rows)
        export_sequence_button = action_button(
            "导出序列索引 CSV",
            role="secondary",
            tooltip="导出序列表。",
            status_tip="写出 sequence_index.csv，便于复核导入顺序、frame、q 范围和 warning。",
        )
        export_sequence_button.clicked.connect(self.export_sequence_index)
        group_button = action_button(
            "将选中曲线建组",
            role="success",
            tooltip="创建曲线组。",
            status_tip="重要：把多选曲线记录为一个有序组，便于后续报告和批处理追踪。",
        )
        group_button.clicked.connect(self.create_selected_group)
        average_button = action_button(
            "平均选中曲线",
            role="primary",
            tooltip="生成平均曲线。",
            status_tip="主操作：对选中曲线插值后平均，生成新曲线并保留原始数据。",
        )
        average_button.clicked.connect(self.average_selected)
        compare_button = action_button(
            "比较曲线 A/B",
            role="primary",
            tooltip="比较两条曲线。",
            status_tip="主操作：按所选方式比较 A/B 两条曲线，并记录比较结果和警告。",
        )
        compare_button.clicked.connect(self.compare_selected)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        form = QFormLayout()
        form.addRow("组名", self.group_name)
        form.addRow("曲线 A", self.curve_a)
        form.addRow("曲线 B", self.curve_b)
        form.addRow("比较类型", self.comparison_type)
        layout.addWidget(self.curve_list)
        layout.addLayout(form)
        sequence_buttons = QHBoxLayout()
        sequence_buttons.addWidget(refresh_sequence_button)
        sequence_buttons.addWidget(select_sequence_button)
        sequence_buttons.addWidget(group_sequence_button)
        sequence_buttons.addWidget(export_sequence_button)
        sequence_buttons.addStretch(1)
        layout.addLayout(sequence_buttons)
        layout.addWidget(self.sequence_table)
        buttons = QHBoxLayout()
        buttons.addWidget(refresh_button)
        buttons.addWidget(group_button)
        buttons.addWidget(average_button)
        buttons.addWidget(compare_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addWidget(self.output, 1)
        self.refresh_curves()

    def refresh_curves(self) -> None:
        current_a = self.curve_a.currentData()
        current_b = self.curve_b.currentData()
        self.curve_list.clear()
        self.curve_a.clear()
        self.curve_b.clear()
        for curve in self.main_window.project.curves:
            label = f"{curve.name}  [{curve.q_unit}]"
            self.curve_list.addItem(label)
            self.curve_a.addItem(label, curve.curve_id)
            self.curve_b.addItem(label, curve.curve_id)
        for combo, current in ((self.curve_a, current_a), (self.curve_b, current_b)):
            if current is not None:
                idx = combo.findData(current)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
        self.refresh_sequence_table()

    def refresh_sequence_table(self) -> None:
        self.sequence_rows = build_sequence_index(self.main_window.project.curves)
        self.sequence_table.setRowCount(len(self.sequence_rows))
        for row_index, row in enumerate(self.sequence_rows):
            for column_index, column in enumerate(SEQUENCE_INDEX_COLUMNS):
                value = row.get(column)
                item = QTableWidgetItem("" if value is None else str(value))
                self.sequence_table.setItem(row_index, column_index, item)
        self.sequence_table.resizeColumnsToContents()

    def select_all_by_sequence_order(self) -> None:
        self.curve_list.clearSelection()
        self.sequence_table.clearSelection()
        for row_index, row in enumerate(self.sequence_rows):
            project_order = row.get("project_order")
            if project_order is not None and 0 <= project_order < self.curve_list.count():
                self.curve_list.item(project_order).setSelected(True)
            self.sequence_table.selectRow(row_index)
        self.output.setPlainText(f"已按序列顺序选择 {len(self.sequence_rows)} 条曲线。")

    def _selected_sequence_curves(self):
        selected_rows = sorted({index.row() for index in self.sequence_table.selectedIndexes()})
        curve_ids = [self.sequence_rows[row]["curve_id"] for row in selected_rows if row < len(self.sequence_rows)]
        return [curve for curve_id in curve_ids if (curve := self._curve_by_id(curve_id)) is not None]

    def create_group_from_selected_sequence_rows(self) -> None:
        curves = self._selected_sequence_curves()
        if not curves:
            self.output.setPlainText("请先在序列管理表中选择要分组的行。")
            return
        group = create_curve_group(
            self.group_name.text().strip() or "sequence_group",
            curves,
            metadata={"group_type": "sequence_table_selection", "source": "sequence_management_table"},
        )
        self.main_window.project.add_group(group)
        record = create_history_record(
            "create_sequence_group",
            input_ids=[curve.curve_id for curve in curves],
            output_ids=[group.group_id],
            parameters={"group_name": group.name, "curve_count": len(curves), "source": "sequence_management_table"},
        )
        self.main_window.project.add_history_record(record)
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已从序列管理表创建曲线组: {group.name}, 曲线数={len(group.curve_ids)}")

    def export_sequence_index(self) -> None:
        default_path = Path(self.main_window.settings.default_export_dir) / "sequence_index.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出序列索引 CSV", str(default_path), "CSV files (*.csv);;All files (*)")
        if not path:
            return
        try:
            output_path = export_sequence_index_csv(self.main_window.project.curves, path)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="序列索引 CSV 导出失败",
                        what_happened="当前序列索引没有写入目标文件。",
                        facts=(f"target_path: {path}", f"curve_count: {len(self.main_window.project.curves)}"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(
            create_history_record("export_sequence_index_csv", parameters={"path": str(output_path), "curve_count": len(self.main_window.project.curves)})
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已导出序列索引: {output_path}")

    def _selected_curves(self):
        rows = sorted(self.curve_list.row(item) for item in self.curve_list.selectedItems())
        return [self.main_window.project.curves[row] for row in rows]

    def _curve_by_id(self, curve_id: str):
        return self.main_window.project.get_curve(curve_id)

    def create_selected_group(self) -> None:
        curves = self._selected_curves()
        if not curves:
            self.output.setPlainText("请先选择要分组的曲线。")
            return
        group = create_curve_group(self.group_name.text().strip() or "curve_group", curves)
        self.main_window.project.add_group(group)
        record = create_history_record(
            "create_curve_group",
            input_ids=[curve.curve_id for curve in curves],
            output_ids=[group.group_id],
            parameters={"group_name": group.name, "curve_count": len(curves)},
        )
        self.main_window.project.add_history_record(record)
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已创建曲线组: {group.name}, 曲线数={len(group.curve_ids)}")

    def average_selected(self) -> None:
        curves = self._selected_curves()
        if len(curves) < 2:
            self.output.setPlainText("至少需要选中两条曲线才能平均。")
            return
        try:
            averaged, record = average_replicates(curves, interpolate=True, name=f"{self.group_name.text().strip() or 'selected'}_average")
        except Exception as exc:
            self.output.setPlainText(f"平均失败: {exc}")
            return
        self.main_window.add_curve(averaged)
        self.main_window.project.add_history_record(record)
        self.refresh_curves()
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已生成平均曲线: {averaged.name}\nrecord_id: {record.record_id}")

    def compare_selected(self) -> None:
        curve_a = self._curve_by_id(self.curve_a.currentData())
        curve_b = self._curve_by_id(self.curve_b.currentData())
        if curve_a is None or curve_b is None:
            self.output.setPlainText("至少需要两条曲线才能比较。")
            return
        if curve_a.curve_id == curve_b.curve_id:
            self.output.setPlainText("不能比较同一条曲线。")
            return
        try:
            result = compare_curves(curve_a, curve_b, self.comparison_type.currentData(), interpolate=True)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="曲线 A/B 比较失败",
                        what_happened="当前两条曲线没有生成比较结果。",
                        facts=(f"curve_a: {curve_a.name}", f"curve_b: {curve_b.name}", "原始导入曲线未被修改。"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_comparison_result(result)
        record = create_history_record(
            f"comparison:{result.comparison_type}",
            input_ids=[curve_a.curve_id, curve_b.curve_id],
            output_ids=[result.comparison_id],
            parameters={"comparison_type": result.comparison_type, "interpolate": True},
            warnings=result.warnings,
        )
        self.main_window.project.add_history_record(record)
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(
            f"比较完成: {result.comparison_type}\ncomparison_id: {result.comparison_id}\n点数: {result.q.size}\nwarnings: {result.warnings}"
        )

