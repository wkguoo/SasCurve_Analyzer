from __future__ import annotations

import warnings

import numpy as np
import pytest

from app.core.data_model import CurveData
from app.core.correlation import compute_correlation_function
from app.core.invariant_analysis import invariant_with_extrapolation
from app.core.lamellar_analysis import lamellar_analysis
from app.core.metric_registry import METHOD_REGISTRY
from app.core.pr_analysis import compute_pr


def _pr_curve() -> CurveData:
    q = np.linspace(0.01, 0.3, 80)
    intensity = 100.0 * np.exp(-(25.0**2) * q**2 / 3.0)
    return CurveData.create(name="pr_contract", q=q, intensity=intensity)


def _curve() -> CurveData:
    q = np.linspace(0.01, 0.2, 60)
    return CurveData.create(name="invariant_contract", q=q, intensity=np.exp(-q))


def test_pr_contract_contains_backfit_and_stability() -> None:
    result = compute_pr(_pr_curve(), (0.01, 0.3), dmax=100.0, regularization=1e-2)

    assert {
        "Dmax",
        "Rg_pr",
        "peak_r",
        "peak_height",
        "peak_count",
        "tail_score",
        "negative_fraction",
        "smoothness",
        "backfit_rmse",
        "backfit_chi_square",
    } <= result.results.keys()
    assert "pr_distribution" in result.results["export_tables"]


def test_pr_contract_records_nonapplicable_absolute_prerequisites() -> None:
    result = compute_pr(_pr_curve(), (0.01, 0.3), dmax=100.0, regularization=1e-2)

    assert {"sample_type", "absolute_intensity", "contrast", "q_extrapolation", "porod_plateau"} <= result.results["prerequisites"].keys()
    assert result.results["prerequisites"]["absolute_intensity"]["status"] == "not_required"
    assert result.results["prerequisites"]["contrast"]["status"] == "not_required"
    assert {"q", "I_observed", "I_back_calculated", "residual"} <= result.results["export_tables"]["pr_backfit"][0].keys()
    assert result.results["backfit_chi_square"] is None
    assert result.results["backfit_chi_square_status"] == "missing_prerequisite"
    assert result.results["reliability_label"] != "high"


def test_conditional_absolute_quantities_are_null_with_reason_without_contrast() -> None:
    result = invariant_with_extrapolation(_curve(), (0.01, 0.2), absolute_intensity=False, contrast=None)

    assert result.results["volume_fraction"] is None
    assert result.results["volume_fraction_status"] == "missing_prerequisite"


def test_invariant_marks_unavailable_porod_tail_without_inventing_a_zero() -> None:
    q = np.array([0.1, 0.2])
    curve = CurveData.create(name="short_invariant_contract", q=q, intensity=np.ones_like(q))

    result = invariant_with_extrapolation(curve, (0.1, 0.2), high_q_method="porod_q^-4")

    assert result.results["Q_high_q_extrapolated"] is None
    assert result.results["high_q_extrapolation_status"] == "missing_prerequisite"
    assert result.results["high_q_extrapolation_invalid_reason"]


def test_invariant_volume_fraction_stays_assumption_dependent_without_sample_confirmation() -> None:
    q = np.linspace(0.01, 0.2, 60)
    curve = CurveData.create(name="conditional_volume_fraction", q=q, intensity=np.exp(-q))

    result = invariant_with_extrapolation(curve, (0.01, 0.2), absolute_intensity=True, contrast=1.0)

    assert result.results["volume_fraction"] is not None
    assert result.results["volume_fraction_status"] == "assumption_dependent"
    assert result.results["reliability_label"] != "high"


def test_invariant_contract_contains_selected_integrand_table() -> None:
    result = invariant_with_extrapolation(_curve(), (0.01, 0.2))

    table = result.results["export_tables"]["invariant_integrand"]
    assert len(table) == 60
    assert {"q", "I_observed", "q_squared_I"} <= table[0].keys()


def test_correlation_contract_contains_conditional_length_parameters() -> None:
    q = np.linspace(0.02, 0.4, 100)
    intensity = 1.0 + 10.0 * np.exp(-0.5 * ((q - 0.12) / 0.015) ** 2)
    curve = CurveData.create(name="correlation_contract", q=q, intensity=intensity)

    result = compute_correlation_function(curve, (0.02, 0.4), {"r_max": 120.0, "r_points": 60})

    assert {
        "long_period",
        "long_period_status",
        "long_period_invalid_reason",
        "interface_thickness",
        "interface_thickness_status",
        "interface_thickness_invalid_reason",
        "q_extrapolation_status",
        "prerequisites",
        "assumption_status",
    } <= result.results.keys()
    assert {"r", "correlation"} <= result.results["export_tables"]["correlation_function"][0].keys()
    assert result.results["reliability_label"] != "high"


def test_lamellar_contract_contains_q0_d0_and_order_deviation() -> None:
    q = np.linspace(0.05, 0.5, 400)
    q0 = 0.12
    intensity = 1.0 + 20.0 * np.exp(-0.5 * ((q - q0) / 0.008) ** 2) + 10.0 * np.exp(-0.5 * ((q - 2.0 * q0) / 0.008) ** 2)
    curve = CurveData.create(name="lamellar_contract", q=q, intensity=intensity)

    result = lamellar_analysis(curve, (0.05, 0.5), prominence=5.0)

    assert {
        "q0",
        "q0_status",
        "q0_invalid_reason",
        "d0",
        "d0_status",
        "d0_invalid_reason",
        "order_index_backfit_rmse",
        "prerequisites",
        "assumption_status",
    } <= result.results.keys()
    assert {"order_index", "deviation_from_integer_order"} <= result.results["export_tables"]["peaks"][1].keys()
    assert np.isclose(result.results["d0"], 2.0 * np.pi / q0, rtol=0.02)
    assert result.results["reliability_label"] != "high"


def _assert_registered_metrics_are_finite_or_explained(result, method_id: str) -> None:
    for spec in METHOD_REGISTRY[method_id].metrics:
        metric = spec.name
        assert metric in result.results
        value = result.results[metric]
        if value is None:
            assert result.results[f"{metric}_status"] in {
                "missing_prerequisite",
                "invalid_value",
                "not_requested",
            }
            assert result.results[f"{metric}_invalid_reason"]
        elif isinstance(value, list):
            assert value
            assert all(np.isfinite(item) for item in value)
        else:
            assert np.isfinite(value)


def test_every_task4_result_contains_registered_metrics_with_safe_unavailable_values() -> None:
    invariant = invariant_with_extrapolation(_curve(), (0.01, 0.2))

    q_corr = np.linspace(0.02, 0.4, 100)
    corr_curve = CurveData.create(
        name="registry_correlation",
        q=q_corr,
        intensity=1.0 + 10.0 * np.exp(-0.5 * ((q_corr - 0.12) / 0.015) ** 2),
    )
    correlation = compute_correlation_function(corr_curve, (0.02, 0.4), {"r_max": 120.0, "r_points": 60})

    q_lamellar = np.linspace(0.05, 0.5, 400)
    lamellar_curve = CurveData.create(
        name="registry_lamellar",
        q=q_lamellar,
        intensity=1.0
        + 20.0 * np.exp(-0.5 * ((q_lamellar - 0.12) / 0.008) ** 2)
        + 10.0 * np.exp(-0.5 * ((q_lamellar - 0.24) / 0.008) ** 2),
    )
    lamellar = lamellar_analysis(lamellar_curve, (0.05, 0.5), prominence=5.0)

    _assert_registered_metrics_are_finite_or_explained(invariant, "invariant")
    _assert_registered_metrics_are_finite_or_explained(correlation, "correlation")
    _assert_registered_metrics_are_finite_or_explained(lamellar, "lamellar")


def test_invariant_registered_q_bands_are_measured_range_integrals_not_tail_aliases() -> None:
    q = np.linspace(0.03, 0.33, 301)
    curve = CurveData.create(name="invariant_bands", q=q, intensity=np.ones_like(q))

    result = invariant_with_extrapolation(curve, (0.03, 0.33))

    first_boundary = (2.0 * 0.03 + 0.33) / 3.0
    second_boundary = (0.03 + 2.0 * 0.33) / 3.0
    assert np.isclose(result.results["Q_low"], (first_boundary**3 - 0.03**3) / 3.0, rtol=1e-5)
    assert np.isclose(result.results["Q_mid"], (second_boundary**3 - first_boundary**3) / 3.0, rtol=1e-5)
    assert np.isclose(result.results["Q_high"], (0.33**3 - second_boundary**3) / 3.0, rtol=1e-5)
    assert result.results["q_band_boundaries"] == {"low_mid": first_boundary, "mid_high": second_boundary}
    assert result.results["Q_band_definition"] == {
        "integrand": "q^2 I(q)",
        "range": "selected finite q range",
        "partition": "three equal q-width bands",
        "tail_extrapolations_are_excluded": True,
    }


def _assert_no_nan_or_infinity(value) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_nan_or_infinity(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_no_nan_or_infinity(nested)
    elif isinstance(value, (float, np.floating, int, np.integer)) and not isinstance(value, bool):
        assert np.isfinite(value)


def test_pr_insufficient_points_exports_no_placeholder_distribution_or_nan_backfit() -> None:
    q = np.linspace(0.01, 0.1, 10)
    curve = CurveData.create(name="short_pr", q=q, intensity=np.exp(-q))

    result = compute_pr(curve, (0.01, 0.1), dmax=80.0, regularization=1e-2)

    assert result.results["r"] == []
    assert result.results["P(r)"] == []
    assert result.results["fit_q"] == []
    assert result.results["fit_I"] == []
    assert result.results["residuals"] == []
    assert result.results["peak_count"] is None
    assert result.results["negative_fraction"] is None
    assert result.results["peak_count_status"] == "missing_prerequisite"
    assert result.results["negative_fraction_status"] == "missing_prerequisite"
    assert result.results["export_tables"]["pr_distribution"] == []
    assert result.results["export_tables"]["pr_backfit"] == []
    _assert_no_nan_or_infinity(result.results)


def test_invariant_insufficient_or_overflowed_integrals_are_none_with_reasons() -> None:
    cases = (
        ("single_point", np.array([0.1]), np.array([1.0])),
        ("overflowed_integrand", np.array([1.0e200, 2.0e200, 3.0e200]), np.ones(3)),
    )

    for name, q, intensity in cases:
        curve = CurveData.create(name=name, q=q, intensity=intensity)
        result = invariant_with_extrapolation(curve, (float(q.min()), float(q.max())))

        for metric in ("Q_measured", "Q_mid", "Q_total"):
            assert result.results[metric] is None
            assert result.results[f"{metric}_status"] in {"missing_prerequisite", "invalid_value"}
            assert result.results[f"{metric}_invalid_reason"]
        _assert_no_nan_or_infinity(result.results)


@pytest.mark.parametrize("r_max", [np.nan, np.inf, -1.0, 0.0])
def test_correlation_rejects_nonfinite_or_nonpositive_r_max(r_max: float) -> None:
    q = np.linspace(0.02, 0.4, 100)
    curve = CurveData.create(name="invalid_rmax", q=q, intensity=np.exp(-q))

    with pytest.raises(ValueError, match="r_max must be a finite positive number"):
        compute_correlation_function(curve, (0.02, 0.4), {"r_max": r_max})


def test_lamellar_tiny_q_derivatives_are_withheld_when_they_overflow() -> None:
    q = np.array([1.0e-320, 2.0e-320, 3.0e-320, 4.0e-320, 5.0e-320])
    intensity = np.array([1.0, 1.0, 10.0, 1.0, 1.0])
    curve = CurveData.create(name="tiny_lamellar", q=q, intensity=intensity)

    result = lamellar_analysis(curve, (float(q.min()), float(q.max())), prominence=1.0)

    assert result.results["q0"] is not None
    assert result.results["d0"] is None
    assert result.results["d0_status"] == "invalid_value"
    assert result.results["d0_invalid_reason"]
    _assert_no_nan_or_infinity(result.results)
    _assert_no_nan_or_infinity(result.results["export_tables"]["peaks"])


def test_correlation_overflowed_transform_never_exports_nonfinite_scalars_or_rows() -> None:
    q = np.linspace(1.0e200, 2.0e200, 20)
    curve = CurveData.create(name="overflowed_correlation", q=q, intensity=np.ones_like(q))

    result = compute_correlation_function(curve, (float(q.min()), float(q.max())), {"r_max": 120.0, "r_points": 30})

    assert result.results["transform_normalization"] is None
    assert result.results["transform_normalization_status"] in {"missing_prerequisite", "invalid_value"}
    assert result.results["transform_normalization_invalid_reason"]
    _assert_no_nan_or_infinity(result.results)
    _assert_no_nan_or_infinity(result.results["export_tables"]["correlation_function"])


def test_invariant_porod_requires_every_tail_value_to_be_finite_and_strictly_positive() -> None:
    q = np.linspace(0.01, 0.5, 1000)
    intensity = q**-4
    intensity[-1] = 0.0
    curve = CurveData.create(name="porod_zero_tail", q=q, intensity=intensity)

    result = invariant_with_extrapolation(curve, (0.01, 0.5), high_q_method="porod_q^-4")

    assert result.results["porod_plateau_status"] == "invalid_value"
    assert result.results["Q_high_q_extrapolated"] is None
    assert result.results["high_q_extrapolation_status"] == "invalid_value"
    assert result.results["porod_plateau_invalid_reason"]


def test_invariant_requested_short_porod_tail_is_a_failed_prerequisite() -> None:
    q = np.array([0.1, 0.2])
    curve = CurveData.create(name="short_porod", q=q, intensity=q**-4)

    result = invariant_with_extrapolation(curve, (0.1, 0.2), high_q_method="porod_q^-4")

    checks = {check["name"]: check for check in result.results["validity_checks"]}
    assert result.results["porod_plateau_status"] == "missing_prerequisite"
    assert result.results["Q_high_q_extrapolated"] is None
    assert result.results["high_q_extrapolation_status"] == "missing_prerequisite"
    assert checks["porod_plateau_valid"]["passed"] is False


def test_invariant_overflowed_low_q_extrapolation_is_withheld_without_nonfinite_leakage() -> None:
    q = np.array([1.0e200, 1.5e200, 2.0e200])
    curve = CurveData.create(name="overflowed_low_tail", q=q, intensity=np.ones_like(q))

    result = invariant_with_extrapolation(curve, (float(q.min()), float(q.max())), low_q_method="constant")

    assert result.results["Q_low_q_extrapolated"] is None
    assert result.results["low_q_extrapolation_status"] == "invalid_value"
    assert result.results["low_q_extrapolation_invalid_reason"]
    _assert_no_nan_or_infinity(result.results)


@pytest.mark.parametrize("contrast", [np.nan, np.inf, -np.inf])
def test_invariant_nonfinite_contrast_is_withheld_without_output_leakage(contrast: float) -> None:
    result = invariant_with_extrapolation(_curve(), (0.01, 0.2), absolute_intensity=True, contrast=contrast)

    assert result.results["contrast"] is None
    assert result.results["contrast_status"] == "missing_prerequisite"
    assert result.results["contrast_invalid_reason"]
    _assert_no_nan_or_infinity(result.results)
    _assert_no_nan_or_infinity(result.parameters)


@pytest.mark.parametrize("dmax", [np.nan, np.inf, -np.inf, 0.0, -1.0])
def test_pr_rejects_nonfinite_or_nonpositive_dmax_before_inversion(dmax: float) -> None:
    with pytest.raises(ValueError, match="dmax must be a finite positive number"):
        compute_pr(_pr_curve(), (0.01, 0.3), dmax=dmax, regularization=1e-2)


@pytest.mark.parametrize("regularization", [np.nan, np.inf, -np.inf, -1.0])
def test_pr_rejects_nonfinite_or_negative_regularization_before_inversion(regularization: float) -> None:
    with pytest.raises(ValueError, match="regularization must be a finite non-negative number"):
        compute_pr(_pr_curve(), (0.01, 0.3), dmax=100.0, regularization=regularization)


def test_pr_uses_aligned_curve_error_for_backfit_chi_square() -> None:
    curve = _pr_curve()
    curve_with_error = CurveData.create(name="pr_with_error", q=curve.q, intensity=curve.intensity, error=np.full_like(curve.q, 0.5))

    result = compute_pr(curve_with_error, (0.01, 0.3), dmax=100.0, regularization=1e-2)

    expected = float(np.sum((np.asarray(result.results["residuals"]) / 0.5) ** 2))
    assert result.results["backfit_chi_square"] == pytest.approx(expected)
    assert result.results["backfit_chi_square_status"] == "available"
    assert result.results["backfit_chi_square_invalid_reason"] is None
    assert result.parameters["regularization"] == 1e-2
    assert result.results["regularization"] == 1e-2


def test_pr_misaligned_error_is_not_claimed_as_a_chi_square() -> None:
    curve = _pr_curve()
    mismatched_error_curve = CurveData.create(name="pr_bad_error", q=curve.q, intensity=curve.intensity, error=np.ones(3))

    result = compute_pr(mismatched_error_curve, (0.01, 0.3), dmax=100.0, regularization=1e-2)

    assert result.results["backfit_chi_square"] is None
    assert result.results["backfit_chi_square_status"] == "missing_prerequisite"
    assert "align" in result.results["backfit_chi_square_invalid_reason"].lower()


def test_pr_extreme_finite_intensity_never_exports_nonfinite_scalars_or_rows() -> None:
    q = np.linspace(0.01, 0.3, 80)
    curve = CurveData.create(name="extreme_pr", q=q, intensity=np.full_like(q, 1.0e308))

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        result = compute_pr(curve, (0.01, 0.3), dmax=100.0, regularization=1e-2)

    assert not [warning for warning in captured if issubclass(warning.category, RuntimeWarning)]
    _assert_no_nan_or_infinity(result.results)
    _assert_no_nan_or_infinity(result.results["export_tables"]["pr_distribution"])
    _assert_no_nan_or_infinity(result.results["export_tables"]["pr_backfit"])
