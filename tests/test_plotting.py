from __future__ import annotations

from app.core.data_model import CurveData
from app.core.plotting import create_curve_figure


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


def test_q3_invariant_contribution_plot_uses_log_q_axis() -> None:
    curve = CurveData.create(name="test", q=[1.0, 2.0, 4.0], intensity=[1.0, 2.0, 3.0])
    figure, warnings = create_curve_figure(curve, plot_type="invariant_contribution")

    assert not warnings
    axis = figure.axes[0]
    assert axis.get_xlabel().startswith("ln q")
    assert axis.get_ylabel().startswith("q^3 I(q)")
    assert list(axis.lines[0].get_ydata()) == [1.0, 16.0, 192.0]


def test_linear_plot_sorts_unsorted_q_for_scientific_curve_reading() -> None:
    curve = CurveData.create(name="test", q=[0.3, 0.1, 0.2], intensity=[30.0, 10.0, 20.0])

    figure, warnings = create_curve_figure(curve, plot_type="linear")

    assert not warnings
    axis = figure.axes[0]
    assert list(axis.lines[0].get_xdata()) == [0.1, 0.2, 0.3]
    assert list(axis.lines[0].get_ydata()) == [10.0, 20.0, 30.0]

