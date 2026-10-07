from __future__ import annotations

import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QWhatsThis,
    QWidget,
)

from app.core.data_model import CurveData
from app.ui.help_texts import install_ui_help, refresh_ui_help
from app.ui.main_window import MainWindow
from app.ui.model_catalog_dialog import ModelCatalogDialog
from app.ui.settings_dialog import SettingsDialog


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    widget = MainWindow()
    assert hasattr(widget, "_plain_help_controller")
    yield widget
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)


def _assert_plain_help(widget: QWidget) -> None:
    text = widget.toolTip()
    assert re.search(r"[\u4e00-\u9fff]", text), (type(widget).__name__, widget.objectName(), text)
    assert widget.whatsThis() == text
    assert widget.statusTip() == text


def test_all_product_controls_actions_and_tabs_have_plain_help(window) -> None:
    controls = (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QAbstractItemView, QTextEdit)
    for owner in [window, *window.findChildren(QWidget)]:
        if not type(owner).__module__.startswith("app.ui"):
            continue
        for name, control in vars(owner).items():
            if isinstance(control, controls):
                assert control.toolTip(), (type(owner).__name__, name)
                _assert_plain_help(control)
    for button in window.findChildren(QAbstractButton):
        _assert_plain_help(button)
    for action in window.findChildren(QAction):
        if not action.isSeparator():
            assert re.search(r"[\u4e00-\u9fff]", action.toolTip()), action.text()
            assert action.whatsThis() == action.toolTip()
    for tabs in window.findChildren(QTabWidget):
        for index in range(tabs.count()):
            text = tabs.tabToolTip(index)
            assert re.search(r"[\u4e00-\u9fff]", text), tabs.tabText(index)
            assert tabs.tabWhatsThis(index) == text
    for table in window.findChildren(QTableWidget):
        for column in range(table.columnCount()):
            assert table.horizontalHeaderItem(column).toolTip()


def test_every_static_dropdown_choice_explains_its_meaning(window) -> None:
    for combo in window.findChildren(QComboBox):
        choices = combo.property("plainHelpChoices") or {}
        for index in range(combo.count()):
            text = combo.itemData(index, Qt.ToolTipRole)
            assert text and re.search(r"[\u4e00-\u9fff]", text), (combo.itemText(index), text)
            if choices:
                key = str(combo.itemData(index)) if combo.itemData(index) is not None else combo.itemText(index)
                assert key in choices or combo.itemText(index) in choices, combo.itemText(index)
        if combo.count():
            previous = combo.currentIndex()
            combo.setCurrentIndex(combo.count() - 1)
            assert combo.itemData(combo.currentIndex(), Qt.ToolTipRole) in combo.toolTip()
            combo.setCurrentIndex(previous)
    assert "横坐标" in window.analysis_tab.q_min.toolTip()
    assert "距离" in window.deep_analysis_tab.dmax.toolTip()
    assert "当前不可用" in window.advanced_tab.pr_button.toolTip() or "尚未" in window.advanced_tab.pr_button.toolTip()


def test_new_dialogs_and_cancel_buttons_receive_context_specific_help(window) -> None:
    settings = SettingsDialog(window)
    settings.show()
    QApplication.processEvents()
    for widget in settings.findChildren(QWidget):
        if isinstance(widget, (QAbstractButton, QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit)):
            _assert_plain_help(widget)
    catalog = ModelCatalogDialog(settings)
    catalog.show()
    QApplication.processEvents()
    _assert_plain_help(catalog.catalog_text)
    _assert_plain_help(catalog.findChildren(QAbstractButton)[0])

    message = QMessageBox(window)
    cancel = message.addButton("取消", QMessageBox.RejectRole)
    message.show()
    QApplication.processEvents()
    assert "返回原界面" in cancel.toolTip()
    assert "已完成" in window.auto_batch_tab.cancel_button.toolTip()
    assert cancel.toolTip() != window.auto_batch_tab.cancel_button.toolTip()
    for dialog in (message, catalog, settings):
        dialog.close()
        dialog.deleteLater()


def test_help_refresh_preserves_project_selection_values_and_dynamic_choices(window) -> None:
    window.add_curve(CurveData.create(name="first", q=[0.1, 0.2], intensity=[1.0, 2.0]))
    window.add_curve(CurveData.create(name="second", q=[0.1, 0.2], intensity=[2.0, 4.0]))
    window.curve_list.setCurrentRow(1)
    window.analysis_tab.q_min.setValue(0.15)
    revision = window.project.revision
    selected = window.current_curve().curve_id
    values = {id(combo): combo.currentIndex() for combo in window.findChildren(QComboBox)}
    refresh_ui_help(window)
    install_ui_help(window)
    assert window.project.revision == revision
    assert window.current_curve().curve_id == selected
    assert window.analysis_tab.q_min.value() == 0.15
    assert {id(combo): combo.currentIndex() for combo in window.findChildren(QComboBox)} == values
    window.records_tab.refresh_sources()
    source = window.records_tab.source_selector
    assert source.count() == 2
    assert all(source.itemData(index, Qt.ToolTipRole) for index in range(source.count()))
    assert window.analysis_tab.q_min.lineEdit().whatsThis() == window.analysis_tab.q_min.whatsThis()


def test_dynamic_object_details_survive_refresh_and_later_source_updates(window) -> None:
    combo = window.records_tab.source_selector
    combo.addItem("same name", "full-curve-id")
    detail = "完整编号：full-curve-id\n来源：C:/data/first.csv"
    combo.setItemData(0, detail, Qt.ToolTipRole)
    refresh_ui_help(window)
    first = combo.itemData(0, Qt.ToolTipRole)
    assert "选择" in first and detail in first
    refresh_ui_help(window)
    assert combo.itemData(0, Qt.ToolTipRole) == first
    updated = "完整编号：full-curve-id\n来源：C:/data/second.csv"
    combo.setItemData(0, updated, Qt.ToolTipRole)
    assert updated in combo.itemData(0, Qt.ToolTipRole)
    assert "first.csv" not in combo.itemData(0, Qt.ToolTipRole)
    assert combo.itemData(0) == "full-curve-id"


def test_file_dialog_navigation_and_confirmation_have_help(window) -> None:
    dialog = QFileDialog(window)
    dialog.setOption(QFileDialog.DontUseNativeDialog)
    dialog.show()
    QApplication.processEvents()
    for button in dialog.findChildren(QAbstractButton):
        _assert_plain_help(button)
    for editor in dialog.findChildren(QLineEdit):
        _assert_plain_help(editor)
    dialog.close()
    dialog.deleteLater()


def test_f1_shows_help_for_focused_editor_and_leaves_other_keys_alone(window, monkeypatch) -> None:
    shown = []
    monkeypatch.setattr(QWhatsThis, "showText", lambda position, text, widget: shown.append((text, widget)))
    editor = window.analysis_tab.q_min.lineEdit()
    QApplication.sendEvent(editor, QKeyEvent(QEvent.KeyPress, Qt.Key_F1, Qt.NoModifier))
    assert shown == [(window.analysis_tab.q_min.whatsThis(), editor)]
    controller = window._plain_help_controller
    assert not controller.eventFilter(editor, QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))
    outside = QLineEdit()
    assert not controller.eventFilter(outside, QKeyEvent(QEvent.KeyPress, Qt.Key_F1, Qt.NoModifier))
    outside.deleteLater()


def test_f1_on_tab_bar_explains_current_page(window, monkeypatch) -> None:
    shown = []
    monkeypatch.setattr(QWhatsThis, "showText", lambda position, text, widget: shown.append((text, widget)))
    tabs = window.tabs
    tabs.setCurrentIndex(2)
    bar = tabs.tabBar()
    QApplication.sendEvent(bar, QKeyEvent(QEvent.KeyPress, Qt.Key_F1, Qt.NoModifier))
    assert shown == [(tabs.tabWhatsThis(2), bar)]


def test_unrelated_events_skip_widget_ancestry_checks(window, monkeypatch) -> None:
    controller = window._plain_help_controller
    monkeypatch.setattr(controller, "_belongs_to_root", lambda _widget: pytest.fail("Unrelated event walked the widget tree"))
    for event_type in (QEvent.StyleChange, QEvent.PaletteChange, QEvent.Polish, QEvent.Paint, QEvent.DynamicPropertyChange):
        assert not controller.eventFilter(window, QEvent(event_type))
    editor = window.analysis_tab.q_min.lineEdit()
    assert not controller.eventFilter(editor, QEvent(QEvent.Show))
    assert not controller.eventFilter(editor, QKeyEvent(QEvent.KeyPress, Qt.Key_Left, Qt.NoModifier))


def test_deleted_window_does_not_break_later_application_events(capsys) -> None:
    app = QApplication.instance() or QApplication([])
    widget = MainWindow()
    controller = widget._plain_help_controller
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    outside = QLineEdit()
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_F1, Qt.NoModifier)
    assert controller.eventFilter(outside, event) is False
    QApplication.sendEvent(outside, event)
    QApplication.processEvents()
    assert "Internal C++ object" not in capsys.readouterr().err
    outside.deleteLater()
