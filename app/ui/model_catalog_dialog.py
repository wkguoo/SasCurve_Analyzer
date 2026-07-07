from __future__ import annotations

from PySide6.QtWidgets import QDialog, QTextEdit, QVBoxLayout

from app.core.model_catalog import format_model_catalog_summary
from app.ui.style import action_button


class ModelCatalogDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Calculation models and formulas")
        self.resize(820, 680)

        self.catalog_text = QTextEdit()
        self.catalog_text.setReadOnly(True)
        self.catalog_text.setPlainText(format_model_catalog_summary())

        close_button = action_button("Close", role="secondary", tooltip="Close the model catalog.")
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(self.catalog_text, 1)
        layout.addWidget(close_button)
