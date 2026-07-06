from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

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
