from __future__ import annotations

import numpy as np

from app.core.shape_models import MODEL_SPECS, cylinder_model, evaluate_model, model_names, sphere_model


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


def test_shape_models_return_finite_positive_values() -> None:
    q = np.linspace(0.001, 0.2, 30)
    assert np.all(np.isfinite(sphere_model(q, 30.0, 2.0, 0.1)))
    assert np.all(np.isfinite(cylinder_model(q, 5.0, 80.0, 2.0, 0.1)))
    assert np.all(evaluate_model("gaussian_chain", q, [20.0, 2.0, 0.1]) > 0)

