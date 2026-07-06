from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.batch import average_replicates, create_curve_group
from app.core.comparison import compare_curves


class BatchTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.comparison_type = QComboBox()
        self.comparison_type.addItems(["difference", "ratio", "relative_difference"])

        group_button = QPushButton("将全部曲线建为一个组")
        group_button.clicked.connect(self.create_all_group)
        average_button = QPushButton("平均全部曲线")
        average_button.clicked.connect(self.average_all)
        compare_button = QPushButton("比较前两条曲线")
        compare_button.clicked.connect(self.compare_first_two)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(group_button)
        layout.addWidget(average_button)
        layout.addWidget(self.comparison_type)
        layout.addWidget(compare_button)
        layout.addWidget(self.output, 1)

    def create_all_group(self) -> None:
        curves = self.main_window.project.curves
        if not curves:
            self.output.setPlainText("没有可分组曲线。")
            return
        group = create_curve_group("all_curves", curves)
        self.main_window.project.add_group(group)
        self.output.setPlainText(f"已创建曲线组: {group.name}, 曲线数={len(group.curve_ids)}")

    def average_all(self) -> None:
        curves = self.main_window.project.curves
        if len(curves) < 2:
            self.output.setPlainText("至少需要两条曲线才能平均。")
            return
        try:
            averaged, record = average_replicates(curves, interpolate=True, name="average_all")
        except Exception as exc:
            self.output.setPlainText(f"平均失败: {exc}")
            return
        self.main_window.add_curve(averaged)
        self.main_window.project.add_history_record(record)
        self.output.setPlainText(f"已生成平均曲线: {averaged.name}\nrecord_id: {record.record_id}")

    def compare_first_two(self) -> None:
        curves = self.main_window.project.curves
        if len(curves) < 2:
            self.output.setPlainText("至少需要两条曲线才能比较。")
            return
        result = compare_curves(curves[0], curves[1], self.comparison_type.currentText(), interpolate=True)
        self.main_window.project.add_comparison_result(result)
        self.output.setPlainText(
            f"比较完成: {result.comparison_type}\ncomparison_id: {result.comparison_id}\n点数: {result.q.size}\nwarnings: {result.warnings}"
        )

