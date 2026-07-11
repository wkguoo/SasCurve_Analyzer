from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pytest

from app.core.data_model import CurveData
from app.core.model_fitting import (
    derived_model_parameters,
    fit_all_allowed_models,
    fit_shape_model_complete,
)
from app.core.shape_models import MODEL_SPECS, evaluate_model


PARAMETER_RECORD_FIELDS = {
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


def _synthetic_case(model_name: str) -> tuple[np.ndarray, dict[str, float]]:
    """Return a stable, noiseless synthetic curve case for one registered model."""

    cases: dict[str, tuple[np.ndarray, dict[str, float]]] = {
        "sphere": (
            np.linspace(0.003, 0.22, 72),
            {"radius": 22.0, "scale": 17.0, "background": 0.2},
        ),
        "core_shell_sphere": (
            np.linspace(0.004, 0.22, 72),
            {
                "core_radius": 18.0,
                "shell_thickness": 5.0,
                "core_contrast": 1.2,
                "shell_contrast": 0.45,
                "scale": 30.0,
                "background": 0.05,
            },
        ),
        "ellipsoid": (
            np.linspace(0.003, 0.20, 72),
            {"equatorial_radius": 18.0, "polar_radius": 42.0, "scale": 12.0, "background": 0.2},
        ),
        "cylinder": (
            np.linspace(0.004, 0.20, 72),
            {"radius": 6.0, "length": 90.0, "scale": 7.0, "background": 0.2},
        ),
        "disk": (
            np.linspace(0.003, 0.22, 72),
            {"radius": 30.0, "thickness": 4.0, "scale": 10.0, "background": 0.2},
        ),
        "gaussian_chain": (
            np.linspace(0.003, 0.20, 72),
            {"Rg": 22.0, "scale": 8.0, "background": 0.1},
        ),
        "dab": (
            np.linspace(0.003, 0.20, 72),
            {"correlation_length": 20.0, "scale": 10.0, "background": 0.1},
        ),
        "mass_fractal": (
            np.linspace(0.01, 0.30, 72),
            {"dimension": 2.2, "cutoff_length": 20.0, "scale": 0.002, "background": 0.1},
        ),
        "surface_fractal": (
            np.linspace(0.03, 0.30, 72),
            {"surface_dimension": 2.5, "scale": 0.001, "background": 0.1},
        ),
        "lamellar_peak_stack": (
            np.linspace(0.01, 0.40, 72),
            {"q0": 0.07, "width": 0.006, "amplitude": 10.0, "decay": 2.0, "background": 0.1},
        ),
    }
    return cases[model_name]


def _assert_finite_or_none(value: object) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float, np.number)):
        assert math.isfinite(float(value))
        return
    if isinstance(value, Mapping):
        for child in value.values():
            _assert_finite_or_none(child)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _assert_finite_or_none(child)


@pytest.mark.parametrize("model_name", list(MODEL_SPECS))
def test_complete_fit_recovers_noiseless_forward_curve_and_traceable_contract(model_name: str) -> None:
    q, parameters = _synthetic_case(model_name)
    spec = MODEL_SPECS[model_name]
    values = [parameters[name] for name in spec.parameter_names]
    intensity = evaluate_model(model_name, q, values)
    curve = CurveData.create(name=f"synthetic_{model_name}", q=q, intensity=intensity)

    result = fit_shape_model_complete(
        curve,
        (float(q.min()), float(q.max())),
        model_name,
    )
    outcome = result.results

    assert outcome["converged"] is True
    assert {
        "fit_quality",
        "covariance",
        "parameter_correlation",
        "covariance_condition_number",
        "max_abs_parameter_correlation",
        "identifiability_status",
        "residual_rows",
        "derived_parameters",
        "attempts",
    } <= outcome.keys()
    assert {row["name"] for row in outcome["parameter_records"]} == set(spec.parameter_names)
    assert all(PARAMETER_RECORD_FIELDS <= set(row) for row in outcome["parameter_records"])
    assert len(outcome["residual_rows"]) == q.size
    assert outcome["attempts"]
    assert all({"source", "status", "error", "initial_vector"} <= set(row) for row in outcome["attempts"])
    assert outcome["fit_quality"]["rmse"] <= 1e-4 * max(1.0, float(np.max(np.abs(intensity))))
    assert outcome["fit_quality"]["AICc"] is None or math.isfinite(outcome["fit_quality"]["AICc"])
    _assert_finite_or_none(outcome["parameter_records"])
    _assert_finite_or_none(outcome["covariance"])
    _assert_finite_or_none(outcome["parameter_correlation"])
    _assert_finite_or_none(outcome["residual_rows"])
    _assert_finite_or_none(outcome["derived_parameters"])
    _assert_finite_or_none(outcome["attempts"])


@pytest.mark.parametrize(
    ("model_name", "parameters", "expected"),
    [
        ("sphere", {"radius": 3.0}, {"diameter": 6.0, "geometric_Rg": math.sqrt(3.0 / 5.0) * 3.0, "volume": 36.0 * math.pi}),
        ("core_shell_sphere", {"core_radius": 3.0, "shell_thickness": 1.0}, {"total_radius": 4.0, "core_diameter": 6.0, "total_diameter": 8.0}),
        ("ellipsoid", {"equatorial_radius": 2.0, "polar_radius": 6.0}, {"axis_ratio": 3.0, "volume": 32.0 * math.pi}),
        ("cylinder", {"radius": 2.0, "length": 10.0}, {"diameter": 4.0, "aspect_ratio": 2.5, "volume": 40.0 * math.pi}),
        ("disk", {"radius": 2.0, "thickness": 1.0}, {"diameter": 4.0, "aspect_ratio": 0.25, "volume": 4.0 * math.pi}),
        ("surface_fractal", {"surface_dimension": 2.4}, {"Porod_exponent": 3.6}),
        ("lamellar_peak_stack", {"q0": 0.2, "width": 0.01}, {"d0": 10.0 * math.pi, "Gaussian_FWHM": 2.0 * math.sqrt(2.0 * math.log(2.0)) * 0.01}),
    ],
)
def test_derived_model_parameters_follow_documented_mappings(
    model_name: str,
    parameters: dict[str, float],
    expected: dict[str, float],
) -> None:
    derived = derived_model_parameters(model_name, parameters, "A^-1")

    assert set(derived) == set(expected)
    for name, expected_value in expected.items():
        assert derived[name]["value"] == pytest.approx(expected_value)
        assert derived[name]["reason"] is None


def test_derived_model_parameters_report_invalid_division_with_reason() -> None:
    derived = derived_model_parameters("cylinder", {"radius": 0.0, "length": 10.0}, "A^-1")

    assert derived["aspect_ratio"]["value"] is None
    assert derived["aspect_ratio"]["reason"]


def test_derived_model_parameters_convert_overflow_to_null_with_reason() -> None:
    derived = derived_model_parameters("sphere", {"radius": 1e200}, "A^-1")

    assert derived["diameter"]["value"] == pytest.approx(2e200)
    assert derived["volume"]["value"] is None
    assert derived["volume"]["reason"]


def test_degenerate_core_shell_fit_is_not_reported_as_strongly_identifiable() -> None:
    q = np.linspace(0.0002, 0.0003, 72)
    parameters = {
        "core_radius": 20.0,
        "shell_thickness": 4.0,
        "core_contrast": 1.0,
        "shell_contrast": 0.5,
        "scale": 100.0,
        "background": 0.2,
    }
    intensity = evaluate_model("core_shell_sphere", q, [parameters[name] for name in MODEL_SPECS["core_shell_sphere"].parameter_names])
    curve = CurveData.create(name="degenerate_core_shell", q=q, intensity=intensity, error=np.full(q.size, 0.01))

    result = fit_shape_model_complete(
        curve,
        (float(q.min()), float(q.max())),
        "core_shell_sphere",
        initial_parameters=parameters,
    )
    values = result.results

    assert values["max_abs_parameter_correlation"] is not None
    assert values["max_abs_parameter_correlation"] >= 0.95
    assert values["identifiability_status"] in {"weak", "non_identifiable"}


def test_complete_fit_uses_documented_attempt_priority_and_minimum_aicc_selection() -> None:
    q, parameters = _synthetic_case("sphere")
    intensity = evaluate_model("sphere", q, [parameters[name] for name in MODEL_SPECS["sphere"].parameter_names])
    curve = CurveData.create(name="attempt_priority", q=q, intensity=intensity)

    result = fit_shape_model_complete(
        curve,
        (float(q.min()), float(q.max())),
        "sphere",
        initial_parameters=parameters,
        batch_median_parameters={"radius": 25.0, "scale": 15.0, "background": 0.2},
    )
    attempts = result.results["attempts"]

    assert [attempt["source"] for attempt in attempts] == [
        "warm_start",
        "batch_median",
        "defaults",
        "jittered_multistart_1",
        "jittered_multistart_2",
    ]
    selected = attempts[result.results["selected_attempt_index"]]
    successful_aicc = [attempt["fit_quality"]["AICc"] for attempt in attempts if attempt["status"] == "success" and attempt["fit_quality"]["AICc"] is not None]
    assert selected["status"] == "success"
    if successful_aicc:
        assert selected["fit_quality"]["AICc"] <= min(successful_aicc) + 1e-9
    assert result.results["error_audit"]["attempt_selection_policy"] == "all_candidates_minimum_AICc_then_RMSE"


def test_complete_fit_does_not_mutate_raw_curve_arrays() -> None:
    q, parameters = _synthetic_case("sphere")
    intensity = evaluate_model("sphere", q, [parameters[name] for name in MODEL_SPECS["sphere"].parameter_names])
    error = np.full(q.size, 0.1)
    curve = CurveData.create(name="non_destructive_complete_fit", q=q, intensity=intensity, error=error)
    q_before = curve.q.copy()
    intensity_before = curve.intensity.copy()
    error_before = curve.error.copy()

    fit_shape_model_complete(curve, (float(q.min()), float(q.max())), "sphere")

    np.testing.assert_array_equal(curve.q, q_before)
    np.testing.assert_array_equal(curve.intensity, intensity_before)
    np.testing.assert_array_equal(curve.error, error_before)


def test_batch_fit_records_all_candidates_and_selects_later_lower_aicc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Batch fitting must retain the complete retry/AICc contract, not first-success selection."""

    import app.core.model_fitting as model_fitting

    q, parameters = _synthetic_case("sphere")
    intensity = evaluate_model("sphere", q, [parameters[name] for name in MODEL_SPECS["sphere"].parameter_names])
    curve = CurveData.create(name="batch_complete_attempt_selection", q=q, intensity=intensity)
    expected_aicc = [99.0, 95.0, 95.0, 95.0, 95.0]
    observed_aicc: list[float] = []
    real_fit_diagnostics = model_fitting.fit_diagnostics

    def controlled_curve_fit(_function, _q, _observed, *, p0, **_kwargs):
        return np.asarray(p0, dtype=float), np.eye(len(p0), dtype=float)

    def controlled_fit_diagnostics(observed, fitted, **kwargs):
        payload = real_fit_diagnostics(observed, fitted, **kwargs)
        if np.asarray(observed).size:
            payload["AICc"] = expected_aicc[len(observed_aicc)]
            observed_aicc.append(payload["AICc"])
        return payload

    monkeypatch.setattr(model_fitting, "curve_fit", controlled_curve_fit)
    monkeypatch.setattr(model_fitting, "fit_diagnostics", controlled_fit_diagnostics)
    results = fit_all_allowed_models(
        curve,
        (float(q.min()), float(q.max())),
        allowed_models=["sphere"],
        warm_starts={"sphere": parameters},
        batch_median_parameters={"sphere": {"radius": 25.0, "scale": 15.0, "background": 0.2}},
    )
    outcome = results["sphere"].results

    assert observed_aicc == expected_aicc
    assert [attempt["source"] for attempt in outcome["attempts"]] == [
        "warm_start",
        "batch_median",
        "defaults",
        "jittered_multistart_1",
        "jittered_multistart_2",
    ]
    assert [attempt["fit_quality"]["AICc"] for attempt in outcome["attempts"]] == expected_aicc
    assert outcome["selected_attempt_index"] == 1
    assert outcome["attempts"][outcome["selected_attempt_index"]]["fit_quality"]["AICc"] == 95.0
    assert outcome["error_audit"]["attempt_selection_policy"] == "all_candidates_minimum_AICc_then_RMSE"


def test_batch_fit_uses_rmse_only_when_all_candidate_aicc_are_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.model_fitting as model_fitting

    q, parameters = _synthetic_case("sphere")
    intensity = evaluate_model("sphere", q, [parameters[name] for name in MODEL_SPECS["sphere"].parameter_names])
    curve = CurveData.create(name="batch_rmse_fallback", q=q, intensity=intensity)
    expected_rmse = [5.0, 3.0, 4.0, 1.0, 2.0]
    observed_rmse: list[float] = []
    real_fit_diagnostics = model_fitting.fit_diagnostics

    def controlled_curve_fit(_function, _q, _observed, *, p0, **_kwargs):
        return np.asarray(p0, dtype=float), np.eye(len(p0), dtype=float)

    def controlled_fit_diagnostics(observed, fitted, **kwargs):
        payload = real_fit_diagnostics(observed, fitted, **kwargs)
        if np.asarray(observed).size:
            payload["AICc"] = None
            payload["rmse"] = expected_rmse[len(observed_rmse)]
            observed_rmse.append(payload["rmse"])
        return payload

    monkeypatch.setattr(model_fitting, "curve_fit", controlled_curve_fit)
    monkeypatch.setattr(model_fitting, "fit_diagnostics", controlled_fit_diagnostics)
    outcome = fit_all_allowed_models(
        curve,
        (float(q.min()), float(q.max())),
        allowed_models=["sphere"],
        warm_starts={"sphere": parameters},
        batch_median_parameters={"sphere": {"radius": 25.0, "scale": 15.0, "background": 0.2}},
    )["sphere"].results

    assert observed_rmse == expected_rmse
    assert all(attempt["fit_quality"]["AICc"] is None for attempt in outcome["attempts"])
    assert outcome["selected_attempt_index"] == 3
    assert outcome["attempts"][3]["fit_quality"]["rmse"] == 1.0


def test_fit_all_allowed_models_isolates_one_model_failure_without_early_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.model_fitting as model_fitting

    q = np.linspace(0.01, 0.20, 36)
    curve = CurveData.create(name="batch_failure_isolation", q=q, intensity=np.exp(-q))

    def broken_sphere(*_args: object, **_kwargs: object) -> np.ndarray:
        raise RuntimeError("synthetic sphere failure")

    def controlled_curve_fit(_function, _q, _observed, *, p0, **_kwargs):
        return np.asarray(p0, dtype=float), np.eye(len(p0), dtype=float)

    monkeypatch.setitem(model_fitting.MODEL_FUNCTIONS, "sphere", broken_sphere)
    monkeypatch.setattr(model_fitting, "curve_fit", controlled_curve_fit)
    results = fit_all_allowed_models(curve, (float(q.min()), float(q.max())))

    assert set(results) == set(MODEL_SPECS)
    assert results["sphere"].results["converged"] is False
    assert "synthetic sphere failure" in (results["sphere"].results["error_message"] or "")
    assert results["gaussian_chain"].analysis_type == "shape_fit:gaussian_chain"
    assert results["lamellar_peak_stack"].analysis_type == "shape_fit:lamellar_peak_stack"
    assert results["gaussian_chain"].results["error_audit"]["attempt_selection_policy"] == "all_candidates_minimum_AICc_then_RMSE"
