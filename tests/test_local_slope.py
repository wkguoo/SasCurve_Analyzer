from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import local_slope


def test_local_slope_matches_power_law_alpha() -> None:
    q = np.logspace(-2, 0, 80)
    alpha_true = 2.2
    intensity = 5.0 * q ** (-alpha_true)
    curve = CurveData.create(name="slope", q=q, intensity=intensity)
    result = local_slope(curve, (q.min(), q.max()), window_length=5)
    alpha = np.asarray(result.results["alpha"])
    assert np.allclose(alpha[5:-5], alpha_true, rtol=1e-3)

