from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QGroupBox, QPushButton, QTableWidget, QTabWidget

from app.core.data_model import CurveData
from app.ui.main_window import MainWindow
from app.ui.model_catalog_dialog import ModelCatalogDialog
from app.ui.settings_dialog import SettingsDialog
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
        assert "项目另存为..." in labels
        assert "保存项目文件夹" not in labels
    finally:
        window.close()


def test_plot_coordinate_readout_has_independent_row() -> None:
    _app()
    window = MainWindow()
    try:
        assert window.plotting_tab.range_controls.indexOf(window.plotting_tab.cursor_label) == -1
        assert window.plotting_tab.coordinate_row.indexOf(window.plotting_tab.cursor_label) >= 0
        assert window.plotting_tab.cursor_label.wordWrap()
        assert window.plotting_tab.current_x_limits() is None
    finally:
        window.close()


def test_plotting_tab_exposes_figure_export_presets_and_handles_empty_export() -> None:
    _app()
    window = MainWindow()
    try:
        buttons = {button.text(): button for button in window.plotting_tab.findChildren(QPushButton)}

        assert "Export current figure" in buttons
        assert window.plotting_tab.figure_preset.count() == 3
        assert window.plotting_tab.figure_format.count() == 3
        buttons["Export current figure"].click()
        assert "Figure export unavailable" in window.plotting_tab.messages.toPlainText()
        assert "建议操作" not in window.plotting_tab.messages.toPlainText()
    finally:
        window.close()


def test_plot_analysis_link_buttons_switch_tabs_and_types() -> None:
    _app()
    window = MainWindow()
    try:
        window.set_plot_type("loglog")
        plot_buttons = {button.text(): button for button in window.plotting_tab.findChildren(QPushButton)}
        plot_buttons["Use this view for analysis"].click()

        assert window.tabs.currentWidget() is window.analysis_tab
        assert window.analysis_tab.analysis_type.currentData() == "power_law"

        window.set_analysis_type("guinier")
        analysis_buttons = {button.text(): button for button in window.analysis_tab.findChildren(QPushButton)}
        analysis_buttons["查看对应图"].click()

        assert window.tabs.currentWidget() is window.plotting_tab
        assert window.plotting_tab.plot_type.currentData() == "guinier"
    finally:
        window.close()


def test_project_output_uses_nested_tabs_for_low_frequency_pages() -> None:
    _app()
    window = MainWindow()
    try:
        top_level_names = [window.tabs.tabText(index) for index in range(window.tabs.count())]
        assert "历史与正式记录" not in top_level_names
        assert "导出报告" not in top_level_names
        assert "分析模板" not in top_level_names
        assert "项目与输出" in top_level_names

        assert isinstance(window.output_tabs, QTabWidget)
        output_names = [window.output_tabs.tabText(index) for index in range(window.output_tabs.count())]
        assert output_names == ["历史与正式记录", "导出报告", "分析模板"]
    finally:
        window.close()


def test_batch_tab_exposes_sequence_management_table_and_buttons() -> None:
    _app()
    window = MainWindow()
    try:
        window.add_curve(
            CurveData.create(
                name="sample_00001",
                q=[0.1, 0.2],
                intensity=[1, 2],
                metadata={"sequence_order": 0, "frame_label": "00001", "frame_index": 1},
            )
        )
        window.add_curve(
            CurveData.create(
                name="sample_00002",
                q=[0.1, 0.25],
                intensity=[3, 4],
                metadata={"sequence_order": 1, "frame_label": "00002", "frame_index": 2},
            )
        )
        buttons = {button.text() for button in window.batch_tab.findChildren(QPushButton)}
        tables = window.batch_tab.findChildren(QTableWidget)

        assert "刷新序列表" in buttons
        assert "按序列顺序选择全部" in buttons
        assert "从选中行建组" in buttons
        assert "导出序列索引 CSV" in buttons
        assert tables
        assert window.batch_tab.sequence_table.rowCount() == 2
        assert window.batch_tab.sequence_rows[1]["frame_label"] == "00002"
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

        math_labels = []
        for combo in [window.analysis_tab.analysis_type, window.plotting_tab.plot_type, window.advanced_tab.transform_type]:
            math_labels.extend(combo.itemText(index) for index in range(combo.count()))
            for index in range(combo.count()):
                key = combo.itemData(index)
                assert all(symbol not in key for symbol in ["\u00b2", "\u00b3", "\u2074", "\u03b1", "\u03c0"])
        joined = "\n".join(math_labels)
        assert "q^2" not in joined
        assert "q^3" not in joined
        assert "q^4" not in joined
        assert "alpha(q)" not in joined
        assert "2*pi" not in joined
        assert "q\u00b2" in joined
        assert "q\u00b3" in joined
        assert "q\u2074" in joined
        assert "\u03b1(q)" in joined
        assert "2\u03c0/q" in joined
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


def test_analysis_tab_exposes_preflight_button() -> None:
    _app()
    window = MainWindow()
    try:
        buttons = {button.text(): button for button in window.analysis_tab.findChildren(QPushButton)}

        assert "检查当前 q 范围" in buttons
        buttons["检查当前 q 范围"].click()
        assert "分析前 q 范围预检" in window.analysis_tab.output.toPlainText()
        assert "当前没有选中的曲线" in window.analysis_tab.output.toPlainText()
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


def test_settings_dialog_exposes_negative_thresholds_and_model_catalog_button() -> None:
    _app()
    window = MainWindow()
    dialog = SettingsDialog(window)
    try:
        buttons = {button.text() for button in dialog.findChildren(QPushButton)}
        checkbox_labels = {checkbox.text() for checkbox in dialog.findChildren(QCheckBox)}
        spinboxes = dialog.findChildren(QDoubleSpinBox)

        assert "View calculation models and formulas" in buttons
        assert "Allow slight negative calibrated intensities" in checkbox_labels
        assert len(spinboxes) >= 2
    finally:
        dialog.close()
        window.close()


def test_model_catalog_dialog_can_be_instantiated() -> None:
    _app()
    dialog = ModelCatalogDialog()
    try:
        assert dialog.windowTitle() == "Calculation models and formulas"
        assert "Sphere form factor" in dialog.catalog_text.toPlainText()
        assert "P(r) inversion interface" in dialog.catalog_text.toPlainText()
    finally:
        dialog.close()
