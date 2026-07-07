from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from app.core.plotting import create_curve_figure, format_plot_cursor_coordinates, transform_x_for_plot
from app.ui.style import action_button, apply_help


PLOT_TYPE_ITEMS = [
    ("Linear: I(q) vs q", "linear"),
    ("Semi-log: ln I(q) vs q", "semilog"),
    ("Log-log / power-law: ln I(q) vs ln q", "loglog"),
    ("Guinier: ln I(q) vs q\u00b2", "guinier"),
    ("Kratky: q\u00b2I(q) vs q", "kratky"),
    ("Porod: q\u2074I(q) vs q", "porod"),
    ("Invariant integrand: q\u00b2I(q) vs q", "invariant"),
    ("Log-q contribution: q\u00b3I(q) vs ln q", "invariant_contribution"),
    ("Local slope: \u03b1(q) vs q", "local_slope"),
    ("Peak / d-spacing: I(q) vs q, d = 2\u03c0/q*", "peak_spacing"),
]


class PlottingTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self._motion_cid: int | None = None

        self.plot_type = QComboBox()
        for label, key in PLOT_TYPE_ITEMS:
            self.plot_type.addItem(label, key)
        apply_help(
            self.plot_type,
            tooltip="Choose the SAS plotting view.",
            status_tip="Display labels use standard math symbols; internal plot keys stay stable for scripts and tests.",
        )
        self.plot_type.currentIndexChanged.connect(self.refresh)

        self.show_error = QCheckBox("Show error bars")
        self.show_error.setChecked(self.main_window.settings.show_error_bars)
        self.show_error.stateChanged.connect(self.refresh)
        apply_help(
            self.show_error,
            tooltip="Toggle error bars.",
            status_tip="Error bars are shown only when the imported curve contains a valid error/sigma column.",
        )

        self.show_d_axis = QCheckBox("Show d = 2\u03c0/q axis")
        self.show_d_axis.stateChanged.connect(self.refresh)
        apply_help(
            self.show_d_axis,
            tooltip="Add a top d-axis when x is raw q.",
            status_tip="The d-axis is an approximate characteristic scale or correlation distance, not an automatic particle diameter.",
        )

        self.annotate_peaks = QCheckBox("Annotate q* / d")
        self.annotate_peaks.setChecked(True)
        self.annotate_peaks.stateChanged.connect(self.refresh)

        self.x_min = QLineEdit()
        self.x_max = QLineEdit()
        self.y_min = QLineEdit()
        self.y_max = QLineEdit()
        for edit in [self.x_min, self.x_max, self.y_min, self.y_max]:
            edit.setPlaceholderText("auto")
            edit.returnPressed.connect(self.refresh)

        plot_button = action_button(
            "Plot current curve",
            role="primary",
            tooltip="Refresh the current plot.",
            status_tip="Draws the selected view and applies display-only axis limits.",
        )
        plot_button.clicked.connect(self.refresh)
        clear_button = action_button("Auto range", role="secondary", tooltip="Clear axis limits.")
        clear_button.clicked.connect(self.clear_axis_range)
        full_button = action_button("Full q", role="secondary", tooltip="Use the full current q range.")
        full_button.clicked.connect(lambda: self.set_q_range_fraction(0.0, 1.0))
        low_button = action_button("Low q", role="secondary", tooltip="Use the lowest third of q.")
        low_button.clicked.connect(lambda: self.set_q_range_fraction(0.0, 1.0 / 3.0))
        mid_button = action_button("Mid q", role="secondary", tooltip="Use the middle third of q.")
        mid_button.clicked.connect(lambda: self.set_q_range_fraction(1.0 / 3.0, 2.0 / 3.0))
        high_button = action_button("High q", role="secondary", tooltip="Use the highest third of q.")
        high_button.clicked.connect(lambda: self.set_q_range_fraction(2.0 / 3.0, 1.0))

        self.figure, _ = create_curve_figure([])
        self.canvas = FigureCanvas(self.figure)
        self.cursor_label = QLabel("Coordinates: -")
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(120)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Plot type"))
        controls.addWidget(self.plot_type)
        controls.addWidget(self.show_error)
        controls.addWidget(self.show_d_axis)
        controls.addWidget(self.annotate_peaks)
        controls.addWidget(plot_button)
        controls.addStretch(1)

        range_controls = QGridLayout()
        range_controls.addWidget(QLabel("X min"), 0, 0)
        range_controls.addWidget(self.x_min, 0, 1)
        range_controls.addWidget(QLabel("X max"), 0, 2)
        range_controls.addWidget(self.x_max, 0, 3)
        range_controls.addWidget(QLabel("Y min"), 0, 4)
        range_controls.addWidget(self.y_min, 0, 5)
        range_controls.addWidget(QLabel("Y max"), 0, 6)
        range_controls.addWidget(self.y_max, 0, 7)
        range_controls.addWidget(clear_button, 1, 0)
        range_controls.addWidget(full_button, 1, 1)
        range_controls.addWidget(low_button, 1, 2)
        range_controls.addWidget(mid_button, 1, 3)
        range_controls.addWidget(high_button, 1, 4)
        range_controls.addWidget(self.cursor_label, 1, 5, 1, 3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addLayout(controls)
        layout.addLayout(range_controls)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.messages)
        self._connect_cursor()

    def refresh(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.messages.setPlainText("No curve selected.")
            return

        plot_type = self.plot_type.currentData()
        self.figure, warnings = create_curve_figure(
            curve,
            plot_type=plot_type,
            show_error=self.show_error.isChecked(),
            show_d_axis=self.show_d_axis.isChecked(),
            annotate_peaks=self.annotate_peaks.isChecked() or plot_type == "peak_spacing",
        )
        limit_warning = self._apply_axis_limits()
        if limit_warning:
            warnings.append(limit_warning)
        self.canvas.figure = self.figure
        self._connect_cursor()
        self.canvas.draw()
        self.messages.setPlainText("\n".join(warnings) if warnings else "Plot completed.")

    def clear_axis_range(self) -> None:
        for edit in [self.x_min, self.x_max, self.y_min, self.y_max]:
            edit.clear()
        self.refresh()

    def set_q_range_fraction(self, start_fraction: float, end_fraction: float) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.messages.setPlainText("No curve selected.")
            return
        q = np.asarray(curve.q, dtype=float)
        q = q[np.isfinite(q)]
        if self.plot_type.currentData() in {"loglog", "guinier", "invariant_contribution"}:
            q = q[q > 0]
        if q.size == 0:
            self.messages.setPlainText("No finite q values are available for range selection.")
            return

        q_sorted = np.sort(q)
        start_index = min(int(np.floor(start_fraction * (q_sorted.size - 1))), q_sorted.size - 1)
        end_index = min(int(np.ceil(end_fraction * (q_sorted.size - 1))), q_sorted.size - 1)
        q_min = q_sorted[start_index]
        q_max = q_sorted[max(start_index, end_index)]
        transformed = transform_x_for_plot(np.array([q_min, q_max]), self.plot_type.currentData())
        finite = transformed[np.isfinite(transformed)]
        if finite.size != 2:
            self.messages.setPlainText("Selected q range cannot be transformed for the current plot type.")
            return
        self.x_min.setText(f"{float(np.min(finite)):.6g}")
        self.x_max.setText(f"{float(np.max(finite)):.6g}")
        self.refresh()

    def _apply_axis_limits(self) -> str | None:
        if not self.figure.axes:
            return None
        axis = self.figure.axes[0]
        try:
            x_min = self._parse_optional_float(self.x_min.text())
            x_max = self._parse_optional_float(self.x_max.text())
            y_min = self._parse_optional_float(self.y_min.text())
            y_max = self._parse_optional_float(self.y_max.text())
        except ValueError as exc:
            return f"Axis limits were ignored: {exc}"
        if x_min is not None and x_max is not None:
            if x_min >= x_max:
                return "Axis limits were ignored: X min must be smaller than X max."
            axis.set_xlim(x_min, x_max)
        elif x_min is not None or x_max is not None:
            current_min, current_max = axis.get_xlim()
            axis.set_xlim(x_min if x_min is not None else current_min, x_max if x_max is not None else current_max)
        if y_min is not None and y_max is not None:
            if y_min >= y_max:
                return "Axis limits were ignored: Y min must be smaller than Y max."
            axis.set_ylim(y_min, y_max)
        elif y_min is not None or y_max is not None:
            current_min, current_max = axis.get_ylim()
            axis.set_ylim(y_min if y_min is not None else current_min, y_max if y_max is not None else current_max)
        return None

    @staticmethod
    def _parse_optional_float(text: str) -> float | None:
        value = text.strip()
        if not value:
            return None
        parsed = float(value)
        if not np.isfinite(parsed):
            raise ValueError(f"{value!r} is not finite")
        return parsed

    def _connect_cursor(self) -> None:
        if self._motion_cid is not None:
            try:
                self.canvas.mpl_disconnect(self._motion_cid)
            except Exception:
                pass
        self._motion_cid = self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

    def _on_mouse_move(self, event) -> None:
        if event.inaxes is None:
            self.cursor_label.setText("Coordinates: -")
            return
        self.cursor_label.setText(format_plot_cursor_coordinates(event.xdata, event.ydata, self.plot_type.currentData()))
