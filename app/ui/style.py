from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

ActionRole = Literal["primary", "secondary", "success", "warning", "danger", "quiet"]

VALID_ACTION_ROLES: set[str] = {"primary", "secondary", "success", "warning", "danger", "quiet"}
DEFAULT_TOOLTIP_DURATION_MS = 7000


def build_app_stylesheet() -> str:
    return """
    QMainWindow {
        background: #f0f3f8;
    }
    QWidget#workspaceHeader, QWidget#projectSidebar {
        background: #ffffff;
        border: 1px solid #dce3ed;
        border-radius: 8px;
    }
    QLabel#brandTitle, QLabel[uiRole="heading"] {
        color: #18344d;
        font-size: 17px;
        font-weight: bold;
    }
    QLabel[uiRole="muted"], QLabel#curveCount {
        color: #596b7e;
    }
    QLabel#projectState {
        color: #315777;
        background: #edf4fa;
        border-radius: 5px;
        padding: 6px 10px;
    }
    QLabel#curveSummary {
        color: #42586c;
        background: #f3f6fa;
        border-radius: 6px;
        padding: 10px;
    }
    QMenuBar {
        background: #f8fafc;
        color: #1f2933;
        border-bottom: 1px solid #d7dee7;
        padding: 4px 8px;
    }
    QMenuBar::item {
        padding: 6px 10px;
        border-radius: 5px;
    }
    QMenuBar::item:selected {
        background: #e5eef6;
    }
    QStatusBar {
        background: #f8fafc;
        color: #465564;
        border-top: 1px solid #d7dee7;
        padding: 4px 8px;
    }
    QSplitter::handle {
        background: #e4eaf1;
    }
    QSplitter::handle:hover {
        background: #9cbad1;
    }
    QListWidget#curveList {
        background: #fbfcfe;
        border: 1px solid #cfd8e3;
        border-radius: 8px;
        padding: 6px;
        alternate-background-color: #f3f7fb;
    }
    QListWidget#curveList::item {
        min-height: 28px;
        padding: 5px 8px;
        border-radius: 5px;
    }
    QListWidget#curveList::item:selected {
        background: #1d6fa3;
        color: white;
    }
    QTabWidget::pane {
        border: 1px solid #cfd8e3;
        border-radius: 8px;
        background: #fbfcfe;
        top: -1px;
    }
    QTabBar::tab {
        background: #e8eef4;
        color: #314252;
        border: 1px solid #cfd8e3;
        border-bottom: none;
        padding: 8px 12px;
        margin-right: 3px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }
    QTabBar::tab:selected {
        background: #fbfcfe;
        color: #16364f;
        font-weight: bold;
    }
    QTabBar::tab:hover:!selected {
        background: #f2f6fa;
    }
    QTabWidget#mainTabs > QTabBar::tab {
        padding: 10px 18px;
    }
    QGroupBox {
        color: #31516d;
        background: #fbfcfe;
        border: 1px solid #dce3ed;
        border-radius: 7px;
        margin-top: 14px;
        padding-top: 10px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 5px;
    }
    QLabel {
        color: #263746;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit, QListWidget, QTableView {
        background: #ffffff;
        color: #1f2933;
        border: 1px solid #c8d2dd;
        border-radius: 6px;
        selection-background-color: #1d6fa3;
        selection-color: #ffffff;
    }
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        min-height: 26px;
        padding: 3px 7px;
    }
    QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QListWidget:focus {
        border: 1px solid #1d6fa3;
    }
    QTextEdit {
        padding: 8px;
    }
    QTableView {
        alternate-background-color: #f4f7fb;
        gridline-color: #e4eaf1;
    }
    QTableView::item {
        padding: 5px 8px;
        border: none;
    }
    QTableView::item:selected {
        background: #e2eff9;
        color: #173e5b;
    }
    QHeaderView::section {
        background: #edf2f8;
        color: #40566d;
        padding: 7px 9px;
        border: none;
        border-right: 1px solid #dce3ed;
        border-bottom: 1px solid #dce3ed;
        font-weight: bold;
    }
    QProgressBar {
        border: 1px solid #dce3ed;
        border-radius: 5px;
        background: #edf2f8;
        text-align: center;
        min-height: 22px;
    }
    QProgressBar::chunk {
        background: #2c7cad;
        border-radius: 4px;
    }
    QScrollArea {
        background: #fbfcfe;
        border: none;
    }
    QScrollBar:vertical {
        background: #f0f3f8;
        width: 12px;
        margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #b5c4d3;
        min-height: 28px;
        border-radius: 5px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
    }
    QCheckBox {
        color: #263746;
        spacing: 7px;
    }
    QPushButton {
        background: #f6f8fa;
        color: #22313f;
        border: 1px solid #b8c3cf;
        border-radius: 6px;
        padding: 7px 12px;
        min-height: 28px;
        font-weight: normal;
    }
    QPushButton:hover {
        background: #eef3f7;
        border-color: #8aa0b4;
    }
    QPushButton:pressed {
        background: #dfe8ef;
    }
    QPushButton:focus, QToolButton:focus {
        border: 2px solid #246d9c;
    }
    QToolButton {
        color: #315777;
        background: #edf4fa;
        border: 1px solid #cbdbe8;
        border-radius: 5px;
        padding: 6px 9px;
    }
    QToolButton:hover {
        background: #e2eff9;
    }
    QPushButton:disabled {
        background: #e5e9ed;
        color: #8b98a5;
        border-color: #d0d6dc;
    }
    QPushButton[uiRole="primary"] {
        background: #1d6fa3;
        color: #ffffff;
        border-color: #175a85;
        font-weight: bold;
    }
    QPushButton[uiRole="primary"]:hover {
        background: #2481bb;
        border-color: #175a85;
    }
    QPushButton[uiRole="success"] {
        background: #2f7d64;
        color: #ffffff;
        border-color: #276851;
        font-weight: bold;
    }
    QPushButton[uiRole="success"]:hover {
        background: #388f73;
    }
    QPushButton[uiRole="warning"] {
        background: #f2b84b;
        color: #3d2b0a;
        border-color: #c89129;
        font-weight: bold;
    }
    QPushButton[uiRole="warning"]:hover {
        background: #f6c765;
    }
    QPushButton[uiRole="danger"] {
        background: #b84a4a;
        color: #ffffff;
        border-color: #943838;
        font-weight: bold;
    }
    QPushButton[uiRole="danger"]:hover {
        background: #cc5a5a;
    }
    QPushButton[uiRole="quiet"] {
        background: transparent;
        color: #1d6fa3;
        border-color: transparent;
    }
    QPushButton[uiRole="quiet"]:hover {
        background: #e8f1f7;
        border-color: #bdd2e2;
    }
    QPushButton[uiRole="quiet"]:checked {
        background: #e2eff9;
        border-color: #9cbad1;
    }
    QToolTip {
        background: #172635;
        color: #f7fafc;
        border: 1px solid #2d465b;
        border-radius: 6px;
        padding: 7px 9px;
        opacity: 245;
    }
    """


def apply_app_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.Window, "#f0f3f8"), (QPalette.WindowText, "#263746"),
        (QPalette.Base, "#ffffff"), (QPalette.AlternateBase, "#f4f7fb"),
        (QPalette.Text, "#263746"), (QPalette.Button, "#f6f8fa"),
        (QPalette.ButtonText, "#263746"), (QPalette.Highlight, "#1d6fa3"),
        (QPalette.HighlightedText, "#ffffff"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    font = QFont(app.font())
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial"])
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(build_app_stylesheet())
    # Match plot labels to the UI while retaining a portable Latin/math fallback.
    from matplotlib import font_manager, rcParams
    available = {entry.name for entry in font_manager.fontManager.ttflist}
    families = [name for name in ("Microsoft YaHei", "Noto Sans CJK SC", "WenQuanYi Zen Hei") if name in available]
    rcParams["font.sans-serif"] = families + ["DejaVu Sans"]
    rcParams["font.family"] = ["DejaVu Sans", *families]


def apply_help(
    widget: QWidget,
    *,
    tooltip: str,
    status_tip: str | None = None,
    duration_ms: int = DEFAULT_TOOLTIP_DURATION_MS,
) -> None:
    tooltip_text = tooltip.strip()
    detail_text = (status_tip or tooltip_text).strip()
    widget.setToolTip(tooltip_text)
    widget.setStatusTip(detail_text)
    widget.setWhatsThis(detail_text)
    widget.setToolTipDuration(duration_ms)


def apply_button_role(button: QPushButton, role: ActionRole = "secondary") -> QPushButton:
    safe_role = role if role in VALID_ACTION_ROLES else "secondary"
    button.setProperty("uiRole", safe_role)
    button.setCursor(Qt.PointingHandCursor)
    button.setMinimumHeight(34)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def action_button(
    text: str,
    *,
    role: ActionRole = "secondary",
    tooltip: str = "",
    status_tip: str | None = None,
) -> QPushButton:
    button = apply_button_role(QPushButton(text), role)
    if tooltip:
        apply_help(button, tooltip=tooltip, status_tip=status_tip)
    return button
