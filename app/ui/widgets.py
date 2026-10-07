from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHeaderView, QLayout,
    QLayoutItem, QScrollArea, QSizePolicy, QTableWidget, QWidget,
)


class FlowLayout(QLayout):
    """Keep actions in reading order and wrap them to the available width."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            if not item.isEmpty():
                size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, row_height = area.x(), area.y(), 0
        gap = max(0, self.spacing())
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            width = min(size.width(), max(item.minimumSize().width(), area.width()))
            if x > area.x() and x + width > area.x() + area.width():
                x, y, row_height = area.x(), y + row_height + gap, 0
            if apply:
                item.setGeometry(QRect(x, y, width, size.height()))
            x += width + gap
            row_height = max(row_height, size.height())
        return y + row_height - rect.y() + bottom


def scroll_page(widget: QWidget) -> QScrollArea:
    """Let dense scientific forms scroll without forcing the whole window wider."""
    area = QScrollArea()
    area.setObjectName(f"{widget.__class__.__name__}Scroll")
    area.setFrameShape(QFrame.NoFrame)
    area.setWidgetResizable(True)
    area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    area.setWidget(widget)
    return area


def configure_combo(combo: QComboBox) -> None:
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(16)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


def configure_table(table: QTableWidget) -> None:
    """Presentation tables are read-only; selection still drives existing actions."""
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(32)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setMinimumSectionSize(64)
    table.setMinimumHeight(150)
