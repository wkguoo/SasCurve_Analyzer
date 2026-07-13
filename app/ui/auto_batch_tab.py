"""One-click model-free automated batch analysis GUI."""

from __future__ import annotations

import re
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
from app.core.batch_inputs import discover_curve_files
from app.core.result_package import export_result_package
from app.ui.style import action_button


HARD_Q_RANGE = (0.01, 0.5)
REFERENCE_FILENAME_PATTERN = "-rt_"


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
            target = export_result_package(result, requested_target, detail_level="all")
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
    """GUI entry point for the fixed-boundary, dual-track model-free workflow."""

    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.thread: QThread | None = None
        self.worker: BatchWorker | None = None

        self.input_dir = QLineEdit()
        self.input_dir.setPlaceholderText("选择包含原位帧和可选室温参考曲线的文件夹")
        self.input_dir.editingFinished.connect(self.refresh_input_preview)
        self.input_preview = QLabel("输入预览：尚未选择数据文件夹")
        self.input_preview.setWordWrap(True)

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
        self.effective_q_min.setValue(HARD_Q_RANGE[0])
        self.effective_q_max = QDoubleSpinBox()
        self.effective_q_max.setRange(0.0, 1_000_000.0)
        self.effective_q_max.setDecimals(6)
        self.effective_q_max.setValue(HARD_Q_RANGE[1])
        for control in (self.effective_q_min, self.effective_q_max):
            control.setEnabled(False)
            control.setToolTip("本项目的不可越过分析边界，原始 CSV 不会被裁剪或改写。")

        self.model_free_mode = QCheckBox("模型免费分析（默认开启）")
        self.model_free_mode.setChecked(True)
        self.model_free_mode.setEnabled(False)
        self.enable_shape_models = QCheckBox("球/圆柱/核壳/分形等形状模型（本批次关闭）")
        self.enable_shape_models.setChecked(False)
        self.enable_shape_models.setEnabled(False)
        self.dual_range_mode = QCheckBox("方法专属双轨 q 选区：adaptive + common")
        self.dual_range_mode.setChecked(True)
        self.dual_range_mode.setEnabled(False)

        self.enable_bootstrap = QCheckBox("移动区块残差 bootstrap（200 次，固定种子）")
        self.enable_bootstrap.setChecked(True)
        self.enable_bootstrap.setEnabled(False)
        self.enable_range_sensitivity = QCheckBox("q 区间边界 ±5% 稳健性检查")
        self.enable_range_sensitivity.setChecked(True)
        self.enable_range_sensitivity.setEnabled(False)

        self.enable_pr = QCheckBox("P(r)（默认关闭）")
        self.enable_correlation = QCheckBox("相关函数（默认关闭）")
        self.enable_kinetics = QCheckBox("动力学拟合（默认关闭；无时间/温度映射）")
        self.enable_statistics = QCheckBox("PCA/聚类（默认关闭）")
        self.enable_archives = QCheckBox("生成 ZIP（默认关闭）")
        self.enable_archives.setChecked(False)
        self.enable_archives.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        choose_input = action_button(
            "选择数据文件夹",
            role="secondary",
            tooltip="选择只读的校准曲线目录。",
            status_tip="只扫描受支持的 CSV/TXT/DAT，不修改原始曲线。",
        )
        choose_output = action_button(
            "选择结果位置",
            role="secondary",
            tooltip="选择结果父目录。",
            status_tip="每次创建新结果目录，不覆盖已有结果。",
        )
        self.run_button = action_button(
            "开始模型免费双轨分析",
            role="primary",
            tooltip="在固定 q 边界内运行模型免费方法并导出结果。",
            status_tip="后台执行并显示进度；不自动生成 ZIP。",
        )
        self.cancel_button = action_button(
            "取消",
            role="secondary",
            tooltip="安全停止尚未执行的分析任务。",
            status_tip="已完成部分将保存到带 incomplete 标记的目录中。",
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
        q_range_row.addWidget(QLabel("Å⁻¹（固定硬边界）"))
        q_range_row.addStretch(1)
        form.addRow("数据文件夹", input_row)
        form.addRow("输入序列", self.input_preview)
        form.addRow("结果父目录", output_row)
        form.addRow("批次名称", self.batch_id)
        form.addRow("样品类型", self.sample_type)
        form.addRow("有效 q 范围", q_range_row)
        layout.addLayout(form)
        for widget in (
            self.model_free_mode,
            self.enable_shape_models,
            self.dual_range_mode,
            self.enable_bootstrap,
            self.enable_range_sensitivity,
            self.enable_pr,
            self.enable_correlation,
            self.enable_kinetics,
            self.enable_statistics,
            self.enable_archives,
        ):
            layout.addWidget(widget)
        button_row = QHBoxLayout()
        button_row.addWidget(self.run_button)
        button_row.addWidget(self.cancel_button)
        layout.addLayout(button_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.output, 1)

    def choose_input(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择 SAS 曲线文件夹",
            self.input_dir.text(),
        )
        if path:
            self.input_dir.setText(path)
            self.refresh_input_preview()

    def choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "选择结果父目录",
            self.output_dir.text(),
        )
        if path:
            self.output_dir.setText(path)

    def refresh_input_preview(self) -> None:
        """Preview sequence composition by filename without opening curve contents."""

        source = Path(self.input_dir.text().strip())
        if not source.is_dir():
            self.input_preview.setText("输入预览：文件夹无效或尚未选择")
            return
        try:
            files = discover_curve_files(source)
        except OSError as exc:
            self.input_preview.setText(f"输入预览：无法读取文件列表（{exc}）")
            return

        references = [
            path for path in files if REFERENCE_FILENAME_PATTERN in path.name.lower()
        ]
        series_files = [path for path in files if path not in references]
        frame_numbers: list[int] = []
        for path in series_files:
            match = re.search(r"_(\d{5})_", path.name)
            if match:
                frame_numbers.append(int(match.group(1)))
        unique_frames = sorted(set(frame_numbers))
        missing = (
            sorted(set(range(unique_frames[0], unique_frames[-1] + 1)) - set(unique_frames))
            if unique_frames
            else []
        )
        missing_text = "无" if not missing else ", ".join(str(value) for value in missing)
        unparsed_count = len(series_files) - len(frame_numbers)
        parse_note = f"；未识别帧号 {unparsed_count} 条" if unparsed_count else ""
        self.input_preview.setText(
            f"主序列 {len(series_files)} 帧；独立室温参考 {len(references)} 条；"
            f"缺失帧：{missing_text}{parse_note}"
        )

    def build_config(self) -> AutoBatchConfig:
        """Build the explicit, reproducible model-free GUI configuration."""

        return AutoBatchConfig(
            batch_id=self.batch_id.text().strip(),
            sample_type=self.sample_type.currentData(),
            effective_q_range=HARD_Q_RANGE,
            enable_shape_models=False,
            range_mode="dual",
            enable_bootstrap=True,
            bootstrap_samples=200,
            bootstrap_seed=12345,
            bootstrap_mode="moving_block_residual",
            enable_range_sensitivity=True,
            sensitivity_boundary_fraction=0.05,
            # Dual-track model-free GUI must not silently build sequence
            # trajectories that double-count adaptive + common envelopes.
            enable_sequence_analysis=False,
            enable_pr=self.enable_pr.isChecked(),
            enable_correlation=self.enable_correlation.isChecked(),
            enable_kinetics=self.enable_kinetics.isChecked(),
            enable_exploratory_statistics=self.enable_statistics.isChecked(),
            create_archives=False,
        )

    def start_run(self) -> None:
        source = Path(self.input_dir.text().strip())
        output = Path(self.output_dir.text().strip())
        batch_id = self.batch_id.text().strip()
        if not source.is_dir() or not self.output_dir.text().strip() or not batch_id:
            self.output.setPlainText("请填写有效的数据文件夹、结果父目录和批次名称。")
            return
        config = self.build_config()
        q_low, q_high = config.effective_q_range
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        optional_flags = [
            f"P(r)={'开' if config.enable_pr else '关'}",
            f"相关函数={'开' if config.enable_correlation else '关'}",
            f"动力学={'开' if config.enable_kinetics else '关'}",
            f"PCA/聚类={'开' if config.enable_exploratory_statistics else '关'}",
            f"ZIP={'开' if config.create_archives else '关'}",
            f"序列轨迹={'开' if config.enable_sequence_analysis else '关'}",
        ]
        self.output.setPlainText(
            "正在分析……\n"
            f"硬边界：{q_low:.6g}–{q_high:.6g} Å⁻¹\n"
            f"q 选区：{config.range_mode}（adaptive + common 双轨）\n"
            f"稳健性：边界 ±{config.sensitivity_boundary_fraction:.0%}；"
            f"bootstrap {config.bootstrap_samples} 次"
            f"{'（开）' if config.enable_bootstrap else '（关）'}\n"
            f"形状模型={'开' if config.enable_shape_models else '关'}；"
            + "；".join(optional_flags)
            + "\n原始数据不会被修改。"
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
            f"{heading}。\n状态：{status}\n成功结果：{successes}\n"
            f"失败或未完成：{failures}\n结果目录：{path}"
        )

    @Slot(str)
    def on_failed(self, reason: str) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.output.setPlainText(f"自动分析未完成：{reason}\n原始数据未被修改。")


__all__ = ["AutoBatchTab", "BatchWorker", "HARD_Q_RANGE"]
