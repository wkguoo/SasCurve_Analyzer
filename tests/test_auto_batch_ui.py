import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def test_main_window_exposes_auto_batch_tab(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        assert tab.run_button.text() == "开始全自动分析并导出"
        assert tab.cancel_button.text() == "取消"
        assert not tab.cancel_button.isEnabled()
        tab.input_dir.setText(str(tmp_path / "missing"))
        tab.start_run()
        assert "有效的数据文件夹" in tab.output.toPlainText()
        assert window.advanced_workspace_tab.tabs.indexOf(tab) >= 0
    finally:
        window.close()


def test_cancel_control_sets_worker_cancellation_request(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        tab = window.auto_batch_tab
        from app.ui.auto_batch_tab import BatchWorker
        from app.core.auto_batch_schema import AutoBatchConfig

        tab.worker = BatchWorker(tmp_path, tmp_path, AutoBatchConfig(batch_id="demo"))
        tab.cancel_button.setEnabled(True)
        tab.cancel_run()

        assert tab.worker.cancellation_requested()
        assert not tab.cancel_button.isEnabled()
        assert "安全取消" in tab.output.toPlainText()
    finally:
        window.close()
