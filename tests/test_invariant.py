from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import information_budget, invariant_measured, kratky_metrics, porod_metrics


def test_finite_q_invariant_matches_numeric_expected() -> None:
    q = np.linspace(0.1, 1.0, 100)
    intensity = 2.0 * q
    curve = CurveData.create(name="inv", q=q, intensity=intensity)
    result = invariant_measured(curve, (0.1, 1.0))
    expected = np.trapezoid(q**2 * intensity, q)
    assert np.isclose(result.results["Q_measured"], expected)
    assert any("finite measured q-range" in warning for warning in result.warnings)


def test_finite_q_invariant_sorts_q_before_integrating() -> None:
    q = np.linspace(0.1, 1.0, 100)
    intensity = 2.0 * q
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_result = invariant_measured(sorted_curve, (0.1, 1.0))
    reversed_result = invariant_measured(reversed_curve, (0.1, 1.0))

    assert reversed_result.results["Q_measured"] > 0
    assert np.isclose(reversed_result.results["Q_measured"], sorted_result.results["Q_measured"])


def test_invariant_reports_negative_intensity_contribution() -> None:
    q = np.array([0.1, 0.2, 0.3, 0.4])
    intensity = np.array([10.0, 8.0, -2.0, -1.0])
    curve = CurveData.create(name="negative_tail", q=q, intensity=intensity)

    result = invariant_measured(curve, (0.1, 0.4))

    assert result.results["negative_intensity_points"] == 2
    assert result.results["negative_contribution_area"] < 0.0
    assert result.results["negative_contribution_fraction"] > 0.0
    assert any("negative" in warning.lower() for warning in result.warnings)


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


def test_information_budget_reports_log_q_contribution_and_quantiles() -> None:
    q = np.array([1.0, 2.0, 3.0, 4.0])
    intensity = np.ones_like(q)
    curve = CurveData.create(name="budget", q=q, intensity=intensity)

    result = information_budget(curve, (1.0, 4.0), q_bands=(2.0, 3.0))

    assert result.analysis_type == "information_budget"
    assert np.allclose(result.results["q3I"], q**3)
    assert np.isclose(result.results["Q_measured"], np.trapezoid(q**2, q))
    assert result.results["q3I_peak_q"] == 4.0
    assert np.isclose(result.results["q3I_peak_d"], 2.0 * np.pi / 4.0)
    assert result.results["q_Q10"] < result.results["q_Q50"] < result.results["q_Q90"]
    assert np.isclose(result.results["d_Q50"], 2.0 * np.pi / result.results["q_Q50"])
    assert result.results["Q_entropy"] > 0.0
    fractions = result.results["Q_low_mid_high_fraction"]
    assert set(fractions) == {"low", "mid", "high"}
    assert np.isclose(sum(fractions.values()), 1.0)

