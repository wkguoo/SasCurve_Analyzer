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


def test_porod_deep_rejects_negative_plateau_for_surface_candidate() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="negative_porod", q=q, intensity=-3.0 * q**-4)

    result = porod_deep_analysis(curve, (float(q.min()), float(q.max())), contrast=1.0, absolute_intensity=True)

    assert result.results["q4I_plateau_mean"] < 0
    assert result.results["q4I_plateau_cv"] >= 0
    assert result.results["specific_surface_candidate"] is None
    assert result.results["interface_area_density_candidate"] is None


def test_porod_deep_requires_porod_like_alpha_for_surface_candidate() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="non_porod", q=q, intensity=3.0 * q**-2)

    result = porod_deep_analysis(curve, (float(q.min()), float(q.max())), contrast=1.0, absolute_intensity=True)

    assert result.results["power_law_alpha"] < 3.0
    assert result.results["specific_surface_candidate"] is None
    assert result.results["interface_area_density_candidate"] is None

