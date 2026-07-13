import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def test_main_window_exposes_model_free_auto_batch_defaults(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        assert tab.run_button.text() == "开始模型免费双轨分析"
        assert tab.cancel_button.text() == "取消"
        assert not tab.cancel_button.isEnabled()
        assert tab.effective_q_min.value() == 0.01
        assert tab.effective_q_max.value() == 0.5
        assert not tab.effective_q_min.isEnabled()
        assert not tab.effective_q_max.isEnabled()
        assert tab.model_free_mode.isChecked()
        assert not tab.enable_shape_models.isChecked()
        assert tab.dual_range_mode.isChecked()
        assert tab.enable_bootstrap.isChecked()
        assert tab.enable_range_sensitivity.isChecked()
        assert not tab.enable_pr.isChecked()
        assert not tab.enable_correlation.isChecked()
        assert not tab.enable_kinetics.isChecked()
        assert not tab.enable_statistics.isChecked()
        assert not tab.enable_archives.isChecked()
        tab.input_dir.setText(str(tmp_path / "missing"))
        tab.start_run()
        assert "有效的数据文件夹" in tab.output.toPlainText()
        assert window.advanced_workspace_tab.tabs.indexOf(tab) >= 0
    finally:
        window.close()


def test_gui_builds_explicit_fixed_model_free_config() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        config = tab.build_config()

        assert config.effective_q_range == (0.01, 0.5)
        assert config.enable_shape_models is False
        assert config.range_mode == "dual"
        assert config.enable_bootstrap is True
        assert config.bootstrap_samples == 200
        assert config.bootstrap_seed == 12345
        assert config.bootstrap_mode == "moving_block_residual"
        assert config.enable_range_sensitivity is True
        assert config.sensitivity_boundary_fraction == 0.05
        assert config.enable_pr is False
        assert config.enable_correlation is False
        assert config.enable_kinetics is False
        assert config.enable_exploratory_statistics is False
        assert config.enable_sequence_analysis is False
        assert config.create_archives is False
    finally:
        window.close()


def test_input_preview_reports_series_reference_and_missing_frames(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        for name in (
            "Ti15_00001_scan.csv",
            "Ti15_00002_scan.csv",
            "Ti15_00004_scan.csv",
            "TI15-rt_00001_scan.csv",
        ):
            (tmp_path / name).write_text("q,I\n", encoding="utf-8")

        tab = window.auto_batch_tab
        tab.input_dir.setText(str(tmp_path))
        tab.refresh_input_preview()

        preview = tab.input_preview.text()
        assert "主序列 3 帧" in preview
        assert "独立室温参考 1 条" in preview
        assert "缺失帧：3" in preview
    finally:
        window.close()


def test_cancel_control_sets_worker_cancellation_request(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        from app.core.auto_batch_schema import AutoBatchConfig
        from app.ui.auto_batch_tab import BatchWorker

        tab.worker = BatchWorker(tmp_path, tmp_path, AutoBatchConfig(batch_id="demo"))
        tab.cancel_button.setEnabled(True)
        tab.cancel_run()

        assert tab.worker.cancellation_requested()
        assert not tab.cancel_button.isEnabled()
        assert "安全取消" in tab.output.toPlainText()
    finally:
        window.close()
