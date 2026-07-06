from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.fractal_analysis import fractal_analysis


def test_fractal_analysis_reports_mass_dimension_candidate() -> None:
    q = np.linspace(0.02, 0.5, 100)
    curve = CurveData.create(name="fractal", q=q, intensity=4.0 * q**-2.4)
    result = fractal_analysis(curve, (float(q.min()), float(q.max())))
    assert np.isclose(result.results["mass_fractal_dimension_candidate"], 2.4, rtol=0.02)
    assert result.results["interpretation"] == "mass_fractal_candidate"

