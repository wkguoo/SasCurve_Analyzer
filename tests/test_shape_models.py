from __future__ import annotations

import numpy as np

from app.core.shape_models import MODEL_SPECS, cylinder_model, evaluate_model, mass_fractal_model, model_names, sphere_model


def test_shape_model_names_cover_requested_models() -> None:
    assert {
        "sphere",
        "core_shell_sphere",
        "ellipsoid",
        "cylinder",
        "disk",
        "gaussian_chain",
        "dab",
        "mass_fractal",
        "surface_fractal",
        "lamellar_peak_stack",
    }.issubset(set(model_names()))
    assert MODEL_SPECS["sphere"].parameter_names == ["radius", "scale", "background"]


def test_model_specs_have_aligned_complete_fit_parameter_metadata() -> None:
    for spec in MODEL_SPECS.values():
        assert len(spec.parameter_names) == len(spec.initial_values)
        assert len(spec.parameter_names) == len(spec.lower_bounds)
        assert len(spec.parameter_names) == len(spec.upper_bounds)
        assert set(spec.units) <= set(spec.parameter_names)


def test_shape_models_return_finite_positive_values() -> None:
    q = np.linspace(0.001, 0.2, 30)
    assert np.all(np.isfinite(sphere_model(q, 30.0, 2.0, 0.1)))
    assert np.all(np.isfinite(cylinder_model(q, 5.0, 80.0, 2.0, 0.1)))
    assert np.all(evaluate_model("gaussian_chain", q, [20.0, 2.0, 0.1]) > 0)


def test_mass_fractal_has_finite_low_q_plateau_and_fractal_slope() -> None:
    dimension = 2.2
    cutoff_length = 100.0
    low_q = np.array([1e-8, 1e-7, 1e-6])
    low_i = mass_fractal_model(low_q, dimension, cutoff_length, scale=1.0, background=0.0)

    assert np.all(np.isfinite(low_i))
    assert low_i.max() / low_i.min() < 1.01

    high_q = np.geomspace(0.2, 2.0, 40)
    high_i = mass_fractal_model(high_q, dimension, cutoff_length, scale=1.0, background=0.0)
    slope, _intercept = np.polyfit(np.log(high_q), np.log(high_i), 1)
    assert np.isclose(slope, -dimension, rtol=0.05)

