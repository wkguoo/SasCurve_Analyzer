from __future__ import annotations

from pathlib import Path

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QGroupBox, QLabel, QMessageBox, QTextEdit, QVBoxLayout, QWidget

from app.core.export import (
    export_curve_csv,
    export_feature_table,
    export_first_hand_transform_csv,
    export_origin_long_csv,
    export_origin_matrix_csv,
    origin_long_guide_path,
)
from app.core.records import create_history_record
from app.core.user_messages import exception_detail, format_user_message, UserMessage
from app.ui.style import action_button


class ExportTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        export_curve_button = action_button(
            "导出当前曲线 CSV",
            role="secondary",
            tooltip="导出当前曲线。",
            status_tip="将当前曲线写为 CSV；不会保存完整项目状态。",
        )
        export_curve_button.clicked.connect(self.export_current_curve)
        export_feature_button = action_button(
            "导出 feature_table.csv",
            role="secondary",
            tooltip="导出特征表。",
            status_tip="汇总当前项目曲线和分析结果为 feature_table.csv。",
        )
        export_feature_button.clicked.connect(self.export_feature_table)
        export_origin_long_button = action_button(
            "导出 Origin 长表",
            role="success",
            tooltip="导出一行一个 q-I 点的 Origin 长表。",
            status_tip="写出 curves_long.csv 和 curves_long_guide.md；适合分组叠图、误差棒、筛选和原位序列分析，不插值、不平滑、不修改曲线。",
        )
        export_origin_long_button.clicked.connect(self.export_origin_long_table)
        export_origin_matrix_button = action_button(
            "导出 Origin 矩阵表",
            role="warning",
            tooltip="导出 q 网格一致时的 Origin 矩阵表。",
            status_tip="仅在所有曲线 q 网格一致时导出 curves_matrix.csv；不自动插值以避免改变原始数据。",
        )
        export_origin_matrix_button.clicked.connect(self.export_origin_matrix_table)
        export_transform_button = action_button(
            "导出当前曲线转换数据 CSV...",
            role="secondary",
            tooltip="导出当前曲线的第一手转换数据宽表。",
            status_tip="写出原始 q/I 及 q²、ln q、ln I(q)、q²I(q)、q⁴I(q) 等确定性变换；不拟合、不加常数、不删除行。",
        )
        export_transform_button.clicked.connect(self.export_current_curve_transform_table)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        basic_group = QGroupBox("基础导出")
        basic_layout = QVBoxLayout(basic_group)
        basic_layout.addWidget(export_curve_button)
        basic_layout.addWidget(export_feature_button)
        basic_layout.addWidget(export_origin_long_button)
        basic_layout.addWidget(export_origin_matrix_button)

        transform_group = QGroupBox("第一手转换数据")
        transform_layout = QVBoxLayout(transform_group)
        transform_note = QLabel("导出原始 q/I 与 q²、ln q、ln I(q)、q²I(q)、q⁴I(q) 等确定性变换列；不包含拟合参数，不删除原始行。")
        transform_note.setWordWrap(True)
        transform_layout.addWidget(transform_note)
        transform_layout.addWidget(export_transform_button)

        layout.addWidget(basic_group)
        layout.addWidget(transform_group)
        layout.addWidget(self.output, 1)

    def _choose_folder(self) -> Path | None:
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹", self.main_window.settings.default_export_dir)
        return Path(folder) if folder else None

    def _confirm_overwrite(self, path: Path) -> bool:
        if not path.exists():
            return True
        response = QMessageBox.question(
            self,
            "确认覆盖导出文件",
            f"目标文件已存在:\n{path}\n\n是否覆盖这个旧结果文件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return response == QMessageBox.Yes

    def export_current_curve(self) -> None:
        curve = self.main_window.current_curve()
        folder = self._choose_folder()
        if curve is None or folder is None:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="曲线 CSV 未导出",
                        what_happened="当前曲线 CSV 导出没有执行。",
                        facts=(
                            f"current_curve is None: {curve is None}。",
                            f"export folder is None: {folder is None}。",
                        ),
                        severity="warning",
                    )
                )
            )
            return
        target = folder / f"{curve.name}_curve.csv"
        if not self._confirm_overwrite(target):
            self.output.setPlainText(f"已取消导出，未覆盖已有文件:\n{target}")
            return
        try:
            path = export_curve_csv(curve, target)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="曲线 CSV 导出失败",
                        what_happened="当前曲线没有写入 CSV 文件。",
                        facts=(f"curve_id：{curve.curve_id}。", f"target_folder：{folder}。"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(
            create_history_record("export_curve_csv", input_ids=[curve.curve_id], parameters={"path": str(path), "format": "csv"})
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已导出: {path}")

    def export_feature_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        target = folder / "feature_table.csv"
        if not self._confirm_overwrite(target):
            self.output.setPlainText(f"已取消导出，未覆盖已有文件:\n{target}")
            return
        try:
            path = export_feature_table(self.main_window.project.curves, self.main_window.project.analysis_results, target)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="feature_table.csv 导出失败",
                        what_happened="项目特征表没有写入 CSV 文件。",
                        facts=(
                            f"curve_count：{len(self.main_window.project.curves)}。",
                            f"analysis_count：{len(self.main_window.project.analysis_results)}。",
                            f"target_folder：{folder}。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(create_history_record("export_feature_table", parameters={"path": str(path), "format": "csv"}))
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已导出: {path}")

    def export_origin_long_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        target = folder / "curves_long.csv"
        if not self._confirm_overwrite(target):
            self.output.setPlainText(f"已取消导出，未覆盖已有文件:\n{target}")
            return
        try:
            path = export_origin_long_csv(self.main_window.project.curves, target)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Origin 长表导出失败",
                        what_happened="`curves_long.csv` 没有写入导出文件夹。",
                        facts=(f"curve_count：{len(self.main_window.project.curves)}。", f"target_folder：{folder}。"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        guide_path = origin_long_guide_path(path)
        self.main_window.project.add_history_record(
            create_history_record(
                "export_origin_long_csv",
                parameters={"path": str(path), "guide_path": str(guide_path), "format": "csv", "curve_count": len(self.main_window.project.curves)},
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已导出 Origin 长表:\n{path}\n说明文档:\n{guide_path}")

    def export_current_curve_transform_table(self) -> None:
        curve = self.main_window.current_curve()
        folder = self._choose_folder()
        if curve is None or folder is None:
            self.output.setPlainText("当前曲线转换数据 CSV 未导出：没有当前曲线或没有选择导出文件夹。")
            return
        target = folder / f"{curve.name}_transformed_data.csv"
        if not self._confirm_overwrite(target):
            self.output.setPlainText(f"已取消导出，未覆盖已有文件:\n{target}")
            return
        try:
            path = export_first_hand_transform_csv(curve, target)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="当前曲线转换数据 CSV 导出失败",
                        what_happened="当前曲线第一手转换数据宽表没有写入 CSV 文件。",
                        facts=(f"curve_id：{curve.curve_id}。", f"target_folder：{folder}。"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(
            create_history_record("export_first_hand_transform_csv", input_ids=[curve.curve_id], parameters={"path": str(path), "format": "csv"})
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(
            "已导出当前曲线转换数据 CSV："
            f"{path}\n"
            "列包括 q、I(q)、q²、ln q、log10 q、ln I(q)、log10 I(q)、q²I(q)、q⁴I(q)。"
            "无定义 log 值保留为空/NaN；未做拟合、平滑或加常数。"
        )

    def export_origin_matrix_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        target = folder / "curves_matrix.csv"
        if not self._confirm_overwrite(target):
            self.output.setPlainText(f"已取消导出，未覆盖已有文件:\n{target}")
            return
        try:
            path, warnings = export_origin_matrix_csv(self.main_window.project.curves, target)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Origin 矩阵表导出失败",
                        what_happened="`curves_matrix.csv` 没有写入导出文件夹。",
                        facts=(f"curve_count：{len(self.main_window.project.curves)}。", f"target_folder：{folder}。"),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(
            create_history_record(
                "export_origin_matrix_csv",
                parameters={"path": None if path is None else str(path), "format": "csv", "curve_count": len(self.main_window.project.curves)},
                warnings=warnings,
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        if path is None:
            self.output.setPlainText("未导出 Origin 矩阵表:\n" + "\n".join(warnings))
        else:
            self.output.setPlainText(f"已导出 Origin 矩阵表: {path}")
