from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QTextEdit, QVBoxLayout, QWidget

from app.core.export import export_analysis_bundle, export_curve_csv, export_feature_table, export_origin_long_csv, export_origin_matrix_csv, origin_long_guide_path
from app.core.records import create_history_record
from app.core.report import generate_markdown_report
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
        export_report_button = action_button(
            "导出 Markdown 报告",
            role="primary",
            tooltip="生成 Markdown 报告。",
            status_tip="主操作：导出包含曲线、分析、历史和正式记录的 Markdown 报告。",
        )
        export_report_button.clicked.connect(self.export_report)
        export_bundle_button = action_button(
            "导出完整分析包",
            role="success",
            tooltip="导出完整分析包。",
            status_tip="重要：一次性导出报告、特征表和分析结果文件，适合交付归档。",
        )
        export_bundle_button.clicked.connect(self.export_analysis_bundle)
        save_project_button = action_button(
            "项目另存为...",
            role="primary",
            tooltip="保存可复现项目。",
            status_tip="辅助入口：与项目菜单共用 MainWindow.save_project_to_folder()，写出 project.json 和内部曲线数据。",
        )
        save_project_button.clicked.connect(self.save_project_folder)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(export_curve_button)
        layout.addWidget(export_feature_button)
        layout.addWidget(export_origin_long_button)
        layout.addWidget(export_origin_matrix_button)
        layout.addWidget(export_report_button)
        layout.addWidget(export_bundle_button)
        layout.addWidget(save_project_button)
        layout.addWidget(self.output, 1)

    def _choose_folder(self) -> Path | None:
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹", self.main_window.settings.default_export_dir)
        return Path(folder) if folder else None

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
        try:
            path = export_curve_csv(curve, folder / f"{curve.name}_curve.csv")
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
        try:
            path = export_feature_table(self.main_window.project.curves, self.main_window.project.analysis_results, folder / "feature_table.csv")
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
        try:
            path = export_origin_long_csv(self.main_window.project.curves, folder / "curves_long.csv")
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

    def export_origin_matrix_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        try:
            path, warnings = export_origin_matrix_csv(self.main_window.project.curves, folder / "curves_matrix.csv")
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

    def export_report(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        try:
            path = generate_markdown_report(
                folder / "sas_curve_analyzer_report.md",
                project_name="sas_curve_analyzer",
                curves=self.main_window.project.curves,
                analyses=self.main_window.project.analysis_results,
                history=self.main_window.project.history_records,
                formal_records=self.main_window.project.formal_records,
            )
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Markdown 报告导出失败",
                        what_happened="Markdown 报告没有写入导出文件夹。",
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
        self.main_window.project.add_history_record(create_history_record("export_markdown_report", parameters={"path": str(path), "format": "markdown"}))
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.output.setPlainText(f"已导出: {path}")

    def export_analysis_bundle(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("导出未执行：没有选择导出文件夹。")
            return
        try:
            outputs = export_analysis_bundle(
                self.main_window.project.curves,
                self.main_window.project.analysis_results,
                folder,
                project_name="sas_curve_analyzer",
                comparisons=self.main_window.project.comparison_results,
                history=self.main_window.project.history_records,
                formal_records=self.main_window.project.formal_records,
                settings=self.main_window.settings,
            )
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="完整分析包导出失败",
                        what_happened="完整分析包没有完成写入。",
                        facts=(
                            f"curve_count：{len(self.main_window.project.curves)}。",
                            f"analysis_count：{len(self.main_window.project.analysis_results)}。",
                            f"comparison_count：{len(self.main_window.project.comparison_results)}。",
                            f"target_folder：{folder}。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        warnings = []
        warning_path = outputs.get("bundle_warnings")
        if warning_path is not None:
            warnings = warning_path.read_text(encoding="utf-8").splitlines()
        self.main_window.project.add_history_record(
            create_history_record("export_analysis_bundle", parameters={"path": str(folder), "files": [str(path) for path in outputs.values()]}, warnings=warnings)
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        message = "已导出完整分析包:\n" + "\n".join(str(path) for path in outputs.values())
        if warnings:
            message += "\n\nwarnings:\n" + "\n".join(warnings)
        self.output.setPlainText(message)

    def save_project_folder(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("项目保存未执行：没有选择项目保存文件夹。")
            return
        try:
            path = self.main_window.save_project_to_folder(folder)
        except Exception as exc:
            self.output.setPlainText(
                format_user_message(
                    UserMessage(
                        title="项目保存失败",
                        what_happened="当前项目没有写入所选项目文件夹。",
                        facts=(
                            f"curve_count：{len(self.main_window.project.curves)}。",
                            f"target_folder：{folder}。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.output.setPlainText(f"项目已保存: {path}")

