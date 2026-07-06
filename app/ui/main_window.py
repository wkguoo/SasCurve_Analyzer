from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QMainWindow, QSplitter, QTabWidget

from app.core.data_model import CurveData
from app.core.project import ProjectState
from app.core.settings import load_settings
from app.ui.analysis_tab import AnalysisTab
from app.ui.advanced_tab import AdvancedTab
from app.ui.batch_tab import BatchTab
from app.ui.check_tab import CheckTab
from app.ui.export_tab import ExportTab
from app.ui.import_tab import ImportTab
from app.ui.plotting_tab import PlottingTab
from app.ui.records_tab import RecordsTab
from app.ui.settings_dialog import SettingsDialog
from app.ui.style import apply_help
from app.ui.templates_tab import TemplatesTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SAS Curve Analyzer")
        self.resize(1240, 780)
        self.project = ProjectState()
        self.settings = load_settings()

        self.curve_list = QListWidget()
        self.curve_list.setObjectName("curveList")
        self.curve_list.setAlternatingRowColors(True)
        apply_help(
            self.curve_list,
            tooltip="已导入曲线列表。",
            status_tip="选择一条曲线后，检查、绘图、分析、导出等页签会使用当前曲线。",
        )
        self.curve_list.currentRowChanged.connect(self._on_curve_selection_changed)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
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
        self._configure_tab_help()

        settings_action = self.menuBar().addAction("设置")
        settings_action.setStatusTip("配置默认 q 单位、图像格式、误差棒和导出目录。")
        settings_action.triggered.connect(self.open_settings)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.curve_list)
        splitter.addWidget(self.tabs)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([285, 955])
        self.setCentralWidget(splitter)

        self.statusBar().showMessage("请导入已完成绝对强度校准的一维 SAS 曲线。")

    def _configure_tab_help(self) -> None:
        tab_help = {
            0: "选择并导入单条或批量 SAS 曲线。",
            1: "查看当前曲线的数据质量检查结果。",
            2: "生成线性、对数、Guinier、Kratky 等常用图。",
            3: "运行 Guinier、幂律、峰识别等无模型分析。",
            4: "对多条曲线分组、平均或 A/B 比较。",
            5: "管理历史记录和正式报告记录。",
            6: "导出曲线、特征表、报告或项目文件夹。",
            7: "保存、加载并批量应用分析模板。",
            8: "实验性高级变换与方法边界提示。",
        }
        for index, text in tab_help.items():
            self.tabs.setTabToolTip(index, text)

    def add_curve(self, curve: CurveData) -> None:
        self.project.add_curve(curve)
        self._append_curve_list_item(curve)
        self.curve_list.setCurrentRow(len(self.project.curves) - 1)
        self.statusBar().showMessage(f"已导入曲线: {curve.name}")

    def _append_curve_list_item(self, curve: CurveData) -> None:
        self.curve_list.addItem(f"{curve.name}  [{curve.q_unit}]")

    def refresh_curve_list(self, selected_row: int | None = None) -> None:
        previous_row = self.curve_list.currentRow()
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        for curve in self.project.curves:
            self._append_curve_list_item(curve)
        self.curve_list.blockSignals(False)
        if self.project.curves:
            row = selected_row if selected_row is not None else previous_row
            row = max(0, min(row, len(self.project.curves) - 1))
            self.curve_list.setCurrentRow(row)
        self.refresh_curve_dependent_controls()

    def refresh_curve_dependent_controls(self) -> None:
        if hasattr(self, "batch_tab"):
            self.batch_tab.refresh_curves()
        if hasattr(self, "records_tab"):
            self.records_tab.refresh()

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
        self.refresh_curve_dependent_controls()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()
