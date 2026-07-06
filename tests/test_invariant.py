from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import invariant_measured, kratky_metrics, porod_metrics


def test_finite_q_invariant_matches_numeric_expected() -> None:
    q = np.linspace(0.1, 1.0, 100)
    intensity = 2.0 * q
    curve = CurveData.create(name="inv", q=q, intensity=intensity)
    result = invariant_measured(curve, (0.1, 1.0))
    expected = np.trapezoid(q**2 * intensity, q)
    assert np.isclose(result.results["Q_measured"], expected)
    assert any("finite measured q-range" in warning for warning in result.warnings)


def test_kratky_metrics_reports_maximum() -> None:
    q = np.array([0.1, 0.2, 0.3])
    intensity = np.array([1.0, 10.0, 1.0])
    curve = CurveData.create(name="kratky", q=q, intensity=intensity)
    result = kratky_metrics(curve, (0.1, 0.3))
    assert result.results["q_K"] == 0.2
    assert result.results["d_K"] > 0


def test_porod_metrics_reports_plateau_statistics() -> None:
    q = np.linspace(1.0, 2.0, 20)
    intensity = 3.0 / q**4
    curve = CurveData.create(name="porod", q=q, intensity=intensity)
    result = porod_metrics(curve, (1.0, 2.0))
    assert np.isclose(result.results["q4I_plateau_mean"], 3.0)
    assert result.results["q4I_plateau_cv"] < 1e-12

