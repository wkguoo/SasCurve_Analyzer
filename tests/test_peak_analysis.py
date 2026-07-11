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


def test_peak_fwhm_uses_q_positions_on_nonuniform_grid() -> None:
    q = np.geomspace(0.1, 1.0, 600)
    peak_q = 0.42
    sigma = 0.035
    intensity = 1.0 + 20.0 * np.exp(-((q - peak_q) ** 2) / (2 * sigma**2))
    curve = CurveData.create(name="nonuniform_peak", q=q, intensity=intensity)

    peak = detect_peaks(curve, (0.1, 1.0), prominence=5.0).results["peaks"][0]

    expected_fwhm = 2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma
    assert np.isclose(peak["FWHM"], expected_fwhm, rtol=0.03)


def test_peak_reports_raw_and_baseline_corrected_area() -> None:
    q = np.linspace(0.1, 1.0, 600)
    peak_q = 0.42
    sigma = 0.02
    background = 8.0 + 0.5 * q
    peak_signal = 20.0 * np.exp(-((q - peak_q) ** 2) / (2 * sigma**2))
    curve = CurveData.create(name="baseline_peak", q=q, intensity=background + peak_signal)

    peak = detect_peaks(curve, (0.1, 1.0), prominence=5.0).results["peaks"][0]

    assert peak["raw_area_within_fwhm"] == peak["peak_area"]
    assert peak["baseline_corrected_peak_area"] is not None
    assert peak["baseline_corrected_peak_area"] < peak["raw_area_within_fwhm"]


def test_peak_reports_extended_descriptive_metrics() -> None:
    q = np.linspace(0.1, 1.0, 600)
    peak_q = 0.42
    sigma = 0.02
    background = 8.0 + 0.5 * q
    intensity = (
        background
        + 30.0 * np.exp(-((q - 0.28) ** 2) / (2 * 0.015**2))
        + 20.0 * np.exp(-((q - peak_q) ** 2) / (2 * sigma**2))
        + 30.0 * np.exp(-((q - 0.58) ** 2) / (2 * 0.015**2))
    )
    curve = CurveData.create(name="extended_peak", q=q, intensity=intensity)

    peak = min(
        detect_peaks(curve, (0.1, 1.0), prominence=5.0).results["peaks"],
        key=lambda row: abs(row["peak_q"] - peak_q),
    )

    assert {
        "baseline",
        "net_height",
        "area",
        "FWHM",
        "HWHM",
        "asymmetry",
        "prominence",
        "SNR",
        "correlation_length",
        "edge_truncation",
        "validity",
    } <= peak.keys()
    assert np.isclose(peak["baseline"], 8.0 + 0.5 * peak["peak_q"], rtol=0.01)
    assert np.isclose(peak["net_height"], 20.0, rtol=0.02)
    assert peak["area"] is not None
    assert peak["area"] > peak["baseline_corrected_peak_area"]
    assert np.isclose(peak["HWHM"], peak["FWHM"] / 2.0)
    assert np.isclose(peak["correlation_length"], 2.0 * np.pi / peak["FWHM"])
    assert peak["edge_truncation"] is False
    assert peak["validity"] == "valid"


def test_edge_truncated_peak_does_not_report_width_area_or_size_as_valid() -> None:
    q = np.linspace(0.1, 1.0, 500)
    intensity = 1.0 + 20.0 * np.exp(-((q - 0.15) ** 2) / (2.0 * 0.10**2))
    curve = CurveData.create(name="left_truncated_peak", q=q, intensity=intensity)

    peak = detect_peaks(curve, (0.1, 1.0)).results["peaks"][0]

    assert peak["edge_truncated"] is True
    assert peak["FWHM"] is None
    assert peak["HWHM"] is None
    assert peak["peak_area"] is None
    assert peak["area"] is None
    assert peak["correlation_length"] is None
    assert peak["asymmetry"] is None
    assert {"prominence", "snr", "valid", "validity_reason"} <= peak.keys()
    assert peak["valid"] is False
    assert peak["validity_reason"] is not None


def test_peak_detection_collapses_duplicate_q_before_width_calculation() -> None:
    q = np.linspace(0.1, 1.0, 300)
    intensity = 1.0 + 20.0 * np.exp(-((q - 0.42) ** 2) / (2 * 0.02**2))
    duplicate_curve = CurveData.create(name="duplicate_peak", q=np.repeat(q, 2), intensity=np.repeat(intensity, 2))

    result = detect_peaks(duplicate_curve, (0.1, 1.0), prominence=5.0)

    assert any("Collapsed" in warning for warning in result.warnings)
    assert np.isclose(result.results["peaks"][0]["FWHM"], 2.0 * np.sqrt(2.0 * np.log(2.0)) * 0.02, rtol=0.04)


def test_peak_full_area_is_limited_when_prominence_base_hits_selected_range_edge() -> None:
    q = np.linspace(0.0, 1.0, 1001)
    intensity = 0.05 + 5.0 * np.exp(-((q - 0.2) / 0.06) ** 2) + 2.0 * np.exp(-((q - 0.5) / 0.02) ** 2)
    curve = CurveData.create(name="baseline_edge_limited_peak", q=q, intensity=intensity)

    peaks = detect_peaks(curve, (0.0, 1.0), prominence=0.2).results["peaks"]
    peak = min(peaks, key=lambda row: abs(row["peak_q"] - 0.2))

    assert peak["baseline_edge_limited"] is True
    assert peak["FWHM"] is not None
    assert peak["area"] is None
    assert peak["valid"] is False
    assert "prominence_contour_baseline" in peak["validity_reason"]
    assert peak["baseline_provenance"]["method"] == "scipy_prominence_contour"


def test_peak_duplicate_q_and_extreme_snr_never_export_infinite_scalars() -> None:
    duplicate_q = np.array([0.1, 0.2, 0.2, 0.3])
    duplicate_i = np.array([1.0, 1.6e308, 1.6e308, 1.0])
    duplicate_curve = CurveData.create(name="extreme_duplicate_peak", q=duplicate_q, intensity=duplicate_i)

    duplicate_peak = detect_peaks(duplicate_curve, (0.1, 0.3)).results["peaks"][0]

    assert np.isfinite(duplicate_peak["peak_I"])
    assert all(duplicate_peak[key] is None or np.isfinite(duplicate_peak[key]) for key in ("peak_I", "prominence", "SNR", "FWHM", "area", "peak_area"))

    q = np.linspace(0.1, 1.0, 300)
    intensity = 1.0 + 20.0 * np.exp(-((q - 0.42) ** 2) / (2.0 * 0.02**2))
    curve = CurveData.create(name="overflowed_peak_snr", q=q, intensity=intensity, error=np.full(q.size, 1.0e-320))

    snr_peak = detect_peaks(curve, (0.1, 1.0), prominence=5.0).results["peaks"][0]

    assert snr_peak["SNR"] is None
    assert "overflow" in snr_peak["peak_snr_unavailable_reason"].lower()


def test_peak_overflowed_area_is_withheld_and_marks_the_peak_limited() -> None:
    q = np.linspace(0.5e210, 1.3e210, 501)
    intensity = (
        2.0e100
        + 1.4e100 * np.exp(-((q - 0.8e210) / 0.05e210) ** 2)
        + 1.6e100 * np.exp(-((q - 1.15e210) / 0.02e210) ** 2)
    )
    curve = CurveData.create(name="overflowed_peak_area", q=q, intensity=intensity)

    peaks = detect_peaks(curve, (float(q.min()), float(q.max())), prominence=1.0e99).results["peaks"]
    peak = min(peaks, key=lambda row: abs(row["peak_q"] - 0.8e210))

    assert peak["raw_area_within_fwhm"] is None
    assert peak["baseline_corrected_peak_area"] is None
    assert peak["valid"] is False
    assert any("overflow" in reason for reason in peak["validity_reasons"])


def test_peak_overflowed_d_spacing_is_withheld_with_a_validity_reason() -> None:
    q = np.linspace(1.0e-320, 3.0e-320, 101)
    intensity = 1.0 + 4.0 * np.exp(-((np.arange(q.size) - 50.0) / 8.0) ** 2)
    curve = CurveData.create(name="overflowed_peak_d", q=q, intensity=intensity)

    peak = detect_peaks(curve, (float(q.min()), float(q.max())), prominence=1.0).results["peaks"][0]

    assert peak["d"] is None
    assert peak["valid"] is False
    assert any("d_spacing" in reason for reason in peak["validity_reasons"])

