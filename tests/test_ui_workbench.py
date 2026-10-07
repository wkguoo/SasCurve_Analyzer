from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QPushButton

from app.core.data_model import CurveData
from app.core.project import ProjectState
from app.ui.analysis_tab import AnalysisTab
from app.ui.plotting_tab import PlottingTab


@pytest.fixture
def qt_app():
    app = QApplication.instance() or QApplication([])
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if font_path.exists():
        QFontDatabase.addApplicationFont(str(font_path))
    yield app


def _window(tmp_path: Path) -> SimpleNamespace:
    curve = CurveData.create(
        name="workbench", q=[0.01, 0.02, 0.03, 0.04, 0.05],
        intensity=[10.0, 9.0, 7.0, 5.0, 4.0], q_unit="nm^-1",
    )
    window = SimpleNamespace(
        selected_curve=curve,
        settings=SimpleNamespace(show_error_bars=False, default_export_dir=str(tmp_path)),
        project=ProjectState(),
        records_tab=SimpleNamespace(refresh=lambda: None),
        mark_project_dirty=lambda: None,
    )
    window.current_curve = lambda: window.selected_curve
    return window


def test_empty_plot_removes_previous_curve_and_cursor(qt_app, tmp_path) -> None:
    window = _window(tmp_path)
    tab = PlottingTab(window)
    try:
        assert tab.figure.axes[0].lines
        tab.cursor_label.setText("Coordinates: old value")
        window.selected_curve = None
        tab.refresh()

        assert not tab.figure.axes[0].lines
        assert tab.canvas.figure is tab.figure
        assert tab.figure.canvas is tab.canvas
        assert tab.current_x_limits() is None
        assert tab.cursor_label.text() == "Coordinates: -"
        assert "Import data" in tab.messages.toPlainText()
        assert any("Select a curve" in text.get_text() for text in tab.figure.axes[0].texts)
    finally:
        tab.close()


def test_plot_view_change_clears_cursor(qt_app, tmp_path) -> None:
    tab = PlottingTab(_window(tmp_path))
    try:
        tab.cursor_label.setText("Coordinates: old view")
        tab.plot_type.setCurrentIndex(tab.plot_type.findData("guinier"))
        assert tab.cursor_label.text() == "Coordinates: -"
    finally:
        tab.close()


def test_collapsed_settings_preserve_range_and_real_figure_export(qt_app, tmp_path, monkeypatch) -> None:
    window = _window(tmp_path)
    tab = PlottingTab(window)
    try:
        tab.range_toggle.setChecked(True)
        tab.x_min.setText("0.02")
        tab.x_max.setText("0.04")
        tab.refresh()
        tab.range_toggle.setChecked(False)
        tab.export_toggle.setChecked(True)
        tab.figure_preset.setCurrentIndex(tab.figure_preset.findData("screen"))
        tab.figure_format.setCurrentIndex(tab.figure_format.findData("png"))
        tab.export_toggle.setChecked(False)
        target = tmp_path / "collapsed.png"
        monkeypatch.setattr("app.ui.plotting_tab.QFileDialog.getSaveFileName", lambda *_args: (str(target), ""))

        tab.export_current_figure()

        assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert tab.current_x_limits() == pytest.approx((0.02, 0.04))
        record = window.project.history_records[-1]
        assert record.parameters["axis_x_limits"] == pytest.approx((0.02, 0.04))
        assert record.parameters["preset"] == "screen"
        assert record.parameters["format"] == "png"
        assert tab.x_min.isHidden() and tab.figure_preset.isHidden()
    finally:
        tab.close()


@pytest.mark.parametrize("tab_type", [PlottingTab, AnalysisTab])
def test_workbench_actions_fit_narrow_width(qt_app, tmp_path, tab_type) -> None:
    tab = tab_type(_window(tmp_path))
    try:
        if isinstance(tab, PlottingTab):
            tab.range_toggle.setChecked(True)
            tab.export_toggle.setChecked(True)
        else:
            tab.auto_region_toggle.setChecked(True)
        tab.resize(480, 1000)
        tab.show()
        qt_app.processEvents()

        assert tab.minimumSizeHint().width() <= 480
        assert tab.width() == 480
        for widget in tab.findChildren(QPushButton) + tab.findChildren(QComboBox):
            if widget.isVisible():
                assert widget.geometry().right() < widget.parentWidget().width()
    finally:
        tab.close()


def test_auto_region_table_is_read_only_and_keeps_range_inputs(qt_app, tmp_path) -> None:
    tab = AnalysisTab(_window(tmp_path))
    try:
        tab.q_min.setValue(0.02)
        tab.q_max.setValue(0.04)
        tab.auto_region_toggle.setChecked(True)
        tab.auto_region_toggle.setChecked(False)

        assert tab.auto_region_table.editTriggers() == QAbstractItemView.NoEditTriggers
        assert tab.auto_region_table.selectionBehavior() == QAbstractItemView.SelectRows
        assert tab._current_raw_q_range() == pytest.approx((0.02, 0.04))
        assert tab.analysis_type.parentWidget() is tab
        assert tab.q_min.parentWidget() is tab
        assert tab.q_max.parentWidget() is tab
    finally:
        tab.close()
