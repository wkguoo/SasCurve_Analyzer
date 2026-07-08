from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.model_fitting import fit_shape_model
from app.core.shape_models import sphere_model


def test_fit_shape_model_recovers_sphere_radius() -> None:
    q = np.linspace(0.003, 0.08, 90)
    intensity = sphere_model(q, 35.0, 120.0, 2.0)
    curve = CurveData.create(name="sphere", q=q, intensity=intensity)
    result = fit_shape_model(curve, (float(q.min()), float(q.max())), "sphere")
    radius = result.results["parameters"]["radius"]["value"]
    assert result.results["converged"] is True
    assert np.isclose(radius, 35.0, rtol=0.08)
    assert result.results["export_tables"]["fit_curves"]


def test_fit_shape_model_reports_length_units_from_q_unit() -> None:
    q = np.linspace(0.003, 0.08, 90)
    intensity = sphere_model(q, 35.0, 120.0, 2.0)
    curve_a = CurveData.create(name="sphere_a", q=q, intensity=intensity, q_unit="A^-1")
    curve_nm = CurveData.create(name="sphere_nm", q=q * 10.0, intensity=intensity, q_unit="nm^-1")

    result_a = fit_shape_model(curve_a, (float(q.min()), float(q.max())), "sphere")
    result_nm = fit_shape_model(curve_nm, (float((q * 10.0).min()), float((q * 10.0).max())), "sphere")

    assert result_a.results["parameters"]["radius"]["unit"] == "A"
    assert result_nm.results["parameters"]["radius"]["unit"] == "nm"


def test_fit_shape_model_warns_when_error_column_is_not_used() -> None:
    q = np.linspace(0.003, 0.08, 90)
    intensity = sphere_model(q, 35.0, 120.0, 2.0)
    error = np.ones_like(q)
    error[5] = 0.0
    curve = CurveData.create(name="sphere_bad_error", q=q, intensity=intensity, error=error)

    result = fit_shape_model(curve, (float(q.min()), float(q.max())), "sphere")

    assert any("unweighted" in warning.lower() for warning in result.warnings)

