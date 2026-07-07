from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from app.core.plotting import create_curve_figure
from app.ui.style import action_button, apply_help


class PlottingTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self.plot_type = QComboBox()
        for label, key in [
            ("Linear I(q)", "linear"),
            ("Semilog ln I", "semilog"),
            ("Log-log ln I vs ln q", "loglog"),
            ("Guinier q^2 plot", "guinier"),
            ("Kratky q^2I", "kratky"),
            ("Porod q^4I", "porod"),
            ("Invariant q^2I", "invariant"),
            ("q^3I contribution spectrum", "invariant_contribution"),
            ("Local slope alpha(q)", "local_slope"),
        ]:
            self.plot_type.addItem(label, key)
        apply_help(
            self.plot_type,
            tooltip="选择绘图坐标。",
            status_tip="Guinier、Kratky、Porod、q³I 贡献谱等图会使用对应变换，并自动过滤不适合取对数的数据点。",
        )
        self.show_error = QCheckBox("显示误差棒")
        self.show_error.setChecked(self.main_window.settings.show_error_bars)
        apply_help(
            self.show_error,
            tooltip="切换误差棒。",
            status_tip="仅当曲线包含 error/sigma 列时显示误差棒；不会修改曲线数据。",
        )

        plot_button = action_button(
            "绘制当前曲线",
            role="primary",
            tooltip="刷新当前图。",
            status_tip="主操作：按所选图类型绘制当前曲线，并在下方显示绘图警告。",
        )
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
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
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
            plot_type=self.plot_type.currentData(),
            show_error=self.show_error.isChecked(),
        )
        self.canvas.figure = self.figure
        self.canvas.draw()
        self.messages.setPlainText("\n".join(warnings) if warnings else "绘图完成。")
