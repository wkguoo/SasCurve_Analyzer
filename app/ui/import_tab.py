from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.io import load_curve
from app.core.transforms import convert_q_unit


class ImportTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.selected_file: Path | None = None

        self.file_label = QLabel("未选择文件")
        choose_button = QPushButton("选择数据文件")
        choose_button.clicked.connect(self.choose_file)

        self.q_column = QLineEdit("q")
        self.intensity_column = QLineEdit("I")
        self.error_column = QLineEdit("error")
        self.q_unit = QLineEdit("A^-1")
        self.intensity_unit = QLineEdit("cm^-1")

        import_button = QPushButton("导入曲线")
        import_button.clicked.connect(self.import_curve)

        convert_to_nm_button = QPushButton("当前曲线 q 转为 nm^-1")
        convert_to_nm_button.clicked.connect(lambda: self.convert_current("nm^-1"))
        convert_to_a_button = QPushButton("当前曲线 q 转为 A^-1")
        convert_to_a_button.clicked.connect(lambda: self.convert_current("A^-1"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)

        file_row = QHBoxLayout()
        file_row.addWidget(choose_button)
        file_row.addWidget(self.file_label, 1)

        form = QFormLayout()
        form.addRow("q 列", self.q_column)
        form.addRow("I(q) 列", self.intensity_column)
        form.addRow("error/sigma 列，可留空", self.error_column)
        form.addRow("q 单位", self.q_unit)
        form.addRow("强度单位", self.intensity_unit)

        layout = QVBoxLayout(self)
        layout.addLayout(file_row)
        layout.addLayout(form)
        layout.addWidget(import_button)
        layout.addWidget(convert_to_nm_button)
        layout.addWidget(convert_to_a_button)
        layout.addWidget(self.log, 1)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 SAS 曲线数据",
            "",
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if path:
            self.selected_file = Path(path)
            self.file_label.setText(str(self.selected_file))

    def import_curve(self) -> None:
        if self.selected_file is None:
            self.log.append("请先选择 csv、txt 或 dat 文件。")
            return

        error_text = self.error_column.text().strip()
        error_column = error_text if error_text else None
        try:
            curve = load_curve(
                self.selected_file,
                q_column=self.q_column.text().strip(),
                intensity_column=self.intensity_column.text().strip(),
                error_column=error_column,
                q_unit=self.q_unit.text().strip(),
                intensity_unit=self.intensity_unit.text().strip(),
            )
        except Exception as exc:
            self.log.append(f"导入失败: {exc}")
            return

        self.main_window.add_curve(curve)
        self.log.append(f"导入成功: {curve.name}, 点数={curve.q.size}, error={'有' if curve.error is not None else '无'}")

    def convert_current(self, target_unit: str) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.log.append("请先选择一条已导入曲线。")
            return
        try:
            converted = convert_q_unit(curve, target_unit)
        except Exception as exc:
            self.log.append(f"单位转换失败: {exc}")
            return
        self.main_window.replace_current_curve_selection(converted)
        self.log.append(f"已生成新曲线: {converted.name}; 原始曲线未被修改。")

