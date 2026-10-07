from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from app.core.data_model import CurveData
from app.ui.main_window import MainWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_curve_search_keeps_source_identity_and_selection(tmp_path) -> None:
    app = _app()
    window = MainWindow()
    try:
        for name in ("样品 A", "sample B"):
            window.add_curve(CurveData.create(name=name, q=[0.01, 0.02], intensity=[2, 1]))
        selected = window.current_curve()
        revision = window.project.revision
        window.curve_search.setText("样品")
        assert not window.curve_list.item(0).isHidden()
        assert window.curve_list.item(1).isHidden()
        assert window.current_curve() is selected
        assert window.project.revision == revision
        assert window.curve_list.item(1).data(Qt.UserRole) == selected.curve_id
        assert "1 / 2" in window.curve_count.text()
        window.curve_search.setText("missing")
        assert "没有匹配" in window.sidebar_hint.text()
        window.curve_search.clear()
        assert not window.curve_list.item(1).isHidden()
        window.save_project_to_folder(tmp_path / "project")
        window.open_project_folder(tmp_path / "project")
        assert window.curve_list.count() == 2
        assert "2 个数据点" in window.curve_summary.text()
    finally:
        window._mark_project_clean()
        window.close()
        app.processEvents()


def test_result_summary_keeps_units_warnings_and_source_values() -> None:
    import numpy as np
    from app.core.data_model import AnalysisResult

    _app()
    window = MainWindow()
    try:
        q = np.linspace(0.01, 0.05, 12)
        curve = CurveData.create("summary", q, np.ones(12), q_unit="nm^-1")
        window.add_curve(curve)
        result = AnalysisResult.create(
            curve=curve, analysis_type="plot_analysis:guinier", q_range=(0.01, 0.05),
            results={"plot_type": "guinier", "Rg": 24.123456789, "missing": float("nan")},
            structured_warnings=[{"warning_code": "TEST_LIMIT", "severity": "warning", "message": "模型适用范围需复核"}],
        )
        text = window.analysis_tab._format_result(result)
        assert "nm^-1" in text
        assert text.index("TEST_LIMIT") < text.index("Rg（回转半径）")
        assert "nan" in text
        assert result.results["Rg"] == 24.123456789
        assert np.isnan(result.results["missing"])
    finally:
        window.close()


def test_workbench_adapts_without_hiding_the_plot_behind_controls() -> None:
    app = _app()
    window = MainWindow()
    try:
        window.show_plotting_tab()
        window.resize(1440, 900)
        window.show()
        app.processEvents()
        workspace = window.curve_workspace_tab
        assert workspace.splitter.orientation() == Qt.Horizontal
        window.resize(1000, 720)
        app.processEvents()
        assert window.width() == 1000
        assert workspace.splitter.orientation() == Qt.Vertical
        assert workspace.plotting_group.height() >= 640
        assert window.plotting_tab.canvas.height() >= 220
        area = workspace.findChild(QScrollArea, "QSplitterScroll")
        assert area.verticalScrollBar().maximum() > 0
        window.resize(1440, 900)
        app.processEvents()
        assert workspace.splitter.orientation() == Qt.Horizontal
        assert workspace.plotting_group.minimumHeight() == 0
    finally:
        window.close()
        app.processEvents()


def test_switching_curve_clears_candidates_from_previous_source() -> None:
    import numpy as np

    _app()
    window = MainWindow()
    try:
        q = np.geomspace(0.01, 0.05, 65)
        window.add_curve(CurveData.create("first", q, 100 * np.exp(-(q * 24) ** 2 / 3)))
        window.analysis_tab.detect_auto_regions_for_current_curve()
        assert window.analysis_tab.auto_region_candidates
        window.add_curve(CurveData.create("second", q, np.ones(q.size)))
        assert window.analysis_tab.auto_region_candidates == []
        assert window.analysis_tab.auto_region_table.rowCount() == 0
        assert window.analysis_tab._selected_auto_region() is None
    finally:
        window.close()


def test_automatic_batch_rejects_empty_input_and_prevents_busy_close(tmp_path, monkeypatch) -> None:
    app = _app()
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        output = tmp_path / "should-not-exist"
        tab.output_dir.setText(str(output))
        tab.input_dir.clear()
        tab.start_run()
        assert tab.thread is None
        assert not output.exists()
        assert "有效的数据文件夹" in tab.output.toPlainText()
        monkeypatch.setattr(tab, "is_running", lambda: True)
        tab.start_run()
        assert tab.thread is None
        assert "仍在运行" in tab.output.toPlainText()
        window.show()
        app.processEvents()
        assert not window.close()
        assert window.isVisible()
        assert "等待" in window.statusBar().currentMessage()
    finally:
        monkeypatch.setattr(window.auto_batch_tab, "is_running", lambda: False)
        window.close()
