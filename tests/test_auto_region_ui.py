from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.data_model import CurveData
from app.ui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_auto_region_detection_handles_no_current_curve() -> None:
    _app()
    window = MainWindow()
    try:
        window.analysis_tab.detect_auto_regions_for_current_curve()

        assert window.project.analysis_results == []
        text = window.analysis_tab.output.toPlainText()
        assert "自动 q 区域识别" in text
        assert "当前没有选中的曲线" in text
    finally:
        window.close()


def test_auto_region_detection_fill_range_and_run_analysis() -> None:
    _app()
    window = MainWindow()
    try:
        q = np.linspace(0.004, 0.06, 80)
        intensity = 100.0 * np.exp(-(q**2) * 10.0**2 / 3.0)
        curve = CurveData.create(name="guinier", q=q, intensity=intensity)
        window.add_curve(curve)

        window.analysis_tab.detect_auto_regions_for_current_curve()

        assert window.analysis_tab.auto_region_table.rowCount() > 0
        assert window.project.analysis_results[-1].analysis_type == "auto_region_detection"

        row = next(
            index
            for index, candidate in enumerate(window.analysis_tab.auto_region_candidates)
            if candidate.region_type == "guinier_candidate" and candidate.fit_ready
        )
        window.analysis_tab.auto_region_table.selectRow(row)
        selected = window.analysis_tab.auto_region_candidates[row]
        window.analysis_tab.fill_selected_auto_region_range()

        assert window.analysis_tab.q_min.value() == pytest.approx(selected.q_start, abs=1e-6)
        assert window.analysis_tab.q_max.value() == pytest.approx(selected.q_end, abs=1e-6)
        assert "auto detected q range" in window.analysis_tab.range_source

        before = len(window.project.analysis_results)
        window.analysis_tab.run_selected_auto_region_analysis()

        assert len(window.project.analysis_results) == before + 1
        assert window.project.analysis_results[-1].results["source_auto_region_id"] == selected.region_id
        assert window.project.analysis_results[-1].results["user_overrode_range"] is False
        assert window.project.analysis_results[-1].q_range == (selected.q_start, selected.q_end)
        assert window.project.history_records[-1].action_type == "auto_region_analysis"
        assert window.is_project_dirty()
        assert selected.region_id in window.records_tab.output.toPlainText()
    finally:
        window.close()


def test_auto_region_detection_uses_full_curve_when_default_range_would_truncate() -> None:
    _app()
    window = MainWindow()
    try:
        q = np.geomspace(0.02, 2.0, 160)
        curve = CurveData.create(name="wide-q", q=q, intensity=2.0e-4 * q**-4)
        window.add_curve(curve)

        assert window.analysis_tab.q_min.value() == pytest.approx(0.0)
        assert window.analysis_tab.q_max.value() == pytest.approx(1.0)
        window.analysis_tab.detect_auto_regions_for_current_curve()

        result = window.project.analysis_results[-1]
        assert result.analysis_type == "auto_region_detection"
        assert result.q_range == (pytest.approx(float(q.min())), pytest.approx(float(q.max())))
        assert "完整 raw q 范围" in window.analysis_tab.output.toPlainText()
        assert window.analysis_tab.q_max.value() == pytest.approx(float(q.max()), abs=1e-6)
    finally:
        window.close()


def test_auto_region_detection_repairs_invalid_range_to_full_curve() -> None:
    _app()
    window = MainWindow()
    try:
        q = np.linspace(0.1, 0.5, 60)
        curve = CurveData.create(name="invalid-range", q=q, intensity=10.0 * q**-2)
        window.add_curve(curve)
        window.analysis_tab.q_min.setValue(0.4)
        window.analysis_tab.q_max.setValue(0.2)

        window.analysis_tab.detect_auto_regions_for_current_curve()

        result = window.project.analysis_results[-1]
        assert result.q_range == (pytest.approx(float(q.min())), pytest.approx(float(q.max())))
        assert "自动改用当前曲线完整 raw q 范围" in window.analysis_tab.output.toPlainText()
    finally:
        window.close()


def test_auto_region_detection_rejects_manual_range_without_curve_overlap() -> None:
    _app()
    window = MainWindow()
    try:
        q = np.linspace(0.1, 0.5, 60)
        curve = CurveData.create(name="no-overlap", q=q, intensity=10.0 * q**-2)
        window.add_curve(curve)
        window.analysis_tab.q_min.setValue(2.0)
        window.analysis_tab.q_max.setValue(3.0)
        before = len(window.project.analysis_results)

        window.analysis_tab.detect_auto_regions_for_current_curve()

        assert len(window.project.analysis_results) == before
        text = window.analysis_tab.output.toPlainText()
        assert "没有与当前曲线 q 范围重叠" in text
    finally:
        window.close()
