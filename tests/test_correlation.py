from __future__ import annotations

import numpy as np

from app.core.correlation import compute_correlation_function
from app.core.data_model import CurveData


def test_correlation_function_exports_real_space_table() -> None:
    q = np.linspace(0.02, 0.4, 100)
    intensity = 1.0 + 10.0 * np.exp(-0.5 * ((q - 0.12) / 0.015) ** 2)
    curve = CurveData.create(name="corr", q=q, intensity=intensity)
    result = compute_correlation_function(curve, (float(q.min()), float(q.max())), {"r_max": 120.0, "r_points": 60})
    assert result.results["export_tables"]["correlation_function"]
    assert len(result.results["r"]) == 60


def test_correlation_function_sorts_q_before_default_rmax() -> None:
    q = np.linspace(0.02, 0.4, 100)
    intensity = 1.0 + 10.0 * np.exp(-0.5 * ((q - 0.12) / 0.015) ** 2)
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_result = compute_correlation_function(sorted_curve, (float(q.min()), float(q.max())), {})
    reversed_result = compute_correlation_function(reversed_curve, (float(q.min()), float(q.max())), {})

    assert np.isclose(reversed_result.results["r"][-1], sorted_result.results["r"][-1])
    assert np.allclose(reversed_result.results["correlation"], sorted_result.results["correlation"])
