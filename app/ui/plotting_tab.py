from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QTextEdit, QVBoxLayout, QWidget
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from app.core.figure_export import FIGURE_EXPORT_PRESETS, SUPPORTED_FIGURE_FORMATS, export_figure_with_preset, safe_figure_filename
from app.core.method_mapping import analysis_for_plot
from app.core.plotting import create_curve_figure, format_plot_cursor_coordinates, transform_x_for_plot
from app.core.records import create_history_record
from app.core.user_messages import exception_detail, format_user_message, UserMessage
from app.ui.style import action_button, apply_help
from app.ui.widgets import FlowLayout, configure_combo


PLOT_TYPE_KEYS = [
    "linear",
    "semilog",
    "loglog",
    "guinier",
    "kratky",
    "porod",
    "invariant",
    "local_slope",
]

PLOT_TYPE_ITEMS = [
    ("Linear: I(q) vs q", "linear"),
    ("Semi-log: ln I(q) vs q", "semilog"),
    ("Log-log / power-law: lg I(q) vs lg q", "loglog"),
    ("Guinier: ln I(q) vs q\u00b2", "guinier"),
    ("Kratky: q\u00b2I(q) vs q", "kratky"),
    ("Porod: q\u2074I(q) vs q", "porod"),
    ("Invariant integrand: q\u00b2I(q) vs q", "invariant"),
    ("Local slope: \u03b1(q) vs q", "local_slope"),
]


class PlottingTab(QWidget):
    def __init__(self, main_window) -> None:
        super().__init__()
        self.main_window = main_window
        self._motion_cid: int | None = None
        self._has_drawn_curve = False

        self.plot_type = QComboBox()
        configure_combo(self.plot_type)
        for label, key in PLOT_TYPE_ITEMS:
            self.plot_type.addItem(label, key)
        apply_help(
            self.plot_type,
            tooltip="Choose the SAS plotting view.",
            status_tip="Display labels use standard math symbols; internal plot keys stay stable for scripts and tests.",
        )
        self.plot_type.currentIndexChanged.connect(self.refresh)

        self.show_error = QCheckBox("显示误差棒")
        self.show_error.setChecked(self.main_window.settings.show_error_bars)
        self.show_error.stateChanged.connect(self.refresh)
        apply_help(
            self.show_error,
            tooltip="Toggle error bars.",
            status_tip="Error bars are shown only when the imported curve contains a valid error/sigma column.",
        )

        self.show_d_axis = QCheckBox("显示 d = 2\u03c0/q 轴")
        self.show_d_axis.stateChanged.connect(self.refresh)
        apply_help(
            self.show_d_axis,
            tooltip="Add a top d-axis when x is raw q.",
            status_tip="The d-axis is an approximate characteristic scale or correlation distance, not an automatic particle diameter.",
        )

        self.annotate_peaks = QCheckBox("标注峰位 q* / d")
        self.annotate_peaks.setChecked(True)
        self.annotate_peaks.stateChanged.connect(self.refresh)
        self.figure_preset = QComboBox()
        configure_combo(self.figure_preset)
        for key, preset in FIGURE_EXPORT_PRESETS.items():
            self.figure_preset.addItem(preset.label, key)
        apply_help(
            self.figure_preset,
            tooltip="图像导出预设。",
            status_tip="选择屏幕预览、组会汇报或论文初稿预设；只影响导出图像，不修改曲线数据。",
        )
        self.figure_format = QComboBox()
        configure_combo(self.figure_format)
        for file_format in SUPPORTED_FIGURE_FORMATS:
            self.figure_format.addItem(file_format.upper(), file_format)
        apply_help(
            self.figure_format,
            tooltip="图像格式。",
            status_tip="支持 PNG、SVG 和 PDF；默认值可由预设覆盖后手动调整。",
        )

        self.x_min = QLineEdit()
        self.x_max = QLineEdit()
        self.y_min = QLineEdit()
        self.y_max = QLineEdit()
        for edit in [self.x_min, self.x_max, self.y_min, self.y_max]:
            edit.setMinimumWidth(0)
            edit.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            edit.setPlaceholderText("自动")
            edit.returnPressed.connect(self.refresh)

        plot_button = action_button(
            "刷新曲线图",
            role="primary",
            tooltip="Refresh the current plot.",
            status_tip="Draws the selected view and applies display-only axis limits.",
        )
        plot_button.clicked.connect(self.refresh)
        analysis_button = action_button(
            "用于当前分析",
            role="secondary",
            tooltip="Open the linked model-free analysis for this plot type.",
            status_tip="Uses the shared plot/analysis mapping. Views without a direct model-free analysis show a message instead.",
        )
        analysis_button.clicked.connect(self.send_view_to_analysis)
        export_figure_button = action_button(
            "导出当前图像",
            role="secondary",
            tooltip="Export the current plot.",
            status_tip="Uses the current curve, plot type, axis limits, error-bar and d-axis settings, plus the selected figure preset.",
        )
        export_figure_button.clicked.connect(self.export_current_figure)
        clear_button = action_button("自动范围", role="secondary", tooltip="Clear axis limits.")
        clear_button.clicked.connect(self.clear_axis_range)
        full_button = action_button("完整 q", role="secondary", tooltip="Use the full current q range.")
        full_button.clicked.connect(lambda: self.set_q_range_fraction(0.0, 1.0))
        low_button = action_button("低 q", role="secondary", tooltip="Use the lowest third of q.")
        low_button.clicked.connect(lambda: self.set_q_range_fraction(0.0, 1.0 / 3.0))
        mid_button = action_button("中 q", role="secondary", tooltip="Use the middle third of q.")
        mid_button.clicked.connect(lambda: self.set_q_range_fraction(1.0 / 3.0, 2.0 / 3.0))
        high_button = action_button("高 q", role="secondary", tooltip="Use the highest third of q.")
        high_button.clicked.connect(lambda: self.set_q_range_fraction(2.0 / 3.0, 1.0))

        self.figure, _ = create_curve_figure([])
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumSize(0, 220)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cursor_label = QLabel("Coordinates: -")
        self.cursor_label.setWordWrap(True)
        self.cursor_label.setMaximumHeight(56)
        self.cursor_label.setObjectName("plotCoordinateReadout")
        self.messages = QTextEdit()
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(90)
        self.messages.setPlaceholderText("Import data, then select a curve to begin plotting.")

        plot_type_row = QHBoxLayout()
        plot_type_row.addWidget(QLabel("绘图类型"))
        plot_type_row.addWidget(self.plot_type, 1)

        controls = FlowLayout()
        controls.addWidget(self.show_error)
        controls.addWidget(self.show_d_axis)
        controls.addWidget(self.annotate_peaks)
        controls.addWidget(plot_button)
        controls.addWidget(analysis_button)

        self.range_toggle = action_button("显示范围", role="quiet", tooltip="Show or hide display-only axis limits.")
        self.range_toggle.setObjectName("rangeOptionsToggle")
        self.range_toggle.setCheckable(True)
        self.export_toggle = action_button("图像导出", role="quiet", tooltip="Show or hide figure export settings.")
        self.export_toggle.setObjectName("figureExportToggle")
        self.export_toggle.setCheckable(True)
        section_controls = FlowLayout()
        section_controls.addWidget(self.range_toggle)
        section_controls.addWidget(self.export_toggle)

        self.range_controls = QGridLayout()
        x_min_label, x_max_label = QLabel("X 下限"), QLabel("X 上限")
        y_min_label, y_max_label = QLabel("Y 下限"), QLabel("Y 上限")
        self.range_controls.addWidget(x_min_label, 0, 0)
        self.range_controls.addWidget(self.x_min, 0, 1)
        self.range_controls.addWidget(x_max_label, 0, 2)
        self.range_controls.addWidget(self.x_max, 0, 3)
        self.range_controls.addWidget(y_min_label, 1, 0)
        self.range_controls.addWidget(self.y_min, 1, 1)
        self.range_controls.addWidget(y_max_label, 1, 2)
        self.range_controls.addWidget(self.y_max, 1, 3)
        self.range_controls.setColumnStretch(1, 1)
        self.range_controls.setColumnStretch(3, 1)
        range_actions = FlowLayout()
        for button in [clear_button, full_button, low_button, mid_button, high_button]:
            range_actions.addWidget(button)
        self._range_widgets = [x_min_label, x_max_label, y_min_label, y_max_label,
                               self.x_min, self.x_max, self.y_min, self.y_max,
                               clear_button, full_button, low_button, mid_button, high_button]
        export_controls = FlowLayout()
        preset_label = QLabel("导出预设")
        self._export_widgets = [preset_label, self.figure_preset, self.figure_format, export_figure_button]
        for widget in self._export_widgets:
            export_controls.addWidget(widget)
        self.range_toggle.toggled.connect(lambda visible: self._set_controls_visible(self._range_widgets, visible))
        self.export_toggle.toggled.connect(lambda visible: self._set_controls_visible(self._export_widgets, visible))

        self.coordinate_row = QHBoxLayout()
        self.coordinate_row.addWidget(QLabel("光标坐标"))
        self.coordinate_row.addWidget(self.cursor_label, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(plot_type_row)
        layout.addLayout(controls)
        layout.addLayout(section_controls)
        layout.addLayout(self.range_controls)
        layout.addLayout(range_actions)
        layout.addLayout(export_controls)
        layout.addLayout(self.coordinate_row)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.messages)
        self._set_controls_visible(self._range_widgets, False)
        self._set_controls_visible(self._export_widgets, False)
        self._connect_cursor()
        self.refresh()

    @staticmethod
    def _set_controls_visible(widgets: list[QWidget], visible: bool) -> None:
        for widget in widgets:
            widget.setVisible(visible)

    def refresh(self) -> None:
        self.cursor_label.setText("Coordinates: -")
        curve = self.main_window.current_curve()
        if curve is None:
            self._has_drawn_curve = False
            self.figure, _ = create_curve_figure([])
            axis = self.figure.axes[0]
            axis.set_axis_off()
            axis.text(0.5, 0.5, "Select a curve to begin\nImport data, then choose a curve in the list.",
                      ha="center", va="center", transform=axis.transAxes, color="#64748b")
            self.canvas.figure = self.figure
            self.figure.set_canvas(self.canvas)
            self._connect_cursor()
            self.canvas.draw()
            self.messages.setPlainText("No curve selected. Import data, then select a curve in the curve list.")
            return

        plot_type = self.plot_type.currentData()
        self.figure, warnings = create_curve_figure(
            curve,
            plot_type=plot_type,
            show_error=self.show_error.isChecked(),
            show_d_axis=self.show_d_axis.isChecked(),
            annotate_peaks=self.annotate_peaks.isChecked(),
        )
        limit_warning = self._apply_axis_limits()
        if limit_warning:
            warnings.append(limit_warning)
        self.canvas.figure = self.figure
        self.figure.set_canvas(self.canvas)
        self._has_drawn_curve = True
        self._connect_cursor()
        self.canvas.draw()
        self.messages.setPlainText("\n".join(warnings) if warnings else "Plot completed.")

    def clear_axis_range(self) -> None:
        for edit in [self.x_min, self.x_max, self.y_min, self.y_max]:
            edit.clear()
        self.refresh()

    def send_view_to_analysis(self) -> None:
        plot_type = self.plot_type.currentData()
        analysis_type = analysis_for_plot(plot_type)
        if analysis_type is None:
            self.messages.setPlainText("No direct model-free analysis is linked to this plot view.")
            return
        self.main_window.set_analysis_type(analysis_type)
        self.main_window.show_analysis_tab()
        self.main_window.analysis_tab.output.setPlainText(
            f"Linked from plot view '{plot_type}'. Select or convert a raw q range, then run the analysis."
        )

    def current_x_limits(self) -> tuple[float, float] | None:
        if not self._has_drawn_curve:
            return None
        if not self.figure.axes:
            return None
        left, right = self.figure.axes[0].get_xlim()
        if not np.isfinite(left) or not np.isfinite(right):
            return None
        return float(left), float(right)

    def export_current_figure(self) -> None:
        curve = self.main_window.current_curve()
        if curve is None or not self._has_drawn_curve:
            self.messages.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Figure export unavailable",
                        what_happened="No plotted curve is available for export.",
                        facts=(
                            f"current_curve is None: {curve is None}.",
                            f"has_drawn_curve: {self._has_drawn_curve}.",
                            "Figure export uses the currently displayed Matplotlib figure.",
                        ),
                        severity="warning",
                    )
                )
            )
            return
        plot_type = self.plot_type.currentData()
        file_format = self.figure_format.currentData()
        preset_key = self.figure_preset.currentData()
        default_name = safe_figure_filename(curve.name, plot_type, file_format)
        default_path = Path(self.main_window.settings.default_export_dir) / default_name
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current figure",
            str(default_path),
            "Figure files (*.png *.svg *.pdf);;All files (*)",
        )
        if not path:
            return
        axis_limits = self.current_x_limits()
        try:
            output_path = export_figure_with_preset(self.figure, path, preset_key=preset_key, file_format=file_format)
        except Exception as exc:
            self.messages.setPlainText(
                format_user_message(
                    UserMessage(
                        title="Figure export failed",
                        what_happened="The current Matplotlib figure was not written to the selected path.",
                        facts=(
                            f"plot_type: {plot_type}.",
                            f"preset: {preset_key}.",
                            f"format: {file_format}.",
                            f"target path: {path}.",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )
            )
            return
        self.main_window.project.add_history_record(
            create_history_record(
                "export_current_figure",
                input_ids=[curve.curve_id],
                parameters={
                    "path": str(output_path),
                    "curve_id": curve.curve_id,
                    "plot_type": plot_type,
                    "preset": preset_key,
                    "format": file_format,
                    "axis_x_limits": axis_limits,
                },
            )
        )
        self.main_window.records_tab.refresh()
        self.main_window.mark_project_dirty()
        self.refresh()
        self.messages.setPlainText(f"Figure exported: {output_path}")

    def set_q_range_fraction(self, start_fraction: float, end_fraction: float) -> None:
        curve = self.main_window.current_curve()
        if curve is None:
            self.messages.setPlainText("No curve selected.")
            return
        q = np.asarray(curve.q, dtype=float)
        q = q[np.isfinite(q)]
        if self.plot_type.currentData() in {"loglog", "guinier"}:
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
            except (TypeError, ValueError, RuntimeError, KeyError):
                # Already disconnected or canvas disposed during tab refresh.
                pass
        self._motion_cid = self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)

    def _on_mouse_move(self, event) -> None:
        if not self._has_drawn_curve or event.inaxes is None:
            self.cursor_label.setText("Coordinates: -")
            return
        self.cursor_label.setText(format_plot_cursor_coordinates(event.xdata, event.ydata, self.plot_type.currentData()))
