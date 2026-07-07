from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.plotting import create_curve_figure, format_plot_cursor_coordinates, transform_x_for_plot


def test_log_plot_excludes_non_positive_intensity() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2, 0.3], intensity=[10, 0, -1])
    _figure, warnings = create_curve_figure(curve, plot_type="semilog")
    assert any("I(q) <= 0" in warning for warning in warnings)


def test_loglog_plot_excludes_non_positive_q() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.0, 0.3], intensity=[10, 8, 6])
    _figure, warnings = create_curve_figure(curve, plot_type="loglog")
    assert any("q <= 0" in warning for warning in warnings)


def test_log_plot_keeps_error_bars_with_error_propagation() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2], intensity=[10, 5], error=[1, 0.5])
    figure, warnings = create_curve_figure(curve, plot_type="semilog", show_error=True)
    assert not warnings
    assert figure.axes


def test_guinier_plot_excludes_non_positive_q_and_intensity() -> None:
    curve = CurveData.create(name="test", q=[-0.1, 0.0, 0.1, 0.2], intensity=[8, 7, 0, 4])
    figure, warnings = create_curve_figure(curve, plot_type="guinier")
    assert any("I(q) <= 0" in warning for warning in warnings)
    assert any("q <= 0" in warning for warning in warnings)
    assert figure.axes
    plotted_y = figure.axes[0].lines[0].get_ydata()
    assert len(plotted_y) == 1
    assert plotted_y[0] == plotted_y[0]


def test_guinier_plot_hides_invalid_error_bars() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2], intensity=[10, 5], error=[1, -0.5])
    figure, warnings = create_curve_figure(curve, plot_type="guinier", show_error=True)
    assert any("error bars were hidden" in warning for warning in warnings)
    assert figure.axes


def test_q3_invariant_contribution_plot_uses_log_q_axis_and_unicode_label() -> None:
    curve = CurveData.create(name="test", q=[1.0, 2.0, 4.0], intensity=[1.0, 2.0, 3.0])
    figure, warnings = create_curve_figure(curve, plot_type="invariant_contribution")

    assert not warnings
    axis = figure.axes[0]
    assert axis.get_xlabel().startswith("ln q")
    assert axis.get_ylabel().startswith("q\u00b3I(q)")
    assert list(axis.lines[0].get_ydata()) == [1.0, 16.0, 192.0]


def test_linear_plot_sorts_unsorted_q_for_scientific_curve_reading() -> None:
    curve = CurveData.create(name="test", q=[0.3, 0.1, 0.2], intensity=[30.0, 10.0, 20.0])

    figure, warnings = create_curve_figure(curve, plot_type="linear")

    assert not warnings
    axis = figure.axes[0]
    assert list(axis.lines[0].get_xdata()) == [0.1, 0.2, 0.3]
    assert list(axis.lines[0].get_ydata()) == [10.0, 20.0, 30.0]


def test_transform_x_for_plot_matches_display_axis() -> None:
    q = np.array([1.0, 2.0, 4.0])
    assert np.allclose(transform_x_for_plot(q, "linear"), q)
    assert np.allclose(transform_x_for_plot(q, "guinier"), q**2)
    assert np.allclose(transform_x_for_plot(q, "loglog"), np.log(q))


def test_cursor_coordinate_format_includes_back_transforms() -> None:
    loglog_text = format_plot_cursor_coordinates(np.log(2.0), np.log(10.0), "loglog")
    guinier_text = format_plot_cursor_coordinates(4.0, np.log(10.0), "guinier")
    slope_text = format_plot_cursor_coordinates(0.2, 3.0, "local_slope")

    assert "q \u2248 2" in loglog_text
    assert "I \u2248 10" in loglog_text
    assert "q\u00b2 = 4" in guinier_text
    assert "q \u2248 2" in guinier_text
    assert "\u03b1(q)" in slope_text
    assert format_plot_cursor_coordinates(None, 1.0, "linear") == "Coordinates: -"


def test_peak_spacing_plot_runs_and_warns_about_d_interpretation() -> None:
    curve = CurveData.create(name="peak", q=[0.1, 0.2, 0.3, 0.4, 0.5], intensity=[1.0, 3.0, 10.0, 3.0, 1.0])
    figure, warnings = create_curve_figure(curve, plot_type="peak_spacing", annotate_peaks=True)

    assert figure.axes[0].get_xlabel().startswith("q")
    assert any("2\u03c0/q" in warning for warning in warnings)


def test_peak_spacing_plot_warns_when_no_peak_detected() -> None:
    curve = CurveData.create(name="flat", q=[0.1, 0.2, 0.3, 0.4], intensity=[1.0, 1.0, 1.0, 1.0])
    _figure, warnings = create_curve_figure(curve, plot_type="peak_spacing")

    assert any("No peak was detected" in warning for warning in warnings)


def test_show_d_axis_adds_secondary_axis_for_raw_q_plots() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2, 0.3], intensity=[10.0, 8.0, 6.0])
    figure, warnings = create_curve_figure(curve, plot_type="linear", show_d_axis=True)

    assert figure.axes[0].child_axes
    assert any("2\u03c0/q" in warning for warning in warnings)


def test_show_d_axis_warns_for_non_raw_q_plots() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2, 0.3], intensity=[10.0, 8.0, 6.0])
    _figure, warnings = create_curve_figure(curve, plot_type="loglog", show_d_axis=True)

    assert any("not enabled" in warning and "2\u03c0/q" in warning for warning in warnings)
