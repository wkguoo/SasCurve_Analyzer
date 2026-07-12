"""One-click automated batch analysis GUI."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig, ProgressEvent
from app.core.result_package import export_result_package
from app.ui.style import action_button


class BatchWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(str, str, int, int)
    failed = Signal(str)

    def __init__(self, source: Path, output: Path, config: AutoBatchConfig) -> None:
        super().__init__()
        self.source = source
        self.output = output
        self.config = config
        self._cancel_event = Event()

    @Slot()
    def cancel(self) -> None:
        self._cancel_event.set()

    def cancellation_requested(self) -> bool:
        """Return whether the GUI requested a safe stop."""

        return self._cancel_event.is_set()

    @Slot()
    def run(self) -> None:
        try:
            def report(event: ProgressEvent) -> None:
                self.progress.emit(
                    event.completed_units,
                    event.total_units,
                    f"{event.curve_name or ''} · {event.operation}",
                )

            cache_dir = self.output / f"{self.config.batch_id}_compute_cache"
            result = run_auto_batch(
                self.source,
                self.config,
                progress_callback=report,
                cancel_requested=self.cancellation_requested,
                cache_dir=cache_dir,
            )
            requested_target = self.output / f"{self.config.batch_id}_{result.run_id[:8]}_results"
            target = export_result_package(result, requested_target, detail_level="usable")
            accepted = {AnalysisStatus.SUCCESS, AnalysisStatus.ASSUMPTION_DEPENDENT}
            failed_or_unfinished = {
                AnalysisStatus.FIT_FAILED,
                AnalysisStatus.INVALID,
                AnalysisStatus.CANCELLED,
            }
            success_count = sum(item.status in accepted for item in result.analyses)
            failure_count = (
                sum(item.status in failed_or_unfinished for item in result.analyses)
                + len(result.failed_inputs)
            )
            self.completed.emit(str(target), result.status, success_count, failure_count)
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class AutoBatchTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.input_dir = QLineEdit()
        self.output_dir = QLineEdit(str(Path(main_window.settings.default_export_dir)))
        self.batch_id = QLineEdit("sas_batch")
        self.sample_type = QComboBox()
        for label, value in [
            ("未知/通用", "unknown"),
            ("颗粒", "particle"),
            ("聚合物", "polymer"),
            ("两相", "two_phase"),
            ("层片", "lamellar"),
        ]:
            self.sample_type.addItem(label, value)
        self.effective_q_min = QDoubleSpinBox()
        self.effective_q_min.setRange(0.0, 1_000_000.0)
        self.effective_q_min.setDecimals(6)
        self.effective_q_min.setSingleStep(0.001)
        self.effective_q_min.setValue(0.01)
        self.effective_q_max = QDoubleSpinBox()
        self.effective_q_max.setRange(0.0, 1_000_000.0)
        self.effective_q_max.setDecimals(6)
        self.effective_q_max.setSingleStep(0.001)
        self.effective_q_max.setValue(0.05)
        for control in (self.effective_q_min, self.effective_q_max):
            control.setToolTip("分析前请确认有效 q 范围；默认值为 0.01–0.05 Å⁻¹。")
        self.enable_pr = QCheckBox("启用 P(r)")
        self.enable_correlation = QCheckBox("启用相关函数")
        self.enable_kinetics = QCheckBox("输出描述性线性趋势")
        self.enable_statistics = QCheckBox("输出探索性 PCA/聚类")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        choose_input = action_button(
            "选择数据文件夹",
            role="secondary",
            tooltip="选择只读的校准曲线目录。",
            status_tip="不会修改原始曲线。",
        )
        choose_output = action_button(
            "选择结果位置",
            role="secondary",
            tooltip="选择结果包父目录。",
            status_tip="每次创建新目录，不覆盖已有结果。",
        )
        self.run_button = action_button(
            "开始全自动分析并导出",
            role="primary",
            tooltip="运行全部适用方法并导出结果包。",
            status_tip="后台执行并显示进度。",
        )
        self.cancel_button = action_button(
            "取消",
            role="secondary",
            tooltip="安全停止尚未执行的分析任务。",
            status_tip="已完成部分将保存在带 incomplete 标记的目录中。",
        )
        self.cancel_button.setEnabled(False)
        choose_input.clicked.connect(self.choose_input)
        choose_output.clicked.connect(self.choose_output)
        self.run_button.clicked.connect(self.start_run)
        self.cancel_button.clicked.connect(self.cancel_run)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        input_row = QHBoxLayout()
        output_row = QHBoxLayout()
        q_range_row = QHBoxLayout()
        input_row.addWidget(self.input_dir, 1)
        input_row.addWidget(choose_input)
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(choose_output)
        q_range_row.addWidget(self.effective_q_min)
        q_range_row.addWidget(QLabel("至"))
        q_range_row.addWidget(self.effective_q_max)
        q_range_row.addWidget(QLabel("Å⁻¹"))
        q_range_row.addStretch(1)
        form.addRow("数据文件夹", input_row)
        form.addRow("结果父目录", output_row)
        form.addRow("批次名称", self.batch_id)
        form.addRow("样品类型", self.sample_type)
        form.addRow("有效 q 范围（分析前请确认）", q_range_row)
        layout.addLayout(form)
        for widget in (
            self.enable_pr,
            self.enable_correlation,
            self.enable_kinetics,
            self.enable_statistics,
        ):
            layout.addWidget(widget)
        button_row = QHBoxLayout()
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.output, 1)

    def choose_input(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 SAS 曲线文件夹", self.input_dir.text())
        if path:
            self.input_dir.setText(path)

    def choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择结果父目录", self.output_dir.text())
        if path:
            self.output_dir.setText(path)

    def start_run(self) -> None:
        source = Path(self.input_dir.text().strip())
        output = Path(self.output_dir.text().strip())
        batch_id = self.batch_id.text().strip()
        if not source.is_dir() or not self.output_dir.text().strip() or not batch_id:
            self.output.setPlainText("请填写有效的数据文件夹、结果父目录和批次名称。")
            return
        q_low = self.effective_q_min.value()
        q_high = self.effective_q_max.value()
        if q_low >= q_high:
            self.output.setPlainText("有效 q 范围必须满足 q 最小值 < q 最大值，请在分析前确认。")
            return
        config = AutoBatchConfig(
            batch_id=batch_id,
            sample_type=self.sample_type.currentData(),
            effective_q_range=(q_low, q_high),
            enable_pr=self.enable_pr.isChecked(),
            enable_correlation=self.enable_correlation.isChecked(),
            enable_kinetics=self.enable_kinetics.isChecked(),
            enable_exploratory_statistics=self.enable_statistics.isChecked(),
        )
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.output.setPlainText(
            f"正在分析……有效 q 范围：{q_low:.6g}–{q_high:.6g} Å⁻¹；原始数据不会被修改。"
        )
        self.thread = QThread(self)
        self.worker = BatchWorker(source, output, config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.completed.connect(self.on_completed)
        self.worker.failed.connect(self.on_failed)
        self.worker.completed.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot()
    def cancel_run(self) -> None:
        if self.worker is None:
            return
        self.worker.cancel()
        self.cancel_button.setEnabled(False)
        self.output.setPlainText("正在安全取消……已完成部分将保存为不完整结果。")

    @Slot(int, int, str)
    def on_progress(self, done: int, total: int, message: str) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.progress.setFormat(f"%v/%m · {message}")

    @Slot(str, str, int, int)
    def on_completed(self, path: str, status: str, successes: int, failures: int) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        headings = {
            "cancelled": "分析已取消",
            "completed": "分析完成（全部成功）",
            "completed_with_limitations": "分析完成（存在方法限制）",
            "partial_success": "分析部分成功（存在失败项）",
            "failed": "分析失败",
        }
        heading = headings.get(status, "分析结束")
        self.output.setPlainText(
            f"{heading}。\n状态：{status}\n成功结果：{successes}\n失败或未完成：{failures}\n结果包：{path}"
        )

    @Slot(str)
    def on_failed(self, reason: str) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.output.setPlainText(f"自动分析未完成：{reason}\n原始数据未被修改。")


__all__ = ["AutoBatchTab", "BatchWorker"]
