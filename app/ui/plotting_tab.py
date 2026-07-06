from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from app.core.plotting import create_curve_figure


class PlottingTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.plot_type = QComboBox()
        self.plot_type.addItems(["linear", "semilog", "loglog", "guinier", "kratky", "porod", "invariant", "local_slope"])
        self.show_error = QCheckBox("显示误差棒")
        self.show_error.setChecked(True)

        plot_button = QPushButton("绘制当前曲线")
        plot_button.clicked.connect(self.refresh)

        self.figure, _ = create_curve_figure([])
        self.canvas = FigureCanvas(self.figure)
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(110)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("图类型"))
        controls.addWidget(self.plot_type)
        controls.addWidget(self.show_error)
        controls.addWidget(plot_button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.messages)

    def refresh(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.messages.setPlainText("尚未选择曲线。")
            return

        self.figure, warnings = create_curve_figure(
            curve,
            plot_type=self.plot_type.currentText(),
            show_error=self.show_error.isChecked(),
        )
        self.canvas.figure = self.figure
        self.canvas.draw()
        self.messages.setPlainText("\n".join(warnings) if warnings else "绘图完成。")
