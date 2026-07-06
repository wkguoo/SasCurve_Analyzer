from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import guinier_analysis


def test_guinier_recovers_rg_and_i0() -> None:
    q = np.linspace(0.01, 0.08, 30)
    rg_true = 8.0
    i0_true = 120.0
    intensity = i0_true * np.exp(-(rg_true**2) * q**2 / 3.0)
    error = 0.02 * intensity
    curve = CurveData.create(name="guinier", q=q, intensity=intensity, error=error)
    result = guinier_analysis(curve, (0.01, 0.08))
    assert np.isclose(result.results["Rg"], rg_true, rtol=1e-3)
    assert np.isclose(result.results["I0"], i0_true, rtol=1e-3)
    assert result.results["fit_points"] == 30


def test_guinier_non_negative_slope_warns() -> None:
    q = np.linspace(0.01, 0.08, 20)
    intensity = 10.0 + q
    curve = CurveData.create(name="bad", q=q, intensity=intensity)
    result = guinier_analysis(curve, (0.01, 0.08))
    assert result.results["Rg"] is None
    assert any("non-negative" in warning for warning in result.warnings)


def test_guinier_qrg_warning() -> None:
    q = np.linspace(0.05, 0.25, 30)
    rg_true = 10.0
    intensity = 100.0 * np.exp(-(rg_true**2) * q**2 / 3.0)
    curve = CurveData.create(name="high_q", q=q, intensity=intensity)
    result = guinier_analysis(curve, (0.05, 0.25))
    assert result.results["qRg_max"] > 1.3
    assert any("qRg_max" in warning for warning in result.warnings)

