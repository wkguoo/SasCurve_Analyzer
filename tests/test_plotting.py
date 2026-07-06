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

