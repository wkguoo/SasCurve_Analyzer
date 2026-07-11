from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from app.core.analysis_schema import EXPORT_TABLE_AUTO_REGION_CANDIDATES, RESULT_GROUP_AUTO_REGION
from app.core.auto_regions import (
    AutoRegionOptions,
    AutoRegionCandidate,
    characteristic_d_from_q,
    confidence_label,
    detect_auto_regions,
    log_q_position_fraction,
    run_analysis_for_region,
)
from app.core.data_model import CurveData
from app.core.export import export_auto_region_candidates_csv


def _candidate_by_type(result, region_type: str) -> list[dict]:
    return [row for row in result.results["candidates"] if row["region_type"] == region_type]


def test_auto_region_schema_constants_and_helpers() -> None:
    assert RESULT_GROUP_AUTO_REGION == "auto_region"
    assert EXPORT_TABLE_AUTO_REGION_CANDIDATES == "auto_region_candidates"
    assert math.isclose(characteristic_d_from_q(0.2), 2.0 * math.pi / 0.2)
    assert characteristic_d_from_q(0.0) is None
    assert confidence_label(0.86) == "recommended"
    assert confidence_label(0.72) == "usable"
    assert confidence_label(0.55) == "caution"
    assert confidence_label(0.49) == "not_recommended"
    assert math.isclose(log_q_position_fraction(0.1, 0.01, 1.0), 0.5)


def test_detect_auto_regions_finds_guinier_candidate() -> None:
    rg = 12.0
    q = np.linspace(0.004, 0.06, 80)
    intensity = 150.0 * np.exp(-(q**2) * rg**2 / 3.0)
    curve = CurveData.create(name="guinier", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    candidates = _candidate_by_type(result, "guinier_candidate")

    assert result.analysis_type == "auto_region_detection"
    assert result.results["result_group"] == "auto_region"
    assert result.results["export_tables"][EXPORT_TABLE_AUTO_REGION_CANDIDATES]
    assert candidates
    best = candidates[0]
    assert best["q_start"] < best["q_end"]
    assert best["d_start"] > best["d_end"]
    assert best["fit_ready"] is True
    assert best["recommended_analysis"] == "guinier_analysis"
    assert best["metrics"]["Rg"] == pytest.approx(rg, rel=0.25)
    assert best["metrics"]["qRg_max"] <= 1.3


def test_detect_auto_regions_finds_power_law_candidate() -> None:
    alpha = 2.4
    q = np.geomspace(0.01, 0.4, 120)
    intensity = 4.0 * q ** (-alpha)
    curve = CurveData.create(name="power-law", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    candidates = _candidate_by_type(result, "power_law_candidate")

    assert candidates
    best = candidates[0]
    assert best["recommended_analysis"] == "power_law_analysis"
    assert best["detection_method"] == "sliding_window_power_law"
    assert best["metrics"]["alpha"] == pytest.approx(alpha, rel=0.12)


def test_power_law_scan_covers_narrow_log_region_on_wide_linear_q_grid() -> None:
    """A linear q grid must not make the scanner jump over a short SAS tail."""

    q = np.linspace(1.0e-4, 1.0, 5500)
    intensity = np.full_like(q, 0.008)
    tail = (q >= 0.0095) & (q <= 0.035)
    intensity[tail] = 0.6 * (q[tail] / 0.01) ** -3.4
    curve = CurveData.create(name="wide-linear-q-with-narrow-tail", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    candidates = _candidate_by_type(result, "power_law_candidate")
    ready = [candidate for candidate in candidates if candidate["fit_ready"]]

    assert ready
    best = ready[0]
    assert best["q_start"] < 0.02 < best["q_end"]
    assert best["n_points"] > AutoRegionOptions().min_points_power_law
    assert best["metrics"]["window_sampling"] == "log_q_multiscale"
    assert best["metrics"]["log_q_span_decades"] >= 0.10
    assert best["metrics"]["local_alpha_method"] == "chunked_log_linear"
    assert best["metrics"]["alpha"] == pytest.approx(3.4, rel=0.03)


def test_detect_auto_regions_finds_peak_candidate_with_boundaries() -> None:
    q = np.linspace(0.02, 0.3, 180)
    q_star = 0.12
    intensity = 3.0 + 40.0 * np.exp(-0.5 * ((q - q_star) / 0.012) ** 2)
    curve = CurveData.create(name="peak", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    peaks = _candidate_by_type(result, "peak_candidate")

    assert peaks
    peak = peaks[0]
    assert peak["q_start"] < peak["metrics"]["q_star"] < peak["q_end"]
    expected_points = int(np.sum((q >= peak["q_start"]) & (q <= peak["q_end"])))
    assert peak["n_points"] == expected_points
    assert peak["metrics"]["d_star"] == pytest.approx(2.0 * math.pi / peak["metrics"]["q_star"])
    assert peak["metrics"]["q_boundary_source"] in {"fwhm", "neighbor_points", "fallback_window"}
    assert peak["metrics"]["peak_prominence"] is not None
    assert "peak_snr" in peak["metrics"]
    assert "peak_local_contrast" in peak["metrics"]
    assert peak["recommended_analysis"] == "peak"


def test_detect_auto_regions_finds_porod_candidate() -> None:
    q = np.geomspace(0.04, 0.5, 130)
    intensity = 2.5e-5 * q ** -4
    curve = CurveData.create(name="porod", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    candidates = _candidate_by_type(result, "porod_candidate")

    assert candidates
    best = candidates[0]
    assert best["recommended_analysis"] == "porod_deep_analysis"
    assert best["confidence_label"] in {"recommended", "usable"}
    assert best["metrics"]["alpha"] == pytest.approx(4.0, abs=0.25)
    assert best["metrics"]["q4I_plateau_cv"] <= 0.2


def test_porod_candidate_requires_high_q_position_for_high_confidence() -> None:
    q = np.geomspace(0.001, 1.0, 240)
    intensity = 1.0e-5 * q**-4
    curve = CurveData.create(name="wide-q-power4", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    porod_candidates = _candidate_by_type(result, "porod_candidate")

    assert porod_candidates
    for candidate in porod_candidates:
        q_position = candidate["metrics"]["q_position_fraction"]
        if q_position < 0.65:
            assert candidate["score"] < 0.70
            assert candidate["confidence_label"] != "recommended"
            assert any("not in the high-q" in warning for warning in candidate["warnings"])


def test_porod_candidate_records_window_limit() -> None:
    q = np.geomspace(0.01, 1.0, 300)
    intensity = 2.0e-5 * q**-4
    curve = CurveData.create(name="limited-porod", q=q, intensity=intensity)

    result = detect_auto_regions(curve, options=AutoRegionOptions(max_scanned_windows=5))
    candidates = _candidate_by_type(result, "porod_candidate")

    assert candidates
    assert all(candidate["metrics"]["scanned_windows"] <= 5 for candidate in candidates)
    assert any(candidate["metrics"]["max_scanned_windows_reached"] for candidate in candidates)
    assert any("max_scanned_windows" in " ".join(candidate["warnings"]) for candidate in candidates)


def test_high_q_noise_is_not_high_confidence_porod() -> None:
    rng = np.random.default_rng(42)
    q = np.geomspace(0.03, 0.6, 160)
    intensity = 1.0 + rng.normal(0.0, 0.18, size=q.size)
    intensity = np.clip(intensity, 0.02, None)
    curve = CurveData.create(name="noisy-tail", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    high_noise = _candidate_by_type(result, "high_q_noise")
    porod_candidates = _candidate_by_type(result, "porod_candidate")

    assert high_noise
    assert high_noise[0]["fit_ready"] is False
    assert high_noise[0]["recommended_analysis"] is None
    assert all(row["confidence_label"] != "recommended" for row in porod_candidates)
    assert all(row["metrics"]["high_q_noise_score"] >= 0.0 for row in porod_candidates)
    assert all(
        row["score"] < 0.50
        for row in porod_candidates
        if row["metrics"].get("q4I_plateau_cv") is not None and row["metrics"]["q4I_plateau_cv"] > 0.50
    )


def test_low_q_upturn_uses_combined_criterion_and_is_not_fit_ready() -> None:
    q = np.geomspace(0.005, 0.4, 120)
    intensity = q ** -1.0
    intensity[:16] *= (q[:16] / q[15]) ** -2.0
    curve = CurveData.create(name="upturn", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    upturns = _candidate_by_type(result, "low_q_upturn")

    assert upturns
    upturn = upturns[0]
    assert upturn["fit_ready"] is False
    assert upturn["recommended_analysis"] is None
    assert upturn["metrics"]["alpha_delta"] > 0


def test_low_q_upturn_downgrades_overlapping_guinier_candidates() -> None:
    q = np.geomspace(0.004, 0.12, 140)
    rg = 9.0
    baseline = 80.0 * np.exp(-(q**2) * rg**2 / 3.0)
    upturned = baseline.copy()
    upturned[:24] *= (q[:24] / q[23]) ** -1.8
    curve = CurveData.create(name="guinier-with-upturn", q=q, intensity=upturned)

    result = detect_auto_regions(curve)
    upturn = _candidate_by_type(result, "low_q_upturn")[0]
    overlapping = [
        candidate
        for candidate in _candidate_by_type(result, "guinier_candidate")
        if candidate["q_start"] <= upturn["q_end"] and candidate["q_end"] >= upturn["q_start"]
    ]

    assert overlapping
    assert any("Low-q upturn overlaps" in " ".join(candidate["warnings"]) for candidate in overlapping)
    assert all(candidate["score"] < 0.85 for candidate in overlapping)


def test_power_law_out_of_range_alpha_is_downgraded() -> None:
    q = np.geomspace(0.01, 0.5, 160)
    curve = CurveData.create(name="alpha-nine", q=q, intensity=1.0e-8 * q**-9)

    result = detect_auto_regions(curve)
    candidates = _candidate_by_type(result, "power_law_candidate")

    assert candidates
    assert candidates[0]["metrics"]["alpha"] == pytest.approx(9.0, rel=0.08)
    assert candidates[0]["confidence_label"] in {"caution", "not_recommended"}
    assert any("outside the usual empirical SAS range" in warning for warning in candidates[0]["warnings"])


def test_detect_auto_regions_warns_without_mutating_invalid_input() -> None:
    q = np.array([0.2, 0.1, 0.1, 0.3, 0.4])
    intensity = np.array([10.0, 12.0, 11.0, 0.0, -1.0])
    original_q = q.copy()
    original_i = intensity.copy()
    curve = CurveData.create(name="invalid", q=q, intensity=intensity)

    result = detect_auto_regions(curve)
    warnings = "\n".join(result.results["detection_warnings"])

    np.testing.assert_allclose(curve.q, original_q)
    np.testing.assert_allclose(curve.intensity, original_i)
    assert "non-monotonic" in warnings
    assert "duplicate q" in warnings
    assert "I(q) <= 0" in warnings
    assert isinstance(result.results["candidates"], list)


def test_run_analysis_for_region_records_source_metadata_and_overrides_range() -> None:
    rg = 10.0
    q = np.linspace(0.004, 0.06, 80)
    intensity = 80.0 * np.exp(-(q**2) * rg**2 / 3.0)
    curve = CurveData.create(name="guinier", q=q, intensity=intensity)
    detection = detect_auto_regions(curve)
    candidate = AutoRegionCandidate.from_dict(_candidate_by_type(detection, "guinier_candidate")[0])

    result = run_analysis_for_region(curve, candidate, user_overridden_q_range=(candidate.q_start, candidate.q_end * 0.95))

    assert result.analysis_type == "guinier"
    assert result.results["source_auto_region_id"] == candidate.region_id
    assert result.results["source_region_type"] == "guinier_candidate"
    assert result.results["user_overrode_range"] is True
    assert result.results["original_q_range"] == (candidate.q_start, candidate.q_end)
    assert result.results["final_q_range"] == (candidate.q_start, candidate.q_end * 0.95)


def test_run_analysis_for_region_skips_not_fit_ready_without_force() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03], intensity=[10.0, 5.0, 3.0])
    candidate = AutoRegionCandidate(
        region_id="low-q-1",
        curve_id=curve.curve_id,
        curve_name=curve.name,
        region_type="low_q_upturn",
        q_start=0.01,
        q_end=0.02,
        d_start=characteristic_d_from_q(0.01),
        d_end=characteristic_d_from_q(0.02),
        transformed_x_start=None,
        transformed_x_end=None,
        n_points=2,
        detection_method="low_q_upturn_combined",
        score=0.6,
        confidence_label="caution",
        fit_ready=False,
        recommended_analysis=None,
        metrics={},
        warnings=["review manually"],
    )

    result = run_analysis_for_region(curve, candidate)

    assert result.analysis_type == "auto_region_skipped"
    assert "not fit-ready" in "\n".join(result.warnings)
    assert result.results["source_auto_region_id"] == "low-q-1"


def test_export_auto_region_candidates_csv_writes_traceable_table(tmp_path) -> None:
    q = np.geomspace(0.01, 0.4, 80)
    curve = CurveData.create(name="power-law", q=q, intensity=3.0 * q**-2.0)
    detection = detect_auto_regions(curve)
    path = export_auto_region_candidates_csv(detection.results["candidates"], tmp_path / "auto_regions.csv")

    table = pd.read_csv(path, encoding="utf-8-sig")

    assert path.exists()
    assert {
        "curve_id",
        "curve_name",
        "region_id",
        "region_type",
        "q_start",
        "q_end",
        "d_min",
        "d_max",
        "score",
        "confidence_label",
        "recommended_analysis",
        "metrics_json",
        "warnings",
        "source_detection_analysis_id",
    }.issubset(table.columns)
    json.loads(table.loc[0, "metrics_json"])
    assert table["source_detection_analysis_id"].notna().all()
    assert pd.api.types.is_numeric_dtype(table["q_start"])
    assert pd.api.types.is_numeric_dtype(table["score"])
