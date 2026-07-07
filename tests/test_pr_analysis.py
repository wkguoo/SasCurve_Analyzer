from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.pr_analysis import compute_pr


def test_compute_pr_returns_distribution_and_reliability() -> None:
    q = np.linspace(0.01, 0.25, 80)
    intensity = 100.0 * np.exp(-(25.0**2) * q**2 / 3.0)
    curve = CurveData.create(name="pr", q=q, intensity=intensity)
    result = compute_pr(curve, (float(q.min()), float(q.max())), dmax=120.0, regularization=0.01)
    assert result.results["Dmax"] == 120.0
    assert result.results["Rg_from_pr"] is not None
    assert result.results["reliability_label"] in {"assumption_dependent", "low", "medium"}
    assert len(result.results["export_tables"]["pr_distribution"]) == 80


def test_compute_pr_sorts_q_before_inversion() -> None:
    q = np.linspace(0.01, 0.25, 80)
    intensity = 100.0 * np.exp(-(25.0**2) * q**2 / 3.0)
    sorted_curve = CurveData.create(name="sorted_pr", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed_pr", q=q[::-1], intensity=intensity[::-1])

    sorted_result = compute_pr(sorted_curve, (float(q.min()), float(q.max())), dmax=120.0, regularization=0.01)
    reversed_result = compute_pr(reversed_curve, (float(q.min()), float(q.max())), dmax=120.0, regularization=0.01)

    assert np.allclose(reversed_result.results["P(r)"], sorted_result.results["P(r)"])
    assert np.allclose(reversed_result.results["fit_I"], sorted_result.results["fit_I"])

