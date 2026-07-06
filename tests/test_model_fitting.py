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

