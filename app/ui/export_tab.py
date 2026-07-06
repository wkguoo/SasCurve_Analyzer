from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.export import export_curve_csv, export_feature_table
from app.core.project import save_project
from app.core.report import generate_markdown_report


class ExportTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        export_curve_button = QPushButton("导出当前曲线 CSV")
        export_curve_button.clicked.connect(self.export_current_curve)
        export_feature_button = QPushButton("导出 feature_table.csv")
        export_feature_button.clicked.connect(self.export_feature_table)
        export_report_button = QPushButton("导出 Markdown 报告")
        export_report_button.clicked.connect(self.export_report)
        save_project_button = QPushButton("保存项目文件夹")
        save_project_button.clicked.connect(self.save_project_folder)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(export_curve_button)
        layout.addWidget(export_feature_button)
        layout.addWidget(export_report_button)
        layout.addWidget(save_project_button)
        layout.addWidget(self.output, 1)

    def _choose_folder(self) -> Path | None:
        folder = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        return Path(folder) if folder else None

    def export_current_curve(self) -> None:
        curve = self.main_window.current_curve()
        folder = self._choose_folder()
        if curve is None or folder is None:
            self.output.setPlainText("请选择曲线和导出文件夹。")
            return
        path = export_curve_csv(curve, folder / f"{curve.name}_curve.csv")
        self.output.setPlainText(f"已导出: {path}")

    def export_feature_table(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择导出文件夹。")
            return
        path = export_feature_table(self.main_window.project.curves, self.main_window.project.analysis_results, folder / "feature_table.csv")
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
        self.output.setPlainText(f"已导出: {path}")

    def save_project_folder(self) -> None:
        folder = self._choose_folder()
        if folder is None:
            self.output.setPlainText("请选择项目保存文件夹。")
            return
        path = save_project(self.main_window.project, folder)
        self.output.setPlainText(f"项目已保存: {path}")

