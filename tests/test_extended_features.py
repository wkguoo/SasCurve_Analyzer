from __future__ import annotations

import numpy as np
import pytest

from app.core.extended_features import (
    analyze_oscillations,
    detect_crossovers,
    detect_shoulders,
    extended_integrals,
    normalized_shape_distance,
)


def test_crossover_detects_known_slope_transition() -> None:
    q = np.geomspace(0.01, 1.0, 300)
    intensity = np.where(q < 0.1, q**-2.0, 0.01 * q**-4.0)

    rows = detect_crossovers(q, intensity, min_segment_points=20)

    assert rows
    assert abs(np.log10(rows[0]["crossover_q"] / 0.1)) < 0.15


def test_extended_integrals_report_all_required_weights() -> None:
    q = np.linspace(0.01, 0.1, 100)
    intensity = np.ones_like(q)

    result = extended_integrals(q, intensity, bands=(0.04, 0.07))

    assert {
        "integral_I",
        "integral_qI",
        "integral_q2I",
        "integral_q4I",
        "Q_low",
        "Q_mid",
        "Q_high",
        "q10",
        "q50",
        "q90",
    } <= result.keys()


def test_shoulder_detection_reports_a_smooth_log_slope_change() -> None:
    q = np.geomspace(0.01, 1.0, 400)
    intensity = q**-2.0 * (1.0 + (q / 0.1) ** 4.0) ** -0.5

    rows = detect_shoulders(q, intensity, min_segment_points=20)

    assert rows
    assert abs(np.log10(rows[0]["shoulder_q"] / 0.1)) < 0.15
    assert {"shoulder_d", "local_alpha", "curvature", "confidence"} <= rows[0].keys()


def test_oscillation_analysis_reports_signal_extrema() -> None:
    q = np.linspace(0.05, 1.0, 400)
    intensity = 2.0 + 0.4 * np.sin(2.0 * np.pi * q / 0.15)

    result = analyze_oscillations(q, intensity, min_points=20)

    assert result["oscillation_count"] >= 3
    assert result["peaks"]
    assert result["troughs"]
    assert result["warnings"] == []


def test_normalized_shape_distance_ignores_multiplicative_intensity_scale() -> None:
    q = np.geomspace(0.01, 1.0, 200)
    reference = 3.0 * q**-2.5
    scaled = 70.0 * q**-2.5

    result = normalized_shape_distance(q, scaled, q, reference)

    assert result["normalized_shape_distance"] < 1e-12
    assert result["valid"] is True


def test_log_domain_detectors_collapse_duplicate_q_rows_with_an_audit_warning() -> None:
    base_q = np.geomspace(0.01, 1.0, 200)
    base_intensity = np.where(base_q < 0.1, base_q**-2.0, 0.01 * base_q**-4.0)
    q = np.repeat(base_q, 2)
    intensity = np.repeat(base_intensity, 2)

    rows = detect_crossovers(q, intensity, min_segment_points=20)

    assert rows
    assert any("Collapsed" in warning for warning in rows.warnings)


def test_extended_integral_bands_partition_the_finite_range_invariant() -> None:
    q = np.linspace(0.01, 0.1, 100)
    result = extended_integrals(q, np.ones_like(q), bands=(0.04, 0.07))

    assert np.isclose(result["Q_low"] + result["Q_mid"] + result["Q_high"], result["integral_q2I"])


def test_shape_distance_explicitly_reports_no_common_q_range() -> None:
    result = normalized_shape_distance(
        np.linspace(0.01, 0.1, 30),
        np.ones(30),
        np.linspace(0.2, 0.4, 30),
        np.ones(30),
    )

    assert result["normalized_shape_distance"] is None
    assert result["valid"] is False
    assert result["warnings"]


def test_shape_distance_reports_unavailable_when_both_shapes_have_zero_scale() -> None:
    q = np.linspace(0.01, 0.1, 30)

    result = normalized_shape_distance(q, np.ones_like(q), q, 4.0 * np.ones_like(q))

    assert result["normalized_shape_distance"] is None
    assert result["valid"] is False
    assert any("normalization" in warning.lower() for warning in result["warnings"])


def test_extended_integrals_collapses_duplicate_q_deterministically() -> None:
    q = np.array([0.01, 0.02, 0.02, 0.03, 0.04])
    intensity = np.array([1.0, 2.0, 4.0, 3.0, 4.0])

    result = extended_integrals(q, intensity, bands=(0.02, 0.03))
    expected = extended_integrals(np.array([0.01, 0.02, 0.03, 0.04]), np.array([1.0, 3.0, 3.0, 4.0]), bands=(0.02, 0.03))

    assert np.isclose(result["integral_q2I"], expected["integral_q2I"])
    assert any("Collapsed" in warning for warning in result["warnings"])


def test_extended_integrals_turns_overflowed_weighted_integral_into_none_with_warning() -> None:
    q = np.array([1.0e50, 2.0e50, 3.0e50])
    intensity = np.full(3, 1.0e300)

    result = extended_integrals(q, intensity)

    assert result["integral_q4I"] is None
    assert any("overflow" in warning.lower() or "non-finite" in warning.lower() for warning in result["warnings"])


def test_extended_integral_band_overflow_returns_none_and_warning() -> None:
    """Finite samples must not leak infinite sub-band invariants."""

    q = np.array([1.0e50, 2.0e50, 3.0e50])
    intensity = np.full(3, 1.0e200)

    result = extended_integrals(q, intensity)

    assert result["integral_q2I"] is None
    assert all(result[key] is None for key in ("Q_low", "Q_mid", "Q_high"))
    assert any("q_low" in warning.lower() or "overflow" in warning.lower() for warning in result["warnings"])


def test_extended_integrals_safely_average_extreme_duplicate_q_values() -> None:
    """A finite duplicate-q mean must remain usable even if a raw sum would overflow."""

    q = np.array([0.1, 0.2, 0.2, 0.3])
    intensity = np.array([1.0, 1.6e308, 1.6e308, 1.0])

    result = extended_integrals(q, intensity)

    assert np.isfinite(result["integral_q2I"])
    assert all(result[key] is None or np.isfinite(result[key]) for key in ("integral_I", "integral_qI", "integral_q2I", "integral_q4I", "Q_low", "Q_mid", "Q_high"))
    assert any("Collapsed" in warning for warning in result["warnings"])


def test_shoulder_and_oscillation_rows_expose_candidate_completeness_and_provenance() -> None:
    shoulder_q = np.geomspace(0.01, 1.0, 400)
    shoulder_i = shoulder_q**-2.0 * (1.0 + (shoulder_q / 0.1) ** 4.0) ** -0.5
    shoulders = detect_shoulders(shoulder_q, shoulder_i, min_segment_points=20)
    oscillation_q = np.linspace(0.05, 1.0, 400)
    oscillation_i = 2.0 + 0.4 * np.sin(2.0 * np.pi * oscillation_q / 0.15)
    oscillations = analyze_oscillations(oscillation_q, oscillation_i, min_points=20)

    expected = {"candidate_type", "edge_truncated", "completeness_status", "provenance", "valid", "validity_reason"}
    assert expected <= shoulders[0].keys()
    assert expected <= oscillations["oscillations"][0].keys()
    assert {"min_peak_distance_points", "spacing_strategy"} <= oscillations.keys()


def test_oscillation_analysis_rejects_nan_prominence() -> None:
    q = np.linspace(0.05, 1.0, 100)
    intensity = 2.0 + 0.4 * np.sin(2.0 * np.pi * q / 0.15)

    with pytest.raises(ValueError, match="finite"):
        analyze_oscillations(q, intensity, min_points=20, prominence=float("nan"))


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), float("-inf")])
def test_crossover_and_shoulder_reject_nonfinite_numeric_thresholds(threshold: float) -> None:
    q = np.geomspace(0.01, 1.0, 120)
    intensity = q**-2.0

    with pytest.raises(ValueError, match="finite"):
        detect_crossovers(q, intensity, min_segment_points=12, min_slope_difference=threshold)
    with pytest.raises(ValueError, match="finite"):
        detect_shoulders(q, intensity, min_segment_points=12, min_curvature=threshold)


def test_extended_feature_point_counts_require_finite_integers() -> None:
    q = np.linspace(0.05, 1.0, 100)
    intensity = 2.0 + 0.4 * np.sin(2.0 * np.pi * q / 0.15)

    with pytest.raises(ValueError, match="integer"):
        detect_crossovers(q, intensity, min_segment_points=12.5)
    with pytest.raises(ValueError, match="finite"):
        detect_shoulders(q, intensity, min_segment_points=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        analyze_oscillations(q, intensity, min_points=float("inf"))
    with pytest.raises(ValueError, match="integer"):
        normalized_shape_distance(q, intensity, q, intensity, grid_points=20.5)


def test_shoulder_provenance_records_actual_threshold_spacing_and_score() -> None:
    q = np.geomspace(0.01, 1.0, 400)
    intensity = q**-2.0 * (1.0 + (q / 0.1) ** 4.0) ** -0.5

    rows = detect_shoulders(q, intensity, min_segment_points=20, min_curvature=0.15)

    provenance = rows[0]["provenance"]
    assert {"find_peaks_prominence_threshold", "min_peak_distance_points", "candidate_score", "max_candidate_score"} <= provenance.keys()
    assert np.isfinite(provenance["find_peaks_prominence_threshold"])
    assert provenance["min_peak_distance_points"] == 10
    assert np.isfinite(provenance["candidate_score"])
    assert np.isfinite(provenance["max_candidate_score"])


def test_oscillation_candidates_with_prominence_support_at_range_edge_are_limited() -> None:
    q = np.linspace(0.05, 1.0, 400)
    intensity = 2.0 + 0.4 * np.sin(2.0 * np.pi * q / 0.15)

    result = analyze_oscillations(q, intensity, min_points=20)
    edge_rows = [row for row in result["oscillations"] if row["edge_truncated"]]

    assert edge_rows
    assert all(row["valid"] is False for row in edge_rows)
    assert all(row["completeness_status"] == "edge_truncated" for row in edge_rows)
    assert all("prominence_contour" in row["validity_reason"] for row in edge_rows)
    assert all("left_base_index" in row["provenance"] and "right_base_index" in row["provenance"] for row in edge_rows)


def test_crossover_overflowed_d_is_none_with_an_audit_warning() -> None:
    q = np.linspace(1.0e-320, 3.0e-320, 121)
    log_q = np.log(q)
    split = 60
    log_intensity = np.where(
        np.arange(q.size) < split,
        0.5 * (log_q - log_q[0]),
        0.5 * (log_q[split] - log_q[0]) + 1.5 * (log_q - log_q[split]),
    )

    rows = detect_crossovers(q, np.exp(log_intensity), min_segment_points=12, min_slope_difference=0.2)

    assert rows
    assert rows[0]["crossover_d"] is None
    assert any("crossover_d" in warning.lower() and "overflow" in warning.lower() for warning in rows.warnings)
