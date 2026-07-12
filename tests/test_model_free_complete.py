from __future__ import annotations

import math

import numpy as np

from app.core.data_model import CurveData
from app.core.model_free import guinier_analysis, local_slope, power_law_analysis


def _guinier_intensity(q: np.ndarray, *, rg: float = 8.0, i0: float = 120.0) -> np.ndarray:
    return i0 * np.exp(-(rg**2) * q**2 / 3.0)


def test_guinier_contains_complete_traceable_contract_and_exclusions() -> None:
    q = np.array([0.005, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    intensity = _guinier_intensity(np.maximum(q, 0.01))
    intensity[1] = -1.0
    curve = CurveData.create(name="guinier_contract", q=q, intensity=intensity)

    result = guinier_analysis(curve, (0.01, 0.05), min_points=5)
    values = result.results

    required = {
        "Rg",
        "I0",
        "slope",
        "intercept",
        "q_start",
        "q_end",
        "qminRg",
        "qmaxRg",
        "fit_points",
        "excluded_points",
        "weighted_fit",
        "parameter_records",
        "fit_quality",
        "residual_rows",
        "excluded_rows",
        "validity",
        "assumptions",
        "warnings",
    }
    assert required <= values.keys()
    assert {"R2", "rmse", "chi_square", "reduced_chi_square", "AICc", "BIC", "information_criterion_basis"} <= values["fit_quality"].keys()
    assert values["fit_points"] == 5
    assert values["excluded_points"] == 3
    assert [row["original_index"] for row in values["excluded_rows"]] == [0, 1, 7]
    assert all({"original_index", "q", "intensity", "error", "reason"} <= row.keys() for row in values["excluded_rows"])
    assert len(values["residual_rows"]) == values["fit_points"]
    assert all(row["original_index"] >= 2 for row in values["residual_rows"])
    assert values["q_start"] == 0.01
    assert values["q_end"] == 0.05
    assert values["qminRg"] is not None
    assert values["qmaxRg"] is not None
    assert {"Rg", "I0", "slope", "intercept"} <= {row["name"] for row in values["parameter_records"]}


def test_guinier_invalid_rg_records_clear_reason_and_native_nulls() -> None:
    q = np.linspace(0.01, 0.08, 12)
    curve = CurveData.create(name="nonnegative_slope", q=q, intensity=10.0 + q)

    result = guinier_analysis(curve, (0.01, 0.08))
    values = result.results

    assert values["Rg"] is None
    assert values["qminRg"] is None
    assert values["qmaxRg"] is None
    assert values["validity"]["Rg_valid"] is False
    assert "non-negative" in values["validity"]["Rg_reason"]
    rg_record = next(row for row in values["parameter_records"] if row["name"] == "Rg")
    assert rg_record["value"] is None
    assert rg_record["stderr"] is None


def test_power_law_uses_all_valid_propagated_log_errors_for_weighted_fit() -> None:
    q = np.logspace(-2, -0.4, 25)
    alpha_true = 3.2
    intensity = 2.5 * q ** (-alpha_true)
    error = 0.03 * intensity
    curve = CurveData.create(name="power_weighted", q=q, intensity=intensity, error=error)

    result = power_law_analysis(curve, (float(q.min()), float(q.max())))
    values = result.results

    assert math.isclose(values["alpha"], alpha_true, rel_tol=1e-7)
    assert values["weighted_fit"] is True
    assert values["fit_quality"]["weighted"] is True
    assert values["fit_quality"]["information_criterion_basis"] == "absolute_sigma_gaussian"
    assert all(row["weighting_valid"] for row in values["residual_rows"])
    assert values["eligible_points"] == q.size
    assert values["actual_fit_points"] == q.size
    assert values["fit_not_performed_rows"] == []
    assert values["uncertainty"]["alpha"] is not None
    assert {"alpha", "prefactor", "slope", "intercept"} <= {row["name"] for row in values["parameter_records"]}


def test_power_law_partial_invalid_errors_falls_back_to_unweighted_without_dropping_log_valid_points() -> None:
    q = np.logspace(-2, -0.4, 10)
    intensity = 1.5 * q ** -2.4
    error = 0.04 * intensity
    error[3] = 0.0
    curve = CurveData.create(name="power_partial_error", q=q, intensity=intensity, error=error)

    result = power_law_analysis(curve, (float(q.min()), float(q.max())))
    values = result.results

    assert values["fit_points"] == q.size
    assert values["weighted_fit"] is False
    assert values["fit_quality"]["weighted"] is False
    assert values["error_audit"]["invalid_transformed_sigma_points"] == 1
    assert values["fit_quality"]["information_criterion_basis"] == "unweighted_residual_variance"


def test_local_slope_reports_point_validity_and_complete_plateau_rows() -> None:
    q = np.logspace(-2, 0, 21)
    intensity = 4.0 * q ** -2.2
    curve = CurveData.create(name="local_slope_contract", q=q, intensity=intensity)

    result = local_slope(curve, (float(q.min()), float(q.max())), window_length=5, std_threshold=0.15)
    values = result.results

    assert {"point_rows", "plateaus", "excluded_rows", "validity", "assumptions", "warnings"} <= values.keys()
    assert len(values["point_rows"]) == q.size
    assert all({"q", "alpha", "valid", "reason"} <= row.keys() for row in values["point_rows"])
    assert all(row["valid"] for row in values["point_rows"])
    assert values["plateaus"]
    required_plateau = {"plateau_id", "q_start", "q_end", "alpha_mean", "alpha_std", "point_count", "stability_score"}
    assert all(required_plateau <= row.keys() for row in values["plateaus"])
    assert all(0.0 <= row["stability_score"] <= 1.0 for row in values["plateaus"])


def test_local_slope_retains_single_center_as_invalid_when_neighbors_are_insufficient() -> None:
    curve = CurveData.create(name="single_slope", q=[0.02], intensity=[100.0])

    result = local_slope(curve, (0.02, 0.02), window_length=1)
    row = result.results["point_rows"][0]

    assert row["q"] == 0.02
    assert row["alpha"] is None
    assert row["valid"] is False
    assert row["reason"] == "insufficient_neighbors"


def test_power_law_absolute_sigma_uses_unscaled_wls_covariance_for_parameter_ci() -> None:
    q = np.logspace(-2, -0.4, 25)
    intensity = 2.5 * q ** -3.2
    error = 0.03 * intensity
    curve = CurveData.create(name="power_absolute_sigma_ci", q=q, intensity=intensity, error=error)

    result = power_law_analysis(curve, (float(q.min()), float(q.max())))
    values = result.results
    sigma = error / (intensity * np.log(10.0))
    design = np.column_stack((np.log10(q), np.ones(q.size)))
    expected_covariance = np.linalg.inv(design.T @ np.diag(1.0 / sigma**2) @ design)
    expected_slope_stderr = math.sqrt(expected_covariance[0, 0])
    alpha_record = next(row for row in values["parameter_records"] if row["name"] == "alpha")

    assert values["weighted_fit"] is True
    assert math.isclose(values["uncertainty"]["slope"], expected_slope_stderr, rel_tol=1e-10)
    assert math.isclose(alpha_record["ci95_high"] - values["alpha"], 1.96 * expected_slope_stderr, rel_tol=1e-10)
    assert values["uncertainty"]["slope"] > 1e-3


def test_local_slope_does_not_claim_ordinary_least_squares_or_error_weighting() -> None:
    q = np.logspace(-2, 0, 9)
    curve = CurveData.create(name="local_slope_no_fit", q=q, intensity=3.0 * q ** -2.0)

    result = local_slope(curve, (float(q.min()), float(q.max())), window_length=3)
    audit = result.results["error_audit"]

    assert audit["strategy"] == "not_used_for_local_derivative"
    assert audit["weighting_decision"] == "not_applicable"
    assert "weighted_fit" not in result.results
    assert all("ordinary least squares" not in warning.lower() for warning in result.warnings)


def test_guinier_reports_eligible_but_not_actually_fitted_points() -> None:
    curve = CurveData.create(name="one_guinier_point", q=[0.02], intensity=[100.0], error=[1.0])

    result = guinier_analysis(curve, (0.02, 0.02))
    values = result.results

    assert values["fit_points"] == 1  # legacy selected-domain count
    assert values["eligible_points"] == 1
    assert values["actual_fit_points"] == 0
    assert values["residual_rows"] == []
    assert values["fit_quality"]["n"] == 0
    assert values["weighted_fit"] is False
    assert values["error_audit"]["weighting_decision"] == "no_fit_performed"
    assert values["fit_not_performed_rows"] == [
        {
            "original_index": 0,
            "q": 0.02,
            "intensity": 100.0,
            "error": 1.0,
            "reason": "fit_not_performed",
            "included_in_fit": False,
        }
    ]


def test_power_law_reports_duplicate_transformed_x_as_not_fitted() -> None:
    curve = CurveData.create(name="same_q", q=[0.1, 0.1], intensity=[100.0, 100.0], error=[1.0, 1.0])

    result = power_law_analysis(curve, (0.1, 0.1), min_points=2)
    values = result.results

    assert values["eligible_points"] == 2
    assert values["actual_fit_points"] == 0
    assert len(values["fit_not_performed_rows"]) == 2
    assert {row["reason"] for row in values["fit_not_performed_rows"]} == {"fit_not_performed"}
    assert values["fit_quality"]["n"] == 0
