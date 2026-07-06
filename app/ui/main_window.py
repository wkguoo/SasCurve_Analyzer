from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QMainWindow, QSplitter, QTabWidget

from app.core.data_model import CurveData
from app.core.project import ProjectState
from app.ui.analysis_tab import AnalysisTab
from app.ui.advanced_tab import AdvancedTab
from app.ui.batch_tab import BatchTab
from app.ui.check_tab import CheckTab
from app.ui.export_tab import ExportTab
from app.ui.import_tab import ImportTab
from app.ui.plotting_tab import PlottingTab
from app.ui.records_tab import RecordsTab
from app.ui.settings_dialog import SettingsDialog
from app.ui.templates_tab import TemplatesTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("sas_curve_analyzer")
        self.resize(1100, 700)
        self.project = ProjectState()

        self.curve_list = QListWidget()
        self.curve_list.currentRowChanged.connect(self._on_curve_selection_changed)

        self.tabs = QTabWidget()
        self.import_tab = ImportTab(self)
        self.check_tab = CheckTab(self)
        self.plotting_tab = PlottingTab(self)
        self.analysis_tab = AnalysisTab(self)
        self.batch_tab = BatchTab(self)
        self.records_tab = RecordsTab(self)
        self.export_tab = ExportTab(self)
        self.templates_tab = TemplatesTab(self)
        self.advanced_tab = AdvancedTab(self)
        self.tabs.addTab(self.import_tab, "数据导入")
        self.tabs.addTab(self.check_tab, "数据检查")
        self.tabs.addTab(self.plotting_tab, "曲线绘图")
        self.tabs.addTab(self.analysis_tab, "无模型分析")
        self.tabs.addTab(self.batch_tab, "批量比较")
        self.tabs.addTab(self.records_tab, "历史与正式记录")
        self.tabs.addTab(self.export_tab, "导出报告")
        self.tabs.addTab(self.templates_tab, "分析模板")
        self.tabs.addTab(self.advanced_tab, "高级功能")

        settings_action = self.menuBar().addAction("设置")
        settings_action.triggered.connect(self.open_settings)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.curve_list)
        splitter.addWidget(self.tabs)
        splitter.setSizes([260, 840])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("请导入已完成绝对强度校准的一维 SAS 曲线。")

    def add_curve(self, curve: CurveData) -> None:
        self.project.add_curve(curve)
        self.curve_list.addItem(f"{curve.name}  [{curve.q_unit}]")
        self.curve_list.setCurrentRow(len(self.project.curves) - 1)
        self.statusBar().showMessage(f"已导入曲线: {curve.name}")

    def current_curve(self) -> CurveData | None:
        row = self.curve_list.currentRow()
        if row < 0 or row >= len(self.project.curves):
            return None
        return self.project.curves[row]

    def replace_current_curve_selection(self, curve: CurveData) -> None:
        self.add_curve(curve)

    def _on_curve_selection_changed(self) -> None:
        self.check_tab.refresh()
        self.plotting_tab.refresh()
        self.analysis_tab.refresh_results()
        self.records_tab.refresh()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()
