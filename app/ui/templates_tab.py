from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.core.analysis_templates import AnalysisTemplate, apply_template, load_template, save_template


class TemplatesTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.template = AnalysisTemplate.create("default_model_free")
        save_button = QPushButton("保存默认模板")
        save_button.clicked.connect(self.save_default_template)
        load_button = QPushButton("加载模板")
        load_button.clicked.connect(self.load_template)
        apply_button = QPushButton("应用模板到全部曲线")
        apply_button.clicked.connect(self.apply_to_all)
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(save_button)
        layout.addWidget(load_button)
        layout.addWidget(apply_button)
        layout.addWidget(self.output, 1)

    def save_default_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存模板", "analysis_template.json", "JSON (*.json)")
        if not path:
            return
        saved = save_template(self.template, Path(path))
        self.output.setPlainText(f"模板已保存: {saved}")

    def load_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "加载模板", "", "JSON (*.json)")
        if not path:
            return
        self.template = load_template(Path(path))
        self.output.setPlainText(f"模板已加载: {self.template.name}")

    def apply_to_all(self) -> None:
        curves = self.main_window.project.curves
        if not curves:
            self.output.setPlainText("没有可应用模板的曲线。")
            return
        run, analyses, history = apply_template(self.template, curves)
        for result in analyses:
            self.main_window.project.add_analysis_result(result)
        for record in history:
            self.main_window.project.add_history_record(record)
        self.output.setPlainText(f"Pipeline {run.status}: {run.pipeline_id}\n分析结果数: {len(analyses)}")

