from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.porod_analysis import porod_deep_analysis


def test_porod_deep_reports_plateau_and_surface_warning() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="porod", q=q, intensity=3.0 * q**-4)
    result = porod_deep_analysis(curve, (float(q.min()), float(q.max())))
    assert np.isclose(result.results["q4I_plateau_mean"], 3.0, rtol=1e-6)
    assert result.results["specific_surface_candidate"] is None
    assert "contrast_required" in result.results["assumptions"]

