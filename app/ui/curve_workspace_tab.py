from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QGroupBox, QSplitter, QVBoxLayout, QWidget
from app.ui.widgets import scroll_page


class CurveWorkspaceTab(QWidget):
    def __init__(self, plotting_tab: QWidget, analysis_tab: QWidget) -> None:
        super().__init__()
        self.plotting_tab = plotting_tab
        self.analysis_tab = analysis_tab
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("curveWorkspaceSplitter")
        self.splitter.setChildrenCollapsible(False)

        plotting_group = self.plotting_group = QGroupBox("曲线绘图")
        plotting_layout = QVBoxLayout(plotting_group)
        plotting_layout.setContentsMargins(8, 8, 8, 8)
        plotting_layout.addWidget(scroll_page(self.plotting_tab))

        analysis_group = self.analysis_group = QGroupBox("曲线分析")
        analysis_layout = QVBoxLayout(analysis_group)
        analysis_layout.setContentsMargins(8, 8, 8, 8)
        analysis_layout.addWidget(scroll_page(self.analysis_tab))

        self.splitter.addWidget(plotting_group)
        self.splitter.addWidget(analysis_group)
        self.splitter.setSizes([720, 480])
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setHandleWidth(8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll_page(self.splitter))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # Use hysteresis so dragging near the breakpoint does not keep resetting panes.
        orientation = self.splitter.orientation()
        if orientation == Qt.Horizontal and self.width() < 1040:
            self.plotting_group.setMinimumHeight(640)
            self.analysis_group.setMinimumHeight(540)
            self.splitter.setOrientation(Qt.Vertical)
            self.splitter.setSizes([480, 380])
        elif orientation == Qt.Vertical and self.width() > 1100:
            self.plotting_group.setMinimumHeight(0)
            self.analysis_group.setMinimumHeight(0)
            self.splitter.setOrientation(Qt.Horizontal)
            self.splitter.setSizes([720, 480])

