from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget
from app.ui.widgets import scroll_page


class DataImportWorkspaceTab(QWidget):
    def __init__(self, import_tab: QWidget, check_tab: QWidget) -> None:
        super().__init__()
        self.import_tab = import_tab
        self.check_tab = check_tab
        self.tabs = QTabWidget()
        self.tabs.setObjectName("dataImportWorkspaceTabs")
        self.tabs.addTab(scroll_page(self.import_tab), "导入数据")
        self.tabs.addTab(scroll_page(self.check_tab), "数据检查")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tabs)

