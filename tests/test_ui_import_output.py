from __future__ import annotations

import os
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.data_model import CurveData
from app.core.project import ProjectState
from app.ui.import_tab import ImportTab
from app.ui.records_tab import RecordsTab


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _window() -> SimpleNamespace:
    project = ProjectState()
    return SimpleNamespace(
        settings=SimpleNamespace(default_q_unit="A^-1"),
        project=project,
        add_curve=project.add_curve,
        records_tab=SimpleNamespace(refresh=lambda: None),
        mark_project_dirty=lambda: None,
    )


def test_import_filter_note_tracks_enabled_range_and_unit(qt_app):
    tab = ImportTab(_window())
    try:
        assert tab._q_range_filter_settings() == (True, 0.01, 0.05)
        assert "仅保留 0.01 ≤ q ≤ 0.05 A^-1" in tab.q_range_note.text()
        assert "含端点" in tab.q_range_note.text()
        assert "范围外数据点不导入" in tab.q_range_note.text()
        assert "源文件不修改" in tab.q_range_note.text()

        tab.import_q_max.setValue(0.04)
        tab.q_unit.setText("nm^-1")
        assert "0.01 ≤ q ≤ 0.04 nm^-1" in tab.q_range_note.text()
        tab.limit_q_range.setChecked(False)
        assert "筛选已关闭" in tab.q_range_note.text()
        assert tab._q_range_filter_settings() == (False, None, None)
        assert not tab.import_q_min.isEnabled()
        assert not tab.import_q_max.isEnabled()
    finally:
        tab.close()


@pytest.mark.parametrize("filter_enabled", [True, False])
def test_import_retains_range_semantics_source_and_history(qt_app, tmp_path, filter_enabled):
    path = tmp_path / "curve.csv"
    source = b"q,I\n0.005,50\n0.01,40\n0.03,30\n0.05,20\n0.06,10\n"
    path.write_bytes(source)
    window = _window()
    tab = ImportTab(window)
    try:
        tab.selected_file = path
        tab.limit_q_range.setChecked(filter_enabled)
        tab.import_curve()

        assert len(window.project.curves) == 1
        curve = window.project.curves[0]
        expected = [0.01, 0.03, 0.05] if filter_enabled else [0.005, 0.01, 0.03, 0.05, 0.06]
        np.testing.assert_allclose(curve.q, expected)
        assert curve.source_file == str(path)
        assert path.read_bytes() == source
        record = window.project.history_records[-1]
        assert record.action_type == "import_curve"
        assert record.output_ids == [curve.curve_id]
        assert record.parameters["q_range_filter_enabled"] is filter_enabled
        assert record.parameters["raw_point_count"] == 5
        assert record.parameters["imported_point_count"] == len(expected)
        if filter_enabled:
            assert record.parameters["q_range_filter_min"] == 0.01
            assert record.parameters["q_range_filter_max"] == 0.05
            assert record.parameters["filtered_out_point_count"] == 2
    finally:
        tab.close()


def test_records_distinguishes_same_name_and_preserves_real_selected_id(qt_app):
    window = _window()
    first = CurveData.create("same-name", [0.01, 0.02], [3, 2], q_unit="nm^-1", intensity_unit="cm^-1")
    second = CurveData.create("same-name", [0.02, 0.03], [4, 1], q_unit="nm^-1", intensity_unit="cm^-1")
    first.curve_id = "abcdef00-aaaa-4000-8000-000000000001"
    second.curve_id = "abcdef00-bbbb-4000-8000-000000000002"
    window.project.add_curve(first)
    window.project.add_curve(second)
    tab = RecordsTab(window)
    try:
        labels = [tab.source_selector.itemText(index) for index in range(2)]
        assert labels[0] != labels[1]
        assert all("same-name" in label and "nm^-1" in label and "cm^-1" in label for label in labels)
        assert first.curve_id[:10] in labels[0]
        assert second.curve_id[:10] in labels[1]
        assert tab.source_selector.itemData(0) == first.curve_id
        assert tab.source_selector.itemData(1) == second.curve_id

        tab.source_selector.setCurrentIndex(1)
        window.project.curves.reverse()
        tab.refresh_sources()
        assert tab.source_selector.currentData() == second.curve_id
        tab.mark_selected_source()
        assert window.project.formal_records[-1].source_id == second.curve_id
        assert window.project.history_records[-1].input_ids == [second.curve_id]
        assert tab.source_selector.currentData() == second.curve_id
    finally:
        tab.close()
