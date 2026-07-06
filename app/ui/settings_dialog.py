from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLineEdit, QVBoxLayout

from app.core.settings import AppSettings, save_settings
from app.ui.style import action_button, apply_help


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(520, 320)
        current = getattr(parent, "settings", AppSettings())
        self.q_unit = QComboBox()
        self.q_unit.addItems(["A^-1", "nm^-1"])
        self.q_unit.setCurrentText(current.default_q_unit)
        apply_help(
            self.q_unit,
            tooltip="默认 q 单位。",
            status_tip="用于新导入曲线的默认 q 单位；仍可在导入页手动覆盖。",
        )
        self.figure_format = QComboBox()
        self.figure_format.addItems(["png", "svg", "pdf"])
        self.figure_format.setCurrentText(current.default_figure_format)
        apply_help(
            self.figure_format,
            tooltip="默认图像格式。",
            status_tip="用于后续图像导出流程的默认格式。",
        )
        self.show_error = QCheckBox("默认显示误差棒")
        self.show_error.setChecked(current.show_error_bars)
        apply_help(
            self.show_error,
            tooltip="默认误差棒显示。",
            status_tip="打开后绘图页默认勾选误差棒；仅在曲线包含误差列时生效。",
        )
        self.show_warnings = QCheckBox("默认启用方法警告")
        self.show_warnings.setChecked(current.show_method_warnings)
        apply_help(
            self.show_warnings,
            tooltip="默认方法警告。",
            status_tip="打开后分析流程默认保留方法边界 warning，便于报告追踪。",
        )
        self.export_dir = QLineEdit(current.default_export_dir)
        apply_help(
            self.export_dir,
            tooltip="默认导出目录。",
            status_tip="导出对话框打开时使用的默认目录；不会自动写入敏感路径。",
        )
        self.log_level = QComboBox()
        self.log_level.addItems(["INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText(current.log_level)
        apply_help(
            self.log_level,
            tooltip="日志等级。",
            status_tip="控制后续记录的详细程度；普通使用保持 INFO 即可。",
        )

        save_button = action_button(
            "保存设置 JSON",
            role="primary",
            tooltip="保存设置文件。",
            status_tip="主操作：将当前设置写入 JSON，并立即同步导入和绘图页默认值。",
        )
        save_button.clicked.connect(self.save_settings)

        form = QFormLayout()
        form.addRow("默认 q 单位", self.q_unit)
        form.addRow("默认图像格式", self.figure_format)
        form.addRow("", self.show_error)
        form.addRow("", self.show_warnings)
        form.addRow("默认导出目录", self.export_dir)
        form.addRow("默认日志等级", self.log_level)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addWidget(save_button)

    def save_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存设置", "sas_curve_analyzer_settings.json", "JSON (*.json)")
        if not path:
            return
        settings = AppSettings(
            default_q_unit=self.q_unit.currentText(),
            default_figure_format=self.figure_format.currentText(),
            show_error_bars=self.show_error.isChecked(),
            show_method_warnings=self.show_warnings.isChecked(),
            default_export_dir=self.export_dir.text(),
            log_level=self.log_level.currentText(),
        )
        save_settings(settings, path)
        parent = self.parent()
        if parent is not None:
            parent.settings = settings
            parent.import_tab.q_unit.setText(settings.default_q_unit)
            parent.plotting_tab.show_error.setChecked(settings.show_error_bars)
        self.accept()

