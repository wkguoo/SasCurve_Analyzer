from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.batch_import import create_in_situ_group, import_in_situ_series, infer_curve_columns
from app.core.import_preview import format_import_preview, preview_curve_file
from app.core.io import load_curve
from app.core.records import create_history_record
from app.core.transforms import convert_q_unit
from app.core.user_messages import exception_detail, format_user_message, UserMessage
from app.ui.style import action_button, apply_help


class ImportTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.selected_file: Path | None = None

        self.file_label = QLabel("未选择文件")
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        apply_help(
            self.file_label,
            tooltip="当前选择的数据文件路径。",
            status_tip="选择文件后会显示完整路径，并尝试自动识别列名和单位。",
        )
        choose_button = action_button(
            "选择数据文件",
            role="secondary",
            tooltip="选择单条 SAS 曲线文件。",
            status_tip="支持 csv、txt、dat；选择后自动识别 q、I(q) 和可选误差列。",
        )
        choose_button.clicked.connect(self.choose_file)

        self.q_column = QLineEdit("q")
        self.intensity_column = QLineEdit("I")
        self.error_column = QLineEdit("")
        self.error_column.setPlaceholderText("留空表示无误差列")
        self.q_unit = QLineEdit(self.main_window.settings.default_q_unit)
        self.intensity_unit = QLineEdit("cm^-1")
        self.limit_q_range = QCheckBox("导入时限制 q 范围")
        self.limit_q_range.setChecked(True)
        self.import_q_min = QDoubleSpinBox()
        self.import_q_max = QDoubleSpinBox()
        for spinbox, value in ((self.import_q_min, 0.01), (self.import_q_max, 0.05)):
            spinbox.setDecimals(6)
            spinbox.setRange(0.0, 1_000_000.0)
            spinbox.setSingleStep(0.001)
            spinbox.setValue(value)
        self.limit_q_range.toggled.connect(self._sync_q_range_filter_enabled)
        self._sync_q_range_filter_enabled(self.limit_q_range.isChecked())
        apply_help(
            self.q_column,
            tooltip="q 列名。",
            status_tip="填写散射矢量 q 的列名；自动识别结果可手动覆盖。",
        )
        apply_help(
            self.intensity_column,
            tooltip="I(q) 列名。",
            status_tip="填写强度列名；导入要求该列为数值型一维强度数据。",
        )
        apply_help(
            self.error_column,
            tooltip="误差列，可留空。",
            status_tip="填写 error/sigma/std 等误差列名；没有误差列时保持为空。",
        )
        apply_help(
            self.q_unit,
            tooltip="q 单位。",
            status_tip="当前支持 A^-1 与 nm^-1；单位转换会生成新曲线，不修改原始数据。",
        )
        apply_help(
            self.intensity_unit,
            tooltip="强度单位。",
            status_tip="记录强度单位用于导出和报告；不会执行强度校准。",
        )

        apply_help(
            self.limit_q_range,
            tooltip="导入时只保留指定 raw q 范围内的数据点。",
            status_tip="启用后，导入时只保留 raw q 在 q_min 到 q_max 之间的数据点；不会修改源文件。",
        )
        apply_help(
            self.import_q_min,
            tooltip="导入过滤下限，默认 0.01。",
            status_tip="启用 q 范围限制时，保留 q >= q_min 的点。",
        )
        apply_help(
            self.import_q_max,
            tooltip="导入过滤上限，默认 0.05。",
            status_tip="启用 q 范围限制时，保留 q <= q_max 的点。",
        )

        import_button = action_button(
            "导入曲线",
            role="primary",
            tooltip="导入当前文件。",
            status_tip="主操作：读取当前选择的数据文件，创建曲线并写入历史记录。",
        )
        import_button.clicked.connect(self.import_curve)
        preview_button = action_button(
            "预览/诊断当前文件",
            role="secondary",
            tooltip="导入前预览数据和基础诊断。",
            status_tip="读取前几行、列映射、q/I 范围、NaN、重复 q、负强度和 error 异常；不会修改原始文件。",
        )
        preview_button.clicked.connect(self.refresh_import_preview)
        batch_button = action_button(
            "批量导入曲线文件",
            role="success",
            tooltip="批量导入序列文件。",
            status_tip="适合 in situ 序列；会自然排序、推断列名并创建曲线组。",
        )
        batch_button.clicked.connect(self.import_batch_files)

        convert_to_nm_button = action_button(
            "当前曲线 q 转为 nm^-1",
            role="secondary",
            tooltip="生成 nm^-1 副本。",
            status_tip="非破坏性转换：创建新曲线，保留原始导入数据。",
        )
        convert_to_nm_button.clicked.connect(lambda: self.convert_current("nm^-1"))
        convert_to_a_button = action_button(
            "当前曲线 q 转为 A^-1",
            role="secondary",
            tooltip="生成 A^-1 副本。",
            status_tip="非破坏性转换：创建新曲线，保留原始导入数据。",
        )
        convert_to_a_button.clicked.connect(lambda: self.convert_current("A^-1"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.preview_output = QTextEdit()
        self.preview_output.setReadOnly(True)

        file_row = QHBoxLayout()
        file_row.addWidget(choose_button)
        file_row.addWidget(self.file_label, 1)

        form = QFormLayout()
        form.addRow("q 列", self.q_column)
        form.addRow("I(q) 列", self.intensity_column)
        form.addRow("error/sigma 列，可留空", self.error_column)
        form.addRow("q 单位", self.q_unit)
        form.addRow("强度单位", self.intensity_unit)

        form.addRow("", self.limit_q_range)
        form.addRow("q_min", self.import_q_min)
        form.addRow("q_max", self.import_q_max)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(file_row)
        layout.addLayout(form)
        layout.addWidget(preview_button)
        layout.addWidget(self.preview_output, 1)
        layout.addWidget(import_button)
        layout.addWidget(batch_button)
        layout.addWidget(convert_to_nm_button)
        layout.addWidget(convert_to_a_button)
        layout.addWidget(self.log, 1)

    def _sync_q_range_filter_enabled(self, enabled: bool) -> None:
        self.import_q_min.setEnabled(enabled)
        self.import_q_max.setEnabled(enabled)

    def _q_range_filter_settings(self) -> tuple[bool, float | None, float | None]:
        enabled = self.limit_q_range.isChecked()
        return enabled, self.import_q_min.value() if enabled else None, self.import_q_max.value() if enabled else None

    def _q_range_history_parameters(self, curve) -> dict[str, object]:
        enabled, q_min, q_max = self._q_range_filter_settings()
        q_filter = curve.metadata.get("import_q_range_filter", {})
        if enabled and q_filter:
            return {
                "q_range_filter_enabled": True,
                "q_range_filter_min": q_filter.get("q_min"),
                "q_range_filter_max": q_filter.get("q_max"),
                "raw_point_count": q_filter.get("raw_point_count"),
                "imported_point_count": q_filter.get("imported_point_count"),
                "filtered_out_point_count": q_filter.get("filtered_out_point_count"),
            }
        return {
            "q_range_filter_enabled": False,
            "q_range_filter_min": q_min,
            "q_range_filter_max": q_max,
            "raw_point_count": int(curve.q.size),
            "imported_point_count": int(curve.q.size),
            "filtered_out_point_count": 0,
        }

    def _q_range_log_text(self, curve) -> str:
        q_filter = curve.metadata.get("import_q_range_filter")
        if not q_filter:
            return "q范围过滤=关闭"
        return (
            "q范围过滤=启用, "
            f"q=[{q_filter.get('q_min')}, {q_filter.get('q_max')}], "
            f"原始点数={q_filter.get('raw_point_count')}, "
            f"导入点数={q_filter.get('imported_point_count')}"
        )

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 SAS 曲线数据",
            "",
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if path:
            self.selected_file = Path(path)
            self._display_selected_file(self.selected_file)
            self._auto_detect_columns(self.selected_file)
            self.refresh_import_preview()

    def _display_selected_file(self, path: Path) -> None:
        self.file_label.setText(path.name)
        apply_help(
            self.file_label,
            tooltip=path.name,
            status_tip=f"完整路径: {path}",
        )

    def _auto_detect_columns(self, path: Path) -> None:
        try:
            from app.core.io import read_table

            columns = infer_curve_columns(read_table(path).columns)
        except Exception as exc:
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="列名自动识别失败",
                        what_happened="软件没有从表头中自动判断出 q、I(q) 或 error/sigma 列。",
                        facts=(
                            "自动识别只匹配软件已知的常见列名别名。",
                            "error/sigma 列是可选列。",
                            "手动填写的列名会覆盖自动识别结果。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="warning",
                    )
                )
            )
            return
        self.q_column.setText(columns.q_column)
        self.intensity_column.setText(columns.intensity_column)
        self.error_column.setText(columns.error_column or "")
        self.q_unit.setText(columns.q_unit)
        self.intensity_unit.setText(columns.intensity_unit)
        self.log.append(
            f"已识别列: q={columns.q_column}, I={columns.intensity_column}, error={columns.error_column or 'None'}, q_unit={columns.q_unit}, I_unit={columns.intensity_unit}"
        )

    def refresh_import_preview(self) -> None:
        if self.selected_file is None:
            self.preview_output.setPlainText("请先选择 csv、txt 或 dat 文件。")
            return
        error_text = self.error_column.text().strip()
        limit_q_range, q_min, q_max = self._q_range_filter_settings()
        preview = preview_curve_file(
            self.selected_file,
            q_column=self.q_column.text().strip() or None,
            intensity_column=self.intensity_column.text().strip() or None,
            error_column=error_text if error_text else None,
            q_unit=self.q_unit.text().strip() or None,
            intensity_unit=self.intensity_unit.text().strip() or None,
            limit_q_range=limit_q_range,
            q_min=q_min,
            q_max=q_max,
        )
        self.preview_output.setPlainText(format_import_preview(preview))

    def import_curve(self) -> None:
        if self.selected_file is None:
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="无法导入曲线",
                        what_happened="当前还没有选择要导入的数据文件。",
                        facts=(
                            "当前 selected_file 为空。",
                            "支持的常用输入扩展名为 `.csv`、`.txt`、`.dat`。",
                        ),
                        severity="warning",
                    )
                )
            )
            return

        error_text = self.error_column.text().strip()
        error_column = error_text if error_text else None
        limit_q_range, q_min, q_max = self._q_range_filter_settings()
        try:
            curve = load_curve(
                self.selected_file,
                q_column=self.q_column.text().strip(),
                intensity_column=self.intensity_column.text().strip(),
                error_column=error_column,
                q_unit=self.q_unit.text().strip(),
                intensity_unit=self.intensity_unit.text().strip(),
                limit_q_range=limit_q_range,
                q_min=q_min,
                q_max=q_max,
            )
        except Exception as exc:
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="导入失败",
                        what_happened="当前文件没有成功转换为一条可用的 SAS 曲线。",
                        facts=(
                            "导入要求至少有可解析为数值的 q 列和 I(q) 列。",
                            "导入失败时不会把该文件加入当前项目曲线列表。",
                            "预览/诊断区域会显示当前列映射和读取到的前几行。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return

        self.main_window.add_curve(curve)
        q_range_parameters = self._q_range_history_parameters(curve)
        self.main_window.project.add_history_record(
            create_history_record(
                "import_curve",
                input_ids=[self.selected_file.name],
                output_ids=[curve.curve_id],
                parameters={
                    "q_column": self.q_column.text().strip(),
                    "intensity_column": self.intensity_column.text().strip(),
                    "error_column": error_column,
                    "q_unit": self.q_unit.text().strip(),
                    "intensity_unit": self.intensity_unit.text().strip(),
                    **q_range_parameters,
                },
            )
        )
        self.main_window.records_tab.refresh()
        self.log.append(
            f"导入成功: {curve.name}, 点数={curve.q.size}, "
            f"error={'有' if curve.error is not None else '无'}, {self._q_range_log_text(curve)}"
        )

    def import_batch_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "批量选择 SAS 曲线数据",
            "",
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if not paths:
            return
        start_row = len(self.main_window.project.curves)
        limit_q_range, q_min, q_max = self._q_range_filter_settings()
        result = import_in_situ_series(paths, limit_q_range=limit_q_range, q_min=q_min, q_max=q_max)
        if result.imported_curves:
            group, record = create_in_situ_group(self.main_window.project, result)
            self.main_window.refresh_curve_list(selected_row=start_row)
            summary = result.import_summary
            self.log.append(
                "\n".join(
                    [
                        f"批量导入完成: 总文件数={summary['total_files']}, 成功={summary['imported_count']}, 失败={summary['failed_count']}",
                        f"series_id: {summary.get('series_id')}",
                        f"q column: {summary.get('q_column')}",
                        f"intensity column: {summary.get('intensity_column')}",
                        f"error column: {summary.get('error_column')}",
                        f"q unit: {summary.get('q_unit')}",
                        f"intensity unit: {summary.get('intensity_unit')}",
                        (
                            f"q范围过滤: 启用, q=[{summary.get('q_range_filter_min')}, {summary.get('q_range_filter_max')}]"
                            if summary.get("q_range_filter_enabled")
                            else "q范围过滤: 关闭"
                        ),
                        f"过滤前总点数: {summary.get('raw_total_points')}",
                        f"过滤后总点数: {summary.get('imported_total_points')}",
                        f"过滤掉总点数: {summary.get('filtered_out_total_points')}",
                        f"曲线组: {group.name}",
                        f"history record: {record.record_id}",
                    ]
                )
            )
        if result.failed_files:
            failed_details = "\n".join(f"- {failed['file']}: {failed['error']}" for failed in result.failed_files)
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="批量导入有文件失败",
                        what_happened=f"{len(result.failed_files)} 个文件未能导入；其它成功文件已保留在当前项目中。",
                        facts=(
                            f"成功导入文件数：{len(result.imported_curves)}。",
                            f"失败文件数：{len(result.failed_files)}。",
                            "批量导入允许部分文件失败，已成功导入的曲线不会因此回滚。",
                        ),
                        technical_detail=failed_details,
                        severity="warning",
                    )
                )
            )
            for failed in result.failed_files:
                self.log.append(f"导入失败: {failed['file']}: {failed['error']}")
        if not result.imported_curves:
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="批量导入未成功导入任何曲线",
                        what_happened="本次选择的文件没有生成任何可用曲线。",
                        facts=(
                            "本次 imported_curves 数量为 0。",
                            f"失败文件数：{len(result.failed_files)}。",
                            "当前项目中未新增本次批量导入曲线。",
                        ),
                        severity="error",
                    )
                )
            )

    def convert_current(self, target_unit: str) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.log.append("请先选择一条已导入曲线。")
            return
        try:
            converted = convert_q_unit(curve, target_unit)
        except Exception as exc:
            self.log.append(
                format_user_message(
                    UserMessage(
                        title="单位转换失败",
                        what_happened="当前曲线没有成功生成目标 q 单位的新副本。",
                        facts=(
                            f"目标单位：{target_unit}。",
                            f"当前曲线单位：{curve.q_unit}。",
                            "单位转换成功时会生成新曲线，不会覆盖原曲线。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.replace_current_curve_selection(converted)
        self.main_window.project.add_history_record(
            create_history_record(
                "convert_q_unit",
                input_ids=[curve.curve_id],
                output_ids=[converted.curve_id],
                parameters={"source_unit": curve.q_unit, "target_unit": target_unit},
            )
        )
        self.main_window.records_tab.refresh()
        self.log.append(f"已生成新曲线: {converted.name}; 原始曲线未被修改。")

