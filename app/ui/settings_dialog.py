from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLineEdit, QPushButton, QVBoxLayout


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.q_unit = QComboBox()
        self.q_unit.addItems(["A^-1", "nm^-1"])
        self.figure_format = QComboBox()
        self.figure_format.addItems(["png", "svg", "pdf"])
        self.show_error = QCheckBox("默认显示误差棒")
        self.show_error.setChecked(True)
        self.show_warnings = QCheckBox("默认启用方法警告")
        self.show_warnings.setChecked(True)
        self.export_dir = QLineEdit("exports")
        self.log_level = QComboBox()
        self.log_level.addItems(["INFO", "WARNING", "ERROR"])

        save_button = QPushButton("保存设置 JSON")
        save_button.clicked.connect(self.save_settings)

        form = QFormLayout()
        form.addRow("默认 q 单位", self.q_unit)
        form.addRow("默认图像格式", self.figure_format)
        form.addRow("", self.show_error)
        form.addRow("", self.show_warnings)
        form.addRow("默认导出目录", self.export_dir)
        form.addRow("默认日志等级", self.log_level)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(save_button)

    def save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存设置", "sas_curve_analyzer_settings.json", "JSON (*.json)")
        if not path:
            return
        payload = {
            "default_q_unit": self.q_unit.currentText(),
            "default_figure_format": self.figure_format.currentText(),
            "show_error_bars": self.show_error.isChecked(),
            "show_method_warnings": self.show_warnings.isChecked(),
            "default_export_dir": self.export_dir.text(),
            "log_level": self.log_level.currentText(),
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.accept()

