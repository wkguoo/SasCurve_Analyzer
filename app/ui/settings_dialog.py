from __future__ import annotations

from dataclasses import asdict

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.model_catalog import format_model_catalog_summary
from app.core.settings import AppSettings, SettingsLoadInfo, load_settings_with_info, save_settings
from app.ui.model_catalog_dialog import ModelCatalogDialog
from app.ui.style import action_button, apply_help
from app.ui.widgets import FlowLayout, scroll_page


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(760, 620)
        self.setMinimumSize(560, 420)
        current = getattr(parent, "settings", AppSettings())

        self.q_unit = QComboBox()
        self.q_unit.addItems(["A^-1", "nm^-1"])
        self.q_unit.setCurrentText(current.default_q_unit)
        apply_help(
            self.q_unit,
            tooltip="Default q unit.",
            status_tip="Used for newly imported curves unless the import tab overrides it.",
        )

        self.figure_format = QComboBox()
        self.figure_format.addItems(["png", "svg", "pdf"])
        self.figure_format.setCurrentText(current.default_figure_format)

        self.show_error = QCheckBox("默认显示误差棒")
        self.show_error.setChecked(current.show_error_bars)
        self.show_warnings = QCheckBox("默认显示方法警告")
        self.show_warnings.setChecked(current.show_method_warnings)
        self.export_dir = QLineEdit(current.default_export_dir)
        self.log_level = QComboBox()
        self.log_level.addItems(["INFO", "WARNING", "ERROR"])
        self.log_level.setCurrentText(current.log_level)
        self.allow_slight_negative = QCheckBox("将轻微负强度列为提示信息")
        self.allow_slight_negative.setChecked(current.allow_slight_negative_intensity)
        apply_help(
            self.allow_slight_negative,
            tooltip="Classify small calibrated negatives as info.",
            status_tip="This does not allow non-positive intensities into log plots or log-based analyses.",
        )
        self.slight_negative_abs_ratio = QDoubleSpinBox()
        self.slight_negative_abs_ratio.setDecimals(8)
        self.slight_negative_abs_ratio.setRange(0.0, 1_000_000.0)
        self.slight_negative_abs_ratio.setSingleStep(0.0001)
        self.slight_negative_abs_ratio.setValue(current.slight_negative_abs_ratio_threshold)
        self.slight_negative_fraction = QDoubleSpinBox()
        self.slight_negative_fraction.setDecimals(8)
        self.slight_negative_fraction.setRange(0.0, 1.0)
        self.slight_negative_fraction.setSingleStep(0.01)
        self.slight_negative_fraction.setValue(current.slight_negative_fraction_threshold)

        save_button = action_button(
            "保存并应用设置",
            role="primary",
            tooltip="Save settings to the default settings path.",
            status_tip="Writes sas_curve_analyzer_settings.json and applies the values to the open window immediately.",
        )
        save_button.clicked.connect(self.save_settings)
        refresh_button = action_button(
            "刷新设置摘要",
            role="secondary",
            tooltip="Reload the settings summary area.",
        )
        refresh_button.clicked.connect(self.refresh_settings_view)
        model_catalog_button = action_button(
            "查看计算模型与公式",
            role="secondary",
            tooltip="Open the model/formula catalog.",
            status_tip="Shows formulas, inputs, outputs, assumptions, limitations, and status for plotting and analysis methods.",
        )
        model_catalog_button.clicked.connect(self.open_model_catalog)

        self.current_settings_view = QTextEdit()
        self.current_settings_view.setReadOnly(True)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow("默认 q 单位", self.q_unit)
        form.addRow("默认图像格式", self.figure_format)
        form.addRow("", self.show_error)
        form.addRow("", self.show_warnings)
        form.addRow("默认导出目录", self.export_dir)
        form.addRow("日志级别", self.log_level)
        form.addRow("", self.allow_slight_negative)
        form.addRow("负强度幅度比例阈值", self.slight_negative_abs_ratio)
        form.addRow("负强度点数比例阈值", self.slight_negative_fraction)

        buttons = FlowLayout()
        buttons.addWidget(save_button)
        buttons.addWidget(refresh_button)
        buttons.addWidget(model_catalog_button)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.current_settings_view, 1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(content))
        self.refresh_settings_view()

    def save_settings(self) -> None:
        settings = AppSettings(
            default_q_unit=self.q_unit.currentText(),
            default_figure_format=self.figure_format.currentText(),
            show_error_bars=self.show_error.isChecked(),
            show_method_warnings=self.show_warnings.isChecked(),
            default_export_dir=self.export_dir.text(),
            log_level=self.log_level.currentText(),
            allow_slight_negative_intensity=self.allow_slight_negative.isChecked(),
            slight_negative_abs_ratio_threshold=float(self.slight_negative_abs_ratio.value()),
            slight_negative_fraction_threshold=float(self.slight_negative_fraction.value()),
        )
        path = save_settings(settings)
        parent = self.parent()
        if parent is not None:
            parent.settings = settings
            parent.settings_info = SettingsLoadInfo(str(path), exists=True, loaded_from_file=True, used_defaults=False)
            parent.import_tab.q_unit.setText(settings.default_q_unit)
            parent.plotting_tab.show_error.setChecked(settings.show_error_bars)
        self.refresh_settings_view()

    def open_model_catalog(self) -> None:
        dialog = ModelCatalogDialog(self)
        dialog.exec()

    def refresh_settings_view(self) -> None:
        parent = self.parent()
        settings = getattr(parent, "settings", None)
        info = getattr(parent, "settings_info", None)
        if settings is None or info is None:
            settings, info = load_settings_with_info()

        lines = [
            "当前设置状态：",
            f"设置文件：{info.path}",
            f"文件存在：{'是' if info.exists else '否'}",
            f"从文件加载：{'是' if info.loaded_from_file else '否'}",
            f"使用默认值：{'是' if info.used_defaults else '否'}",
            f"加载错误：{info.error_message or '无'}",
            "",
            "当前生效值：",
        ]
        labels = {
            "default_q_unit": "默认 q 单位", "default_figure_format": "默认图像格式",
            "show_error_bars": "默认显示误差棒", "show_method_warnings": "方法警告偏好",
            "default_export_dir": "默认导出目录", "log_level": "日志级别",
            "allow_slight_negative_intensity": "轻微负强度分类",
            "slight_negative_abs_ratio_threshold": "负强度幅度比例阈值",
            "slight_negative_fraction_threshold": "负强度点数比例阈值",
        }
        for key, value in asdict(settings).items():
            display_value = ('是' if value else '否') if isinstance(value, bool) else value
            lines.append(f"- {labels.get(key, key)}：{display_value}")
        lines.extend(["", format_model_catalog_summary()])
        self.current_settings_view.setPlainText("\n".join(lines))
