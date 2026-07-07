from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QPushButton

from app.core.data_model import CurveData
from app.ui.main_window import MainWindow
from app.ui.style import action_button, apply_help, build_app_stylesheet


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_action_button_sets_importance_role_and_tooltip() -> None:
    _app()
    button = action_button(
        "导入曲线",
        role="primary",
        tooltip="读取当前选择的数据文件。",
        status_tip="主操作：导入当前文件并记录历史。",
    )

    assert button.property("uiRole") == "primary"
    assert button.toolTip() == "读取当前选择的数据文件。"
    assert button.statusTip() == "主操作：导入当前文件并记录历史。"
    assert button.whatsThis() == "主操作：导入当前文件并记录历史。"
    assert button.toolTipDuration() == 7000


def test_apply_help_keeps_tooltip_short_and_moves_detail_to_status_tip() -> None:
    _app()
    button = QPushButton("保存项目")

    apply_help(
        button,
        tooltip="保存项目状态。",
        status_tip="重要：写出 project.json 和曲线数据，便于后续复现。",
    )

    assert button.toolTip() == "保存项目状态。"
    assert button.statusTip().startswith("重要：")
    assert button.whatsThis() == button.statusTip()


def test_build_app_stylesheet_defines_tooltips_and_button_roles() -> None:
    stylesheet = build_app_stylesheet()

    assert "QToolTip" in stylesheet
    assert 'QPushButton[uiRole="primary"]' in stylesheet
    assert 'QPushButton[uiRole="danger"]' in stylesheet


def test_refresh_curve_list_preserves_current_selection_by_default() -> None:
    _app()
    window = MainWindow()
    try:
        for index in range(3):
            window.add_curve(CurveData.create(name=f"curve-{index}", q=[0.1, 0.2], intensity=[1.0, 2.0]))

        window.curve_list.setCurrentRow(2)
        window.refresh_curve_list()

        assert window.curve_list.currentRow() == 2
        assert window.current_curve().name == "curve-2"
    finally:
        window.close()


def test_export_tab_exposes_origin_export_buttons() -> None:
    _app()
    window = MainWindow()
    try:
        labels = {button.text() for button in window.export_tab.findChildren(QPushButton)}

        assert "导出 Origin 长表" in labels
        assert "导出 Origin 矩阵表" in labels
    finally:
        window.close()


def test_combo_boxes_use_researcher_labels_with_core_keys_in_user_data() -> None:
    _app()
    window = MainWindow()
    try:
        combos = [
            window.analysis_tab.analysis_type,
            window.plotting_tab.plot_type,
            window.batch_tab.comparison_type,
            window.records_tab.source_type,
            window.advanced_tab.transform_type,
        ]
        for combo in combos:
            visible_labels = [combo.itemText(index) for index in range(combo.count())]
            assert all("_" not in label for label in visible_labels)
            assert all(combo.itemData(index) for index in range(combo.count()))

        assert window.analysis_tab.analysis_type.currentData() == "guinier"
        assert window.plotting_tab.plot_type.currentData() == "linear"
        assert window.batch_tab.comparison_type.currentData() == "difference"
    finally:
        window.close()


def test_deep_analysis_controls_are_visually_separated_from_standard_analysis() -> None:
    _app()
    window = MainWindow()
    try:
        groups = {group.title() for group in window.analysis_tab.findChildren(QGroupBox)}
        assert "深度分析参数" in groups
    finally:
        window.close()


def test_experimental_advanced_controls_are_disabled_by_default() -> None:
    _app()
    window = MainWindow()
    try:
        curve = CurveData.create(name="curve", q=[0.1, 0.2, 0.3], intensity=[10.0, 8.0, 6.0])
        window.add_curve(curve)

        assert not window.advanced_tab.pr_button.isEnabled()
        assert not window.advanced_tab.corr_button.isEnabled()
        window.advanced_tab.pr_button.click()
        window.advanced_tab.corr_button.click()
        assert window.project.analysis_results == []
    finally:
        window.close()
