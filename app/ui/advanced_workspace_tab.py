from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget


class AdvancedWorkspaceTab(QWidget):
    def __init__(self, advanced_tab: QWidget, deep_analysis_tab: QWidget, batch_tab: QWidget) -> None:
        super().__init__()
        self.advanced_tab = advanced_tab
        self.deep_analysis_tab = deep_analysis_tab
        self.batch_tab = batch_tab
        self.tabs = QTabWidget()
        self.tabs.setObjectName("advancedWorkspaceTabs")
        self.tabs.addTab(self.advanced_tab, "高级方法")
        self.tabs.addTab(self.deep_analysis_tab, "深度分析")
        self.tabs.addTab(self.batch_tab, "批量比较")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

