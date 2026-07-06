from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.batch_import import create_in_situ_group, import_in_situ_series, infer_curve_columns
from app.core.io import load_curve
from app.core.records import create_history_record
from app.core.transforms import convert_q_unit
from app.ui.style import action_button, apply_help


class ImportTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.selected_file: Path | None = None

        self.file_label = QLabel("未选择文件")
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

        import_button = action_button(
            "导入曲线",
            role="primary",
            tooltip="导入当前文件。",
            status_tip="主操作：读取当前选择的数据文件，创建曲线并写入历史记录。",
        )
        import_button.clicked.connect(self.import_curve)
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

        file_row = QHBoxLayout()
        file_row.addWidget(choose_button)
        file_row.addWidget(self.file_label, 1)

        form = QFormLayout()
        form.addRow("q 列", self.q_column)
        form.addRow("I(q) 列", self.intensity_column)
        form.addRow("error/sigma 列，可留空", self.error_column)
        form.addRow("q 单位", self.q_unit)
        form.addRow("强度单位", self.intensity_unit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(file_row)
        layout.addLayout(form)
        layout.addWidget(import_button)
        layout.addWidget(batch_button)
        layout.addWidget(convert_to_nm_button)
        layout.addWidget(convert_to_a_button)
        layout.addWidget(self.log, 1)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 SAS 曲线数据",
            "",
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if path:
            self.selected_file = Path(path)
            self.file_label.setText(str(self.selected_file))
            self._auto_detect_columns(self.selected_file)

    def _auto_detect_columns(self, path: Path) -> None:
        try:
            from app.core.io import read_table

            columns = infer_curve_columns(read_table(path).columns)
        except Exception as exc:
            self.log.append(f"列名自动识别失败，可手动填写: {exc}")
            return
        self.q_column.setText(columns.q_column)
        self.intensity_column.setText(columns.intensity_column)
        self.error_column.setText(columns.error_column or "")
        self.q_unit.setText(columns.q_unit)
        self.intensity_unit.setText(columns.intensity_unit)
        self.log.append(
            f"已识别列: q={columns.q_column}, I={columns.intensity_column}, error={columns.error_column or 'None'}, q_unit={columns.q_unit}, I_unit={columns.intensity_unit}"
        )

    def import_curve(self) -> None:
        if self.selected_file is None:
            self.log.append("请先选择 csv、txt 或 dat 文件。")
            return

        error_text = self.error_column.text().strip()
        error_column = error_text if error_text else None
        try:
            curve = load_curve(
                self.selected_file,
                q_column=self.q_column.text().strip(),
                intensity_column=self.intensity_column.text().strip(),
                error_column=error_column,
                q_unit=self.q_unit.text().strip(),
                intensity_unit=self.intensity_unit.text().strip(),
            )
        except Exception as exc:
            self.log.append(f"导入失败: {exc}")
            return

        self.main_window.add_curve(curve)
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
                },
            )
        )
        self.main_window.records_tab.refresh()
        self.log.append(f"导入成功: {curve.name}, 点数={curve.q.size}, error={'有' if curve.error is not None else '无'}")

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
        result = import_in_situ_series(paths)
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
                        f"曲线组: {group.name}",
                        f"history record: {record.record_id}",
                    ]
                )
            )
        if result.failed_files:
            for failed in result.failed_files:
                self.log.append(f"导入失败: {failed['file']}: {failed['error']}")
        if not result.imported_curves:
            self.log.append("批量导入未成功导入任何曲线。")

    def convert_current(self, target_unit: str) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.log.append("请先选择一条已导入曲线。")
            return
        try:
            converted = convert_q_unit(curve, target_unit)
        except Exception as exc:
            self.log.append(f"单位转换失败: {exc}")
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

