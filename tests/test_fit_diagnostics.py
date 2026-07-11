from __future__ import annotations

import json

import numpy as np
import pytest

from app.core.fit_diagnostics import (
    FitDiagnostics,
    build_residual_rows,
    covariance_to_correlation,
    fit_diagnostics,
    parameter_records,
)


def test_fit_diagnostics_reports_complete_statistics() -> None:
    observed = np.array([1.0, 2.0, 4.0, 8.0])
    fitted = np.array([1.1, 1.9, 4.2, 7.8])
    sigma = np.full(4, 0.2)

    result = fit_diagnostics(observed, fitted, parameter_count=2, sigma=sigma)

    required = {
        "n",
        "parameter_count",
        "dof",
        "rss",
        "wrss",
        "rmse",
        "mae",
        "R2",
        "adjusted_R2",
        "chi_square",
        "reduced_chi_square",
        "AIC",
        "AICc",
        "BIC",
    }
    assert required <= result.keys()
    assert result["dof"] == 2
    assert result["weighted"] is True
    assert result["weighted_point_count"] == 4
    assert result["wrss"] == pytest.approx(2.5)


def test_fit_diagnostics_preserves_unweighted_metrics_when_sigma_is_misaligned() -> None:
    observed = np.array([1.0, 2.0, 3.0])
    fitted = np.array([1.1, 1.9, 2.8])

    result = fit_diagnostics(observed, fitted, parameter_count=1, sigma=np.array([0.2, 0.2]))

    assert result["rss"] == pytest.approx(0.06)
    assert result["weighted"] is False
    assert result["weighted_point_count"] == 0
    assert result["wrss"] is None
    assert result["sigma_aligned"] is False
    assert result["weighting_reason"] == "sigma_length_mismatch"


def test_fit_diagnostics_uses_only_finite_positive_sigma_points() -> None:
    observed = np.array([1.0, 2.0, 3.0, np.nan])
    fitted = np.array([1.1, 1.8, 3.5, 4.0])
    sigma = np.array([0.1, 0.0, np.nan, 0.1])

    result = fit_diagnostics(observed, fitted, parameter_count=1, sigma=sigma)

    assert result["n"] == 3
    assert result["weighted"] is True
    assert result["weighted_point_count"] == 1
    assert result["chi_square"] == pytest.approx(1.0)
    assert result["reduced_chi_square"] is None
    assert result["invalid_sigma_point_count"] == 2


def test_fit_diagnostics_uses_absolute_sigma_likelihood_for_information_criteria() -> None:
    observed = np.array([1.0, 2.0, 3.0, 4.0])
    fitted = np.array([1.2, 1.6, 3.2, 3.9])
    sigma = np.full(4, 0.5)

    weighted = fit_diagnostics(observed, fitted, parameter_count=1, sigma=sigma)
    unweighted = fit_diagnostics(observed, fitted, parameter_count=1)

    likelihood_term = 1.0 + 4.0 * np.log(2.0 * np.pi * 0.5**2)
    expected_aic = likelihood_term + 2.0
    assert weighted["chi_square"] == pytest.approx(1.0)
    assert weighted["sigma_is_absolute"] is True
    assert weighted["information_criterion_basis"] == "absolute_sigma_gaussian"
    assert weighted["information_criterion_point_count"] == 4
    assert weighted["information_criterion_reason"] is None
    assert weighted["AIC"] == pytest.approx(expected_aic)
    assert weighted["AICc"] == pytest.approx(expected_aic + 2.0)
    assert weighted["BIC"] == pytest.approx(likelihood_term + np.log(4.0))
    assert weighted["AIC"] != pytest.approx(unweighted["AIC"])
    assert unweighted["information_criterion_basis"] == "unweighted_residual_variance"


def test_fit_diagnostics_with_relative_sigma_withholds_information_criteria() -> None:
    result = fit_diagnostics(
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array([1.2, 1.6, 3.2, 3.9]),
        parameter_count=1,
        sigma=np.full(4, 0.5),
        sigma_is_absolute=False,
    )

    assert result["weighted"] is True
    assert result["sigma_is_absolute"] is False
    assert result["information_criterion_basis"] == "unavailable_relative_sigma"
    assert result["information_criterion_point_count"] == 4
    assert result["information_criterion_reason"] == "relative_sigma"
    assert result["AIC"] is None
    assert result["AICc"] is None
    assert result["BIC"] is None


def test_fit_diagnostics_does_not_report_adjusted_or_reduced_statistics_without_dof() -> None:
    result = fit_diagnostics(
        np.array([1.0, 2.0]),
        np.array([1.1, 1.9]),
        parameter_count=2,
        sigma=np.array([0.1, 0.1]),
    )

    assert result["dof"] == 0
    assert result["adjusted_R2"] is None
    assert result["reduced_chi_square"] is None


def test_fit_diagnostics_rejects_mismatched_observed_and_fitted_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        fit_diagnostics(np.array([1.0, 2.0]), np.array([1.0]), parameter_count=1)


def test_fit_diagnostics_dataclass_is_serializable_without_numpy_scalars() -> None:
    diagnostics = FitDiagnostics(
        n=np.int64(2),
        parameter_count=np.int64(1),
        dof=np.int64(1),
        rss=np.float32(0.5),
        wrss=np.float64(np.nan),
        AIC=np.float64(np.inf),
        weighted=np.bool_(True),
        sigma_is_absolute=np.bool_(True),
        sigma_aligned=np.bool_(False),
        invalid_sigma_point_count=np.int64(1),
        non_finite_weighted_residual_point_count=np.int64(2),
        information_criterion_point_count=np.int64(2),
        information_criterion_basis=np.str_("absolute_sigma_gaussian"),
        information_criterion_reason=np.str_("example"),
    )

    payload = diagnostics.to_dict()

    assert payload["n"] == 2
    assert type(payload["rss"]) is float
    assert payload["wrss"] is None
    assert payload["AIC"] is None
    assert payload["weighted"] is True
    assert payload["sigma_is_absolute"] is True
    assert type(payload["information_criterion_basis"]) is str
    assert all(not isinstance(value, np.generic) for value in payload.values())
    assert json.loads(json.dumps(payload))["information_criterion_point_count"] == 2


def test_parameter_records_include_bounds_ci_and_tolerant_bound_hits() -> None:
    values = np.array([10.00000001, 2.0])
    initial = np.array([9.0, 1.5])
    stderr = np.array([0.5, np.nan])
    lower = np.array([0.0, -np.inf])
    upper = np.array([10.0, np.inf])
    values_before = values.copy()

    rows = parameter_records(
        ["Rg", "background"],
        values,
        units=["A", "a.u."],
        initial=initial,
        bounds=(lower, upper),
        stderr=stderr,
        bound_tolerance=1e-6,
    )

    assert set(rows[0]) == {
        "name",
        "value",
        "unit",
        "initial",
        "lower_bound",
        "upper_bound",
        "stderr",
        "ci95_low",
        "ci95_high",
        "bound_hit",
    }
    assert rows[0]["bound_hit"] is True
    assert rows[0]["ci95_low"] == pytest.approx(9.02)
    assert rows[0]["ci95_high"] == pytest.approx(10.98)
    assert rows[1]["stderr"] is None
    assert rows[1]["ci95_low"] is None
    assert rows[1]["bound_hit"] is None
    np.testing.assert_array_equal(values, values_before)


def test_parameter_records_accept_name_keyed_optional_values() -> None:
    rows = parameter_records(
        ["scale", "background"],
        [20.0, 1.0],
        units={"scale": "cm^-1", "background": "cm^-1"},
        initial={"scale": 10.0},
        bounds={"scale": (0.0, 30.0)},
        stderr={"scale": 2.0},
    )

    assert rows[0]["initial"] == 10.0
    assert rows[0]["ci95_high"] == pytest.approx(23.92)
    assert rows[0]["lower_bound"] == 0.0
    assert rows[0]["upper_bound"] == 30.0
    assert rows[1]["initial"] is None
    assert rows[1]["lower_bound"] is None


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        (((0.0, 1.0), (-2.0, 2.0)), [(0.0, 1.0), (-2.0, 2.0)]),
        ([(0.0, 1.0), (-2.0, 2.0)], [(0.0, 1.0), (-2.0, 2.0)]),
        (np.array([[0.0, 1.0], [-2.0, 2.0]]), [(0.0, 1.0), (-2.0, 2.0)]),
        ((np.array([0.0, -2.0]), np.array([1.0, 2.0])), [(0.0, 1.0), (-2.0, 2.0)]),
    ],
)
def test_parameter_records_supports_documented_bounds_shapes(bounds, expected) -> None:
    rows = parameter_records(["a", "b"], [0.5, 0.5], bounds=bounds)

    assert [(row["lower_bound"], row["upper_bound"]) for row in rows] == expected


def test_singular_covariance_returns_null_correlations() -> None:
    correlation = covariance_to_correlation(np.array([[1.0, np.nan], [np.nan, 1.0]]))

    assert correlation[0][0] == 1.0
    assert correlation[0][1] is None
    assert correlation[1][0] is None
    assert correlation[1][1] == 1.0


def test_covariance_to_correlation_handles_zero_variance_and_rejects_non_square_input() -> None:
    correlation = covariance_to_correlation(np.array([[0.0, 0.0], [0.0, 1.0]]))

    assert correlation == [[None, None], [None, 1.0]]
    with pytest.raises(ValueError, match="square"):
        covariance_to_correlation(np.ones((2, 3)))


def test_covariance_to_correlation_rejects_materially_non_psd_matrix() -> None:
    covariance = np.array(
        [
            [1.0, 0.9, 0.9],
            [0.9, 1.0, -0.9],
            [0.9, -0.9, 1.0],
        ]
    )

    with pytest.raises(ValueError, match="positive semidefinite"):
        covariance_to_correlation(covariance)


def test_covariance_to_correlation_tolerates_negligible_negative_eigenvalue_from_roundoff() -> None:
    covariance = np.array([[1.0, 1.0 + 1e-12], [1.0 + 1e-12, 1.0]])

    correlation = covariance_to_correlation(covariance)

    assert correlation == [[1.0, 1.0], [1.0, 1.0]]


def test_residual_rows_record_inclusion_and_standardized_residual() -> None:
    rows = build_residual_rows(
        np.array([0.1]),
        np.array([2.0]),
        np.array([1.5]),
        sigma=np.array([0.25]),
    )

    assert rows[0]["residual"] == 0.5
    assert rows[0]["standardized_residual"] == 2.0
    assert rows[0]["weight"] == 16.0
    assert rows[0]["included"] is True
    assert rows[0]["exclusion_reason"] is None


def test_residual_rows_keep_all_original_rows_and_mark_nonfinite_inputs() -> None:
    q = np.array([0.1, np.nan, 0.3])
    observed = np.array([2.0, 3.0, np.nan])
    fitted = np.array([1.5, 3.0, 2.5])
    sigma = np.array([0.25, -1.0, np.nan])
    q_before = q.copy()

    rows = build_residual_rows(q, observed, fitted, sigma=sigma)

    assert len(rows) == 3
    assert rows[0]["included"] is True
    assert rows[1]["included"] is False
    assert "non_finite_q" in rows[1]["exclusion_reason"]
    assert rows[1]["residual"] is None
    assert rows[2]["included"] is False
    assert "non_finite_observed" in rows[2]["exclusion_reason"]
    assert rows[2]["sigma"] is None
    np.testing.assert_equal(q, q_before)


def test_residual_rows_reject_mismatched_sigma_length() -> None:
    with pytest.raises(ValueError, match="same length"):
        build_residual_rows(
            np.array([0.1, 0.2]),
            np.array([2.0, 3.0]),
            np.array([1.5, 2.5]),
            sigma=np.array([0.1]),
        )


def test_fit_diagnostics_separates_valid_sigma_from_nonfinite_weighted_residual() -> None:
    largest = np.finfo(float).max

    result = fit_diagnostics(
        np.array([largest]),
        np.array([-largest]),
        parameter_count=0,
        sigma=np.array([1.0]),
    )

    assert result["sigma_aligned"] is True
    assert result["invalid_sigma_point_count"] == 0
    assert result["non_finite_weighted_residual_point_count"] == 1
    assert result["weighted"] is False
    assert result["wrss"] is None
    assert result["weighting_reason"] == "non_finite_weighted_residual"
