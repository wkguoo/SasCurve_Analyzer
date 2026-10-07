"""Exercise the desktop workflow offscreen and save synthetic-data screenshots.

Run with the GUI requirements installed. It never opens the desktop, changes
default settings, or reads experimental input; temporary inputs/projects are
removed after checking. The output folder contains only PNGs and a JSON receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QFileDialog
from shiboken6 import isValid

from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.style import apply_app_theme
from app.core.data_model import CurveData
import app.ui.auto_batch_tab as batch_ui


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".tmp/ui-quality"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    # Qt's Windows offscreen plugin does not enumerate system fonts.
    if not QFontDatabase.families():
        for name in ("msyh.ttc", "segoeui.ttf"):
            font = Path("C:/Windows/Fonts") / name
            if font.exists():
                QFontDatabase.addApplicationFont(str(font))
    apply_app_theme(app)
    window = MainWindow()
    screenshots: list[str] = []
    receipt: dict = {}

    def capture(name: str, widget=window) -> None:
        app.processEvents()
        target = output / f"{name}.png"
        assert widget.grab().save(str(target)), target
        if target.name not in screenshots:
            screenshots.append(target.name)

    window.show()
    try:
        with tempfile.TemporaryDirectory(prefix="sas-ui-") as temporary:
            temporary_path = Path(temporary)
            q = np.geomspace(0.002, 0.2, 180)
            intensity = 100 * np.exp(-(q * 24) ** 2 / 3) + 0.05
            source = temporary_path / "Ti合金_sample_01.csv"
            np.savetxt(source, np.column_stack((q, intensity, intensity * 0.03)),
                       delimiter=",", header="q_A_inv,intensity_cm_inv,sigma", comments="")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            capture("01-import-empty")
            tab = window.import_tab
            tab.selected_file = source
            tab._display_selected_file(source)
            tab._auto_detect_columns(source)
            tab.refresh_import_preview()
            capture("02-import-preview")
            tab.import_curve()
            curve = window.current_curve()
            assert curve is not None
            expected = (q >= 0.01) & (q <= 0.05)
            np.testing.assert_allclose(curve.q, q[expected])
            np.testing.assert_allclose(curve.intensity, intensity[expected])
            receipt["imported_points"] = int(curve.q.size)
            receipt["source_points"] = int(q.size)
            window.data_import_workspace_tab.tabs.setCurrentIndex(1)
            capture("03-data-check")
            window.show_plotting_tab()
            capture("04-workbench")
            window.analysis_tab.fill_current_range()
            window.set_analysis_type("guinier")
            window.analysis_tab.run_analysis()
            assert window.project.analysis_results
            capture("05-analysis")
            window.analysis_tab.auto_region_toggle.setChecked(True)
            window.analysis_tab.detect_auto_regions_for_current_curve()
            capture("06-region-candidates")
            window.analysis_tab.auto_region_toggle.setChecked(False)
            plot = window.plotting_tab
            plot.range_toggle.setChecked(True)
            plot.export_toggle.setChecked(True)
            capture("07-plot-options")
            image_path = temporary_path / "figure.png"
            original_dialog = QFileDialog.getSaveFileName
            QFileDialog.getSaveFileName = lambda *_args, **_kwargs: (str(image_path), "")
            try:
                plot.figure_preset.setCurrentIndex(plot.figure_preset.findData("screen"))
                plot.figure_format.setCurrentIndex(plot.figure_format.findData("png"))
                plot.export_current_figure()
            finally:
                QFileDialog.getSaveFileName = original_dialog
            assert image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            receipt["figure_export"] = "PNG signature verified"
            plot.range_toggle.setChecked(False)
            plot.export_toggle.setChecked(False)
            window.resize(1000, 720)
            app.processEvents()
            assert window.size().width() == 1000
            assert window.curve_workspace_tab.splitter.orientation() == Qt.Vertical
            capture("08-narrow-workbench")
            window.resize(1440, 900)
            window.add_curve(CurveData.create(
                "Ti-alloy_sample_02", curve.q, curve.intensity * 1.1,
                q_unit=curve.q_unit, intensity_unit=curve.intensity_unit,
            ))
            batch = window.batch_tab
            batch.curve_a.setCurrentIndex(0)
            batch.curve_b.setCurrentIndex(1)
            batch.compare_selected()
            assert window.project.comparison_results
            batch.select_all_by_sequence_order()
            batch.average_selected()
            assert len(window.project.curves) == 3
            window.curve_list.setCurrentRow(0)
            receipt["batch_comparison"] = "A/B comparison and derived average created"
            window.tabs.setCurrentWidget(window.advanced_workspace_tab)
            for index in range(window.advanced_workspace_tab.tabs.count()):
                window.advanced_workspace_tab.tabs.setCurrentIndex(index)
                capture(f"09-advanced-{index}")
            window.auto_batch_tab.start_run()
            assert "有效" in window.auto_batch_tab.output.toPlainText()
            batch_input = temporary_path / "batch-input"
            batch_input.mkdir()
            for frame in (1, 2):
                np.savetxt(batch_input / f"Ti_0000{frame}_abs.csv",
                           np.column_stack((q, intensity * frame, intensity * 0.03)),
                           delimiter=",", header="q_A_inv,intensity_cm_inv,sigma", comments="")
            auto = window.auto_batch_tab
            auto.input_dir.setText(str(batch_input))
            auto.output_dir.setText(str(temporary_path / "batch-output"))
            auto.batch_id.setText("ui-check")
            auto.sample_type.setCurrentIndex(auto.sample_type.findData("particle"))
            # Bound this UI smoke check to one existing model. The complete
            # ten-model optimizer contract is covered by the numerical suite.
            original_config = batch_ui.AutoBatchConfig
            batch_ui.AutoBatchConfig = lambda **kwargs: original_config(**kwargs, allowed_models=["sphere"])
            try:
                auto.start_run()
            finally:
                batch_ui.AutoBatchConfig = original_config
            batch_thread = auto.thread
            deadline = time.monotonic() + 60
            while not auto.run_button.isEnabled() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            if not auto.run_button.isEnabled():
                auto.cancel_run()
                if isValid(batch_thread):
                    batch_thread.quit()
                    batch_thread.wait(30000)
                app.processEvents()
                raise RuntimeError("Automatic batch exceeded the UI-check time limit")
            if isValid(batch_thread):
                batch_thread.quit()
                batch_thread.wait(5000)
            assert "结果包：" in auto.output.toPlainText(), auto.output.toPlainText()
            receipt["automatic_batch"] = auto.output.toPlainText().splitlines()[1]
            receipt["automatic_batch_scope"] = "Two synthetic frames; existing sphere model, UI worker and package export"
            assert "failed" not in receipt["automatic_batch"], auto.output.toPlainText()
            capture("09-advanced-3")
            window.show_project_output_tab(0)
            window.records_tab.source_selector.setCurrentIndex(0)
            window.records_tab.mark_selected_source()
            assert window.project.formal_records
            capture("10-records")
            window.show_project_output_tab(1)
            export_folder = temporary_path / "csv-exports"
            export_folder.mkdir()
            original_folder_dialog = QFileDialog.getExistingDirectory
            QFileDialog.getExistingDirectory = lambda *_args, **_kwargs: str(export_folder)
            try:
                window.export_tab.export_current_curve()
                window.export_tab.export_feature_table()
            finally:
                QFileDialog.getExistingDirectory = original_folder_dialog
            assert len(list(export_folder.glob("*.csv"))) >= 2
            receipt["csv_export"] = "Current curve and feature table written"
            capture("11-export")
            window.show_project_output_tab(2)
            capture("12-templates")
            dialog = SettingsDialog(window)
            dialog.show()
            capture("13-settings", dialog)
            dialog.close()
            project_path = temporary_path / "project"
            expected_ids = [item.curve_id for item in window.project.curves]
            window.save_project_to_folder(project_path)
            window.new_project()
            assert window.current_curve() is None
            assert not window.plotting_tab.figure.axes[0].lines
            window.open_project_folder(project_path)
            assert [item.curve_id for item in window.project.curves] == expected_ids
            assert window.project.formal_records
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            receipt["source_unchanged"] = True
            receipt["project_roundtrip"] = "Curve IDs, analysis and formal records retained"
            receipt["minimum_window"] = [
                max(window.minimumWidth(), window.minimumSizeHint().width()),
                max(window.minimumHeight(), window.minimumSizeHint().height()),
            ]
            receipt["screenshots"] = screenshots
            receipt["scope"] = "Synthetic data; Qt offscreen, no desktop interaction or scientific acceptance"
    finally:
        window._mark_project_clean()
        window.close()
        app.processEvents()
    (output / "receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
