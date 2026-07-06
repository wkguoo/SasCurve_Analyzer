from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.invariant_analysis import invariant_with_extrapolation


def test_invariant_requires_assumptions_for_volume_fraction() -> None:
    q = np.linspace(0.01, 0.2, 60)
    curve = CurveData.create(name="inv", q=q, intensity=np.exp(-q))
    result = invariant_with_extrapolation(curve, (float(q.min()), float(q.max())))
    assert result.results["Q_measured"] > 0
    assert result.results["volume_fraction_candidate"] is None
    assert "contrast_required" in result.results["assumptions"]


def test_invariant_with_extrapolation_sorts_q_before_integrating() -> None:
    q = np.linspace(0.01, 0.2, 60)
    intensity = np.exp(-q)
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_result = invariant_with_extrapolation(sorted_curve, (float(q.min()), float(q.max())))
    reversed_result = invariant_with_extrapolation(reversed_curve, (float(q.min()), float(q.max())))

    assert reversed_result.results["Q_measured"] > 0
    assert np.isclose(reversed_result.results["Q_measured"], sorted_result.results["Q_measured"])
