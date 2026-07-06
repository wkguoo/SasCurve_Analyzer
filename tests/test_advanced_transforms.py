from __future__ import annotations

import numpy as np

from app.core.advanced_transforms import transform_curve
from app.core.correlation import compute_correlation_function
from app.core.data_model import CurveData
from app.core.plugin_base import get_builtin_plugins
from app.core.pr_analysis import compute_pr


def test_q_squared_size_lni_q2i_q4i_transforms() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    assert np.allclose(transform_curve(curve, "q_squared").output, [0.01, 0.04])
    assert np.allclose(transform_curve(curve, "q_to_size").output, 2 * np.pi / curve.q)
    assert np.allclose(transform_curve(curve, "lnI").output, np.log(curve.intensity))
    assert np.allclose(transform_curve(curve, "q2I").output, curve.q**2 * curve.intensity)
    assert np.allclose(transform_curve(curve, "q4I").output, curve.q**4 * curve.intensity)


def test_invalid_q_i_transform_warnings() -> None:
    curve = CurveData.create(name="bad", q=[0.0, 0.2], intensity=[0, 20])
    assert transform_curve(curve, "q_to_size").warnings
    assert transform_curve(curve, "lnI").warnings


def test_pr_placeholder_interface() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 5])
    result = compute_pr(curve, (0.1, 0.2), dmax=50.0)
    assert result.results["experimental"] is True
    assert result.warnings


def test_correlation_placeholder_raises_clear_error() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 5])
    try:
        compute_correlation_function(curve, (0.1, 0.2), {})
    except NotImplementedError as exc:
        assert "reserved" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError")


def test_builtin_plugin_compatibility_layer() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03, 0.04, 0.05], intensity=[100, 90, 80, 70, 60])
    plugins = get_builtin_plugins()
    assert {"guinier", "power_law", "peak_detection", "invariant"}.issubset(plugins)
    execution = plugins["invariant"].safe_run(curve, {"q_range": (0.01, 0.05)})
    assert execution.error is None
    assert execution.result is not None
