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


def test_local_slope_sorts_unsorted_q_before_gradient() -> None:
    q = np.logspace(-2, 0, 80)
    alpha_true = 2.2
    intensity = 5.0 * q ** (-alpha_true)
    order = np.r_[40:80, 0:40]
    curve = CurveData.create(name="slope", q=q[order], intensity=intensity[order])

    result = local_slope(curve, (q.min(), q.max()), window_length=5)
    q_mid = np.asarray(result.results["q_mid"])
    alpha = np.asarray(result.results["alpha"])

    assert np.all(np.diff(q_mid) > 0)
    assert np.allclose(alpha[5:-5], alpha_true, rtol=1e-3)


def test_local_slope_warns_and_excludes_duplicate_q() -> None:
    q = np.array([0.1, 0.2, 0.2, 0.4, 0.8])
    intensity = 5.0 * q ** -2
    curve = CurveData.create(name="duplicate_q", q=q, intensity=intensity)

    result = local_slope(curve, (0.1, 0.8), window_length=3)
    q_mid = np.asarray(result.results["q_mid"])
    alpha = np.asarray(result.results["alpha"])

    assert np.all(np.diff(q_mid) > 0)
    assert np.all(np.isfinite(alpha))
    assert any("duplicate q" in warning for warning in result.warnings)

