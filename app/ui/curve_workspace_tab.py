from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QSplitter, QVBoxLayout, QWidget


class CurveWorkspaceTab(QWidget):
    def __init__(self, plotting_tab: QWidget, analysis_tab: QWidget) -> None:
        super().__init__()
        self.plotting_tab = plotting_tab
        self.analysis_tab = analysis_tab
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("curveWorkspaceSplitter")
        self.splitter.setChildrenCollapsible(False)

        plotting_group = QGroupBox("曲线绘图")
        plotting_layout = QVBoxLayout(plotting_group)
        plotting_layout.setContentsMargins(8, 8, 8, 8)
        plotting_layout.addWidget(self.plotting_tab)

        analysis_group = QGroupBox("曲线分析")
        analysis_layout = QVBoxLayout(analysis_group)
        analysis_layout.setContentsMargins(8, 8, 8, 8)
        analysis_layout.addWidget(self.analysis_tab)

        self.splitter.addWidget(plotting_group)
        self.splitter.addWidget(analysis_group)
        self.splitter.setSizes([720, 480])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

