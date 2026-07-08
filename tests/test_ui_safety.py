from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.data_model import CurveData
import app.ui.batch_tab as batch_tab_module
import app.ui.export_tab as export_tab_module
from app.ui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_export_current_curve_cancel_does_not_overwrite_existing_file(tmp_path: Path, monkeypatch) -> None:
    _app()
    window = MainWindow()
    target = tmp_path / "curve_curve.csv"
    target.write_text("old result\n", encoding="utf-8")
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(export_tab_module.QFileDialog, "getExistingDirectory", lambda *_args, **_kwargs: str(tmp_path))
        monkeypatch.setattr(window.export_tab, "_confirm_overwrite", lambda _path: False, raising=False)

        window.export_tab.export_current_curve()

        assert target.read_text(encoding="utf-8") == "old result\n"
        assert "取消" in window.export_tab.output.toPlainText()
    finally:
        window.close()


def test_save_project_to_suspicious_folder_cancel_does_not_write_project(tmp_path: Path, monkeypatch) -> None:
    _app()
    window = MainWindow()
    (tmp_path / "raw_curve.csv").write_text("q,I\n0.1,10\n", encoding="utf-8")
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(window, "_confirm_project_folder_write", lambda _folder, _reasons: False, raising=False)

        result = window.save_project_to_folder(tmp_path)

        assert result is None
        assert not (tmp_path / "project.json").exists()
        assert not (tmp_path / "curves").exists()
    finally:
        window.close()


def test_batch_compare_failure_is_shown_without_traceback() -> None:
    _app()
    window = MainWindow()
    try:
        window.add_curve(CurveData.create(name="low_q", q=[0.1, 0.2], intensity=[10, 20]))
        window.add_curve(CurveData.create(name="high_q", q=[0.5, 0.6], intensity=[5, 6]))
        window.batch_tab.curve_a.setCurrentIndex(0)
        window.batch_tab.curve_b.setCurrentIndex(1)

        window.batch_tab.compare_selected()

        text = window.batch_tab.output.toPlainText()
        assert "比较失败" in text
        assert "overlapping q range" in text
        assert window.project.comparison_results == []
    finally:
        window.close()


def test_export_sequence_index_failure_is_shown_without_traceback(tmp_path: Path, monkeypatch) -> None:
    _app()
    window = MainWindow()
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(
            batch_tab_module.QFileDialog,
            "getSaveFileName",
            lambda *_args, **_kwargs: (str(tmp_path / "sequence_index.csv"), "CSV files (*.csv)"),
        )

        def raise_export_error(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(batch_tab_module, "export_sequence_index_csv", raise_export_error)

        window.batch_tab.export_sequence_index()

        text = window.batch_tab.output.toPlainText()
        assert "序列索引" in text
        assert "disk full" in text
    finally:
        window.close()
