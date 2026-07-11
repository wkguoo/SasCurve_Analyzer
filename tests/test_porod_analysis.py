from __future__ import annotations

import numpy as np
import pytest

from app.core.data_model import CurveData
from app.core.model_free import porod_metrics
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


def test_porod_deep_reports_plateau_candidate_range_statistics_and_noise_score() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="flat_porod", q=q, intensity=3.0 * q**-4)

    result = porod_deep_analysis(curve, (float(q.min()), float(q.max())))

    assert {
        "plateau_candidate_q_min",
        "plateau_candidate_q_max",
        "plateau_candidate_points",
        "plateau_candidate_mean",
        "plateau_candidate_std",
        "plateau_candidate_cv",
        "plateau_candidate_valid",
        "plateau_candidate_reason",
        "noise_score",
    } <= result.results.keys()
    assert np.isclose(result.results["plateau_candidate_q_min"], q.min())
    assert np.isclose(result.results["plateau_candidate_q_max"], q.max())
    assert result.results["plateau_candidate_points"] == q.size
    assert np.isclose(result.results["plateau_candidate_mean"], 3.0, rtol=1e-6)
    assert np.isclose(result.results["noise_score"], 0.0, atol=1e-12)


def test_porod_deep_requires_explicit_two_phase_confirmation_for_absolute_surface_candidate() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="flat_porod_without_two_phase", q=q, intensity=3.0 * q**-4)

    result = porod_deep_analysis(
        curve,
        (float(q.min()), float(q.max())),
        contrast=1.0,
        absolute_intensity=True,
    )

    assert result.results["specific_surface_candidate"] is None
    assert result.results["interface_area_density_candidate"] is None
    assert result.results["two_phase_confirmed"] is False
    assert "two_phase_required" in result.results["assumptions"]

    confirmed = porod_deep_analysis(
        curve,
        (float(q.min()), float(q.max())),
        contrast=1.0,
        absolute_intensity=True,
        two_phase_confirmed=True,
    )
    assert confirmed.results["specific_surface_candidate"] is not None
    assert confirmed.results["two_phase_confirmed"] is True


def test_basic_porod_metrics_also_reports_full_finite_range_statistics() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="basic_flat_porod", q=q, intensity=3.0 * q**-4)

    result = porod_metrics(curve, (float(q.min()), float(q.max())))

    assert {"q4I_plateau_q_min", "q4I_plateau_q_max", "q4I_plateau_min", "q4I_plateau_max", "noise_score"} <= result.results.keys()
    assert np.isclose(result.results["q4I_plateau_q_min"], q.min())
    assert np.isclose(result.results["q4I_plateau_q_max"], q.max())
    assert np.isclose(result.results["noise_score"], 0.0, atol=1e-12)


@pytest.mark.parametrize("contrast", [float("nan"), float("inf"), 1.0e-200])
def test_porod_rejects_nonfinite_or_unsafely_squared_contrast_without_candidate(contrast: float) -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="unsafe_contrast", q=q, intensity=3.0 * q**-4)

    result = porod_deep_analysis(
        curve,
        (float(q.min()), float(q.max())),
        contrast=contrast,
        absolute_intensity=True,
        two_phase_confirmed=True,
    )

    assert result.results["specific_surface_candidate"] is None
    assert result.results["interface_area_density_candidate"] is None
    assert result.results["contrast"] is None
    assert any("contrast" in warning.lower() for warning in result.warnings)


def test_porod_requires_literal_boolean_true_for_two_phase_confirmation() -> None:
    q = np.linspace(0.5, 2.0, 80)
    curve = CurveData.create(name="truthy_two_phase", q=q, intensity=3.0 * q**-4)

    result = porod_deep_analysis(
        curve,
        (float(q.min()), float(q.max())),
        contrast=1.0,
        absolute_intensity=True,
        two_phase_confirmed="confirmed",  # type: ignore[arg-type]
    )

    assert result.results["specific_surface_candidate"] is None
    assert result.results["two_phase_confirmed"] is False
    assert any("two-phase" in warning.lower() for warning in result.warnings)


def test_porod_uses_valid_contiguous_plateau_for_absolute_candidate() -> None:
    q = np.linspace(0.5, 2.0, 80)
    q4i = np.resize(np.array([0.85, 1.15]), q.size)
    curve = CurveData.create(name="alternating_q4i", q=q, intensity=q4i / q**4)

    result = porod_deep_analysis(
        curve,
        (float(q.min()), float(q.max())),
        contrast=1.0,
        absolute_intensity=True,
        two_phase_confirmed=True,
    )

    assert result.results["plateau_candidate_valid"] is False
    assert result.results["specific_surface_candidate"] is None
    assert result.results["interface_area_density_candidate"] is None
    assert any("contiguous" in warning.lower() for warning in result.warnings)


def test_porod_statistics_never_export_nonfinite_values_after_finite_sample_reduction() -> None:
    q = np.linspace(1.0, 2.0, 6)
    q4i = np.array([1.6e308, -1.6e308, 1.6e308, -1.6e308, 1.6e308, -1.6e308])
    curve = CurveData.create(name="overflowed_porod_reduction", q=q, intensity=q4i / q**4)

    deep = porod_deep_analysis(curve, (float(q.min()), float(q.max())))
    basic = porod_metrics(curve, (float(q.min()), float(q.max())))

    statistic_keys = (
        "q4I_plateau_mean",
        "q4I_plateau_std",
        "q4I_plateau_cv",
        "q4I_plateau_min",
        "q4I_plateau_max",
        "q4I_plateau_median",
        "q4I_plateau_range",
        "noise_score",
    )
    for result in (deep, basic):
        assert all(result.results[key] is None or np.isfinite(result.results[key]) for key in statistic_keys)
        assert result.results["q4I_plateau_range"] is None
        assert any("overflow" in warning.lower() or "non-finite" in warning.lower() for warning in result.warnings)

