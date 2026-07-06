from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import power_law_analysis


def test_power_law_recovers_alpha() -> None:
    q = np.logspace(-2, 0, 50)
    alpha_true = 3.5
    intensity = 2.0 * q ** (-alpha_true)
    curve = CurveData.create(name="power", q=q, intensity=intensity)
    result = power_law_analysis(curve, (q.min(), q.max()))
    assert np.isclose(result.results["alpha"], alpha_true, rtol=1e-6)


def test_power_law_filters_invalid_points() -> None:
    curve = CurveData.create(name="invalid", q=[0.0, 0.1, 0.2], intensity=[10.0, -1.0, 2.0])
    result = power_law_analysis(curve, (0.0, 0.2), min_points=2)
    assert result.results["fit_points"] == 1
    assert any("I(q) <= 0" in warning or "Too few" in warning for warning in result.warnings)

