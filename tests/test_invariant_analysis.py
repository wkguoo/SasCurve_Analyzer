from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.invariant_analysis import invariant_with_extrapolation
from app.core.model_free import kratky_metrics


def test_invariant_requires_assumptions_for_volume_fraction() -> None:
    q = np.linspace(0.01, 0.2, 60)
    curve = CurveData.create(name="inv", q=q, intensity=np.exp(-q))
    result = invariant_with_extrapolation(curve, (float(q.min()), float(q.max())))
    assert result.results["Q_measured"] > 0
    assert result.results["volume_fraction_candidate"] is None
    assert "contrast_required" in result.results["assumptions"]


def test_invariant_does_not_emit_volume_fraction_without_absolute_intensity() -> None:
    q = np.linspace(0.01, 0.2, 60)
    curve = CurveData.create(name="inv", q=q, intensity=np.full_like(q, 0.1))

    result = invariant_with_extrapolation(curve, (float(q.min()), float(q.max())), contrast=1.0, absolute_intensity=False)

    assert result.results["contrast_factor_phi_1_minus_phi"] is None
    assert result.results["volume_fraction_candidate"] is None
    assert "absolute_intensity_required" in result.results["assumptions"]


def test_invariant_with_extrapolation_sorts_q_before_integrating() -> None:
    q = np.linspace(0.01, 0.2, 60)
    intensity = np.exp(-q)
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_result = invariant_with_extrapolation(sorted_curve, (float(q.min()), float(q.max())))
    reversed_result = invariant_with_extrapolation(reversed_curve, (float(q.min()), float(q.max())))

    assert reversed_result.results["Q_measured"] > 0
    assert np.isclose(reversed_result.results["Q_measured"], sorted_result.results["Q_measured"])


def test_kratky_metrics_reports_width_area_and_peak_completeness() -> None:
    q = np.linspace(0.05, 1.0, 500)
    peak_q = 0.42
    sigma = 0.06
    q2i = 8.0 * np.exp(-((q - peak_q) ** 2) / (2.0 * sigma**2))
    curve = CurveData.create(name="kratky_peak", q=q, intensity=q2i / q**2)

    result = kratky_metrics(curve, (float(q.min()), float(q.max())))

    assert np.isclose(result.results["q_K"], peak_q, atol=0.003)
    assert {
        "FWHM",
        "HWHM",
        "area",
        "peak_completeness_status",
        "peak_complete",
    } <= result.results.keys()
    assert np.isclose(result.results["FWHM"], 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma, rtol=0.03)
    assert np.isclose(result.results["HWHM"], result.results["FWHM"] / 2.0)
    assert result.results["area"] > 0
    assert result.results["peak_completeness_status"] == "complete"
    assert result.results["peak_complete"] is True


def test_kratky_does_not_attach_internal_peak_width_to_boundary_global_maximum() -> None:
    q = np.linspace(0.05, 1.0, 500)
    q2i = 20.0 * np.exp(-q / 0.22) + 8.0 * np.exp(-((q - 0.55) ** 2) / (2.0 * 0.05**2))
    curve = CurveData.create(name="boundary_global_kratky", q=q, intensity=q2i / q**2)

    result = kratky_metrics(curve, (float(q.min()), float(q.max())))
    values = result.results

    assert np.isclose(values["q_K"], q[0])
    assert values["FWHM"] is None
    assert values["area"] is None
    assert values["width_peak_q"] is None
    assert values["width_peak_matches_q_K"] is False
    assert values["peak_completeness_status"] == "left_truncated"


def test_kratky_collapses_duplicate_q_before_peak_width_calculation() -> None:
    q = np.linspace(0.05, 1.0, 300)
    q2i = 8.0 * np.exp(-((q - 0.42) ** 2) / (2.0 * 0.06**2))
    curve = CurveData.create(name="duplicate_kratky", q=np.repeat(q, 2), intensity=np.repeat(q2i / q**2, 2))

    result = kratky_metrics(curve, (float(q.min()), float(q.max())))

    assert any("Collapsed" in warning for warning in result.warnings)
    assert result.results["peak_completeness_status"] == "complete"


def test_kratky_extreme_duplicate_q_values_never_export_infinite_maximum() -> None:
    q = np.array([1.0, 2.0, 2.0, 3.0])
    q2i = np.array([1.0e307, 1.6e308, 1.6e308, 1.0e307])
    curve = CurveData.create(name="extreme_duplicate_kratky", q=q, intensity=q2i / q**2)

    result = kratky_metrics(curve, (1.0, 3.0))

    assert np.isfinite(result.results["q2I_max"])
    assert any("Collapsed" in warning for warning in result.warnings)
    assert result.results["peak_completeness_status"] != "complete" or result.results["area"] is None or np.isfinite(result.results["area"])


def test_kratky_overflowed_d_and_area_are_unavailable_not_complete() -> None:
    tiny_q = np.array([1.0e-320, 2.0e-320, 3.0e-320])
    tiny_curve = CurveData.create(name="overflowed_kratky_d", q=tiny_q, intensity=np.ones_like(tiny_q))

    tiny_result = kratky_metrics(tiny_curve, (float(tiny_q.min()), float(tiny_q.max())))

    assert tiny_result.results["d_K"] is None
    assert any("d_k" in warning.lower() and "overflow" in warning.lower() for warning in tiny_result.warnings)

    q = np.linspace(0.5e154, 1.3e154, 501)
    q2i = 2.0e307 + 1.4e308 * np.exp(-((q - 0.9e154) / 0.1e154) ** 2)
    curve = CurveData.create(name="overflowed_kratky_area", q=q, intensity=q2i / q**2)

    result = kratky_metrics(curve, (float(q.min()), float(q.max())))

    assert result.results["area"] is None
    assert result.results["raw_area_within_fwhm"] is None
    assert result.results["peak_complete"] is False
    assert result.results["peak_completeness_status"] != "complete"
    assert any("overflow" in warning.lower() for warning in result.warnings)
