from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QTextEdit, QVBoxLayout, QWidget

from app.core.export import export_analysis_bundle, export_curve_csv, export_feature_table
from app.core.project import save_project
from app.core.records import create_history_record
from app.core.report import generate_markdown_report
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
            "保存项目文件夹",
            role="primary",
            tooltip="保存可复现项目。",
            status_tip="主操作：写出 project.json 和内部曲线数据，便于下次恢复项目状态。",
        )
        save_project_button.clicked.connect(self.save_project_folder)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(export_curve_button)
        layout.addWidget(export_feature_button)
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
            self.output.setPlainText("请选择曲线和导出文件夹。")
            return
        path = export_curve_csv(curve, folder / f"{curve.name}_curve.csv")
        self.main_window.project.add_history_record(
            create_history_record("export_curve_csv", input_ids=[curve.curve_id], parameters={"path": str(path), "format": "csv"})
        )
        self.main_window.records_tab.refresh()
        self.output.setPlainText(f"已导出: {path}")

    def export_feature_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择导出文件夹。")
            return
        path = export_feature_table(self.main_window.project.curves, self.main_window.project.analysis_results, folder / "feature_table.csv")
        self.main_window.project.add_history_record(create_history_record("export_feature_table", parameters={"path": str(path), "format": "csv"}))
        self.main_window.records_tab.refresh()
        self.output.setPlainText(f"已导出: {path}")

    def export_report(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择导出文件夹。")
            return
        path = generate_markdown_report(
            folder / "sas_curve_analyzer_report.md",
            project_name="sas_curve_analyzer",
            curves=self.main_window.project.curves,
            analyses=self.main_window.project.analysis_results,
            history=self.main_window.project.history_records,
            formal_records=self.main_window.project.formal_records,
        )
        self.main_window.project.add_history_record(create_history_record("export_markdown_report", parameters={"path": str(path), "format": "markdown"}))
        self.main_window.records_tab.refresh()
        self.output.setPlainText(f"已导出: {path}")

    def export_analysis_bundle(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择导出文件夹。")
            return
        outputs = export_analysis_bundle(
            self.main_window.project.curves,
            self.main_window.project.analysis_results,
            folder,
            project_name="sas_curve_analyzer",
            history=self.main_window.project.history_records,
            formal_records=self.main_window.project.formal_records,
        )
        self.main_window.project.add_history_record(
            create_history_record("export_analysis_bundle", parameters={"path": str(folder), "files": [str(path) for path in outputs.values()]})
        )
        self.main_window.records_tab.refresh()
        self.output.setPlainText("已导出完整分析包:\n" + "\n".join(str(path) for path in outputs.values()))

    def save_project_folder(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择项目保存文件夹。")
            return
        expected_path = folder / "project.json"
        self.main_window.project.add_history_record(create_history_record("export_project_save", parameters={"path": str(expected_path), "format": "project_folder"}))
        path = save_project(self.main_window.project, folder)
        self.main_window.records_tab.refresh()
        self.output.setPlainText(f"项目已保存: {path}")

