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


def test_import_widget_reuses_detection_preview_and_reads_fresh_on_import(tmp_path, monkeypatch):
    from io import StringIO
    from app.core import io

    _app()
    window = MainWindow()
    path = tmp_path / "curve.csv"
    path.write_text("q,I\n0.01,10\n0.02,5\n0.03,2\n", encoding="utf-8")
    calls = []
    original = io.pd.read_csv

    def parse(source, *args, **kwargs):
        if isinstance(source, StringIO):
            calls.append(source.getvalue())
        return original(source, *args, **kwargs)

    monkeypatch.setattr(io.pd, "read_csv", parse)
    import app.ui.import_tab as import_tab_module
    monkeypatch.setattr(import_tab_module.QFileDialog, "getOpenFileName", lambda *_args: (str(path), ""))
    try:
        tab = window.import_tab
        tab.choose_file()
        assert len(calls) == 1  # Detection and initial preview share one event.
        tab.import_curve()
        assert len(calls) == 2  # A later import always observes current bytes.
        assert len(window.project.curves) == 1
        path.write_text("q,I\n0.01,100\n0.02,5\n0.03,2\n", encoding="utf-8")
        tab.refresh_import_preview()
        assert len(calls) == 3
    finally:
        window.close()


def test_gui_import_observes_same_size_rewrite_with_restored_timestamp(tmp_path, monkeypatch):
    import os
    from app.core.io import TableReadCache
    import app.ui.import_tab as import_tab_module

    _app()
    window = MainWindow()
    path = tmp_path / "curve.csv"
    path.write_text("q,I\n0.01,10\n0.02,5\n0.03,2\n", encoding="utf-8")
    original = path.stat()
    signature = TableReadCache._signature(path)
    # Model Windows creation-time semantics also on Unix CI.
    monkeypatch.setattr(TableReadCache, "_signature", staticmethod(lambda _path: signature))
    monkeypatch.setattr(import_tab_module.QFileDialog, "getOpenFileName", lambda *_args: (str(path), ""))
    try:
        window.import_tab.choose_file()
        path.write_text("q,I\n0.01,20\n0.02,5\n0.03,2\n", encoding="utf-8")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        assert path.stat().st_size == original.st_size
        window.import_tab.import_curve()
        curve = window.project.curves[0]
        assert curve.intensity[0] == 20
    finally:
        window.close()


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
