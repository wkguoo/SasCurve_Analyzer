from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.lamellar_analysis import lamellar_analysis


def test_lamellar_analysis_indexes_peak_orders() -> None:
    q = np.linspace(0.05, 0.5, 400)
    q0 = 0.12
    intensity = 1.0 + 20.0 * np.exp(-0.5 * ((q - q0) / 0.008) ** 2) + 10.0 * np.exp(-0.5 * ((q - 2 * q0) / 0.008) ** 2)
    curve = CurveData.create(name="lamellar", q=q, intensity=intensity)
    result = lamellar_analysis(curve, (float(q.min()), float(q.max())), prominence=5.0)
    assert np.isclose(result.results["long_period_candidate"], 2.0 * np.pi / q0, rtol=0.02)
    assert result.results["indexed_peaks"][1]["nearest_lamellar_order"] == 2

