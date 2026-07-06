from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.feature_extraction import detect_peaks


def test_single_peak_detection_and_d_spacing() -> None:
    q = np.linspace(0.1, 1.0, 300)
    peak_q = 0.42
    intensity = 1.0 + 20.0 * np.exp(-((q - peak_q) ** 2) / (2 * 0.02**2))
    curve = CurveData.create(name="peak", q=q, intensity=intensity)
    result = detect_peaks(curve, (0.1, 1.0), prominence=5.0)
    assert result.results["peak_count"] == 1
    peak = result.results["peaks"][0]
    assert np.isclose(peak["peak_q"], peak_q, atol=0.005)
    assert np.isclose(peak["d"], 2.0 * np.pi / peak["peak_q"])
    assert any("not a particle diameter" in warning for warning in result.warnings)


def test_peak_detection_sorts_q_before_width_and_area() -> None:
    q = np.linspace(0.1, 1.0, 300)
    peak_q = 0.42
    intensity = 1.0 + 20.0 * np.exp(-((q - peak_q) ** 2) / (2 * 0.02**2))
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_peak = detect_peaks(sorted_curve, (0.1, 1.0), prominence=5.0).results["peaks"][0]
    reversed_peak = detect_peaks(reversed_curve, (0.1, 1.0), prominence=5.0).results["peaks"][0]

    assert reversed_peak["FWHM"] > 0
    assert reversed_peak["peak_area"] > 0
    assert np.isclose(reversed_peak["FWHM"], sorted_peak["FWHM"])
    assert np.isclose(reversed_peak["peak_area"], sorted_peak["peak_area"])

