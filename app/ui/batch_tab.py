from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QTextEdit, QVBoxLayout, QWidget

from app.core.batch import average_replicates, create_curve_group
from app.core.comparison import compare_curves
from app.core.records import create_history_record
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
        self.comparison_type.addItems(["difference", "ratio", "relative_difference"])
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
        result = compare_curves(curve_a, curve_b, self.comparison_type.currentText(), interpolate=True)
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
        self.output.setPlainText(
            f"比较完成: {result.comparison_type}\ncomparison_id: {result.comparison_id}\n点数: {result.q.size}\nwarnings: {result.warnings}"
        )

