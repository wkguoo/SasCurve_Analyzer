from __future__ import annotations

from copy import deepcopy
from math import exp, sqrt
from types import SimpleNamespace

import numpy as np
import pytest

import app.core.batch_consensus as batch_consensus
from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_consensus import ConsensusRegion, candidate_consensus, resolve_consensus_regions
from app.core.data_model import CurveData


def _candidate(
    curve_id: str | None,
    q_start: float,
    q_end: float,
    score: float,
    *,
    fit_ready: object = True,
    region_type: str = "guinier_candidate",
    n_points: float = 0.0,
) -> dict[str, object]:
    return {
        "curve_id": curve_id,
        "q_start": q_start,
        "q_end": q_end,
        "score": score,
        "fit_ready": fit_ready,
        "region_type": region_type,
        "n_points": n_points,
    }


def test_candidate_consensus_prefers_high_coverage_over_single_high_score() -> None:
    candidates = [
        _candidate("a", 0.01, 0.03, 0.8),
        _candidate("b", 0.011, 0.031, 0.9),
        _candidate("c", 0.2, 0.3, 0.99),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=3, min_coverage=0.66)

    assert result is not None
    assert result.region_type == "guinier"
    assert result.coverage == pytest.approx(2 / 3)
    assert result.median_score == pytest.approx(0.85)
    assert result.candidate_n_points_min == pytest.approx(0.0)
    assert result.candidate_n_points_max == pytest.approx(0.0)
    assert result.q_range == pytest.approx((0.011, 0.03))
    assert result.log_median_q_range == pytest.approx((sqrt(0.01 * 0.011), sqrt(0.03 * 0.031)))
    assert result.supporting_curve_ids == ("a", "b")


def test_candidate_consensus_returns_none_below_coverage() -> None:
    result = candidate_consensus(
        "porod",
        [_candidate("a", 0.2, 0.3, 0.9, region_type="porod_candidate")],
        curve_count=4,
        min_coverage=0.70,
    )

    assert result is None


def test_candidate_consensus_deduplicates_curve_ids_and_ignores_unready_or_invalid_rows() -> None:
    candidates = [
        _candidate("a", 0.01, 0.03, 0.2),
        _candidate("a", 0.011, 0.031, 0.9),
        _candidate("b", 0.012, 0.032, 0.8),
        _candidate("c", 0.011, 0.031, 0.99, fit_ready=False),
        _candidate("d", 0.0, 0.031, 0.99),
        _candidate("e", 0.04, 0.04, 0.99),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=3, min_coverage=0.66)
    reversed_result = candidate_consensus("guinier", list(reversed(candidates)), curve_count=3, min_coverage=0.66)

    assert result is not None
    assert result == reversed_result
    assert result.supporting_curve_ids == ("a", "b")
    assert result.coverage == pytest.approx(2 / 3)
    assert result.median_score == pytest.approx(0.85)
    assert result.q_range == pytest.approx((0.012, 0.031))
    assert result.log_median_q_range == pytest.approx((sqrt(0.011 * 0.012), sqrt(0.031 * 0.032)))


def test_candidate_consensus_uses_deterministic_tie_break_for_equal_clusters() -> None:
    candidates = [
        _candidate("high", 0.20, 0.30, 0.8),
        _candidate("low", 0.01, 0.02, 0.8),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=0.5)
    reversed_result = candidate_consensus("guinier", list(reversed(candidates)), curve_count=2, min_coverage=0.5)

    assert result is not None
    assert result == reversed_result
    assert result.q_range == pytest.approx((0.01, 0.02))
    assert result.supporting_curve_ids == ("low",)


def test_candidate_consensus_uses_strict_common_range_and_retains_log_median_audit_range() -> None:
    candidates = [
        _candidate("a", 0.01, 0.04, 0.8),
        _candidate("b", 0.02, 0.03, 0.9),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=1.0)

    assert result is not None
    assert result.q_range == pytest.approx((0.02, 0.03))
    assert result.log_median_q_range == pytest.approx((sqrt(0.01 * 0.02), sqrt(0.04 * 0.03)))
    for candidate in candidates:
        assert float(candidate["q_start"]) <= result.q_range[0]
        assert result.q_range[1] <= float(candidate["q_end"])


def test_candidate_consensus_rejects_nearby_centers_without_a_common_interval() -> None:
    candidates = [
        _candidate("a", 0.90, 1.00, 0.8),
        _candidate("b", 1.25, 1.35, 0.9),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=1.0)

    assert result is None


def test_candidate_consensus_includes_exact_log_center_threshold_and_rejects_values_above_it() -> None:
    q_start, q_end = 0.10, 0.20
    threshold = batch_consensus.LOG_Q_CENTER_CLUSTER_THRESHOLD
    at_threshold = [
        _candidate("a", q_start, q_end, 0.8),
        _candidate("b", q_start * exp(threshold), q_end * exp(threshold), 0.8),
    ]
    above_threshold = [
        _candidate("a", q_start, q_end, 0.8),
        _candidate("b", q_start * exp(threshold + 0.0001), q_end * exp(threshold + 0.0001), 0.8),
    ]

    exact_result = candidate_consensus("guinier", at_threshold, curve_count=2, min_coverage=1.0)
    above_result = candidate_consensus("guinier", above_threshold, curve_count=2, min_coverage=1.0)

    assert exact_result is not None
    assert exact_result.coverage == pytest.approx(1.0)
    assert above_result is None


def test_candidate_consensus_accepts_exact_minimum_coverage_and_rejects_just_below_it() -> None:
    candidates = [
        _candidate("a", 0.01, 0.03, 0.8),
        _candidate("b", 0.011, 0.031, 0.9),
    ]
    exact_minimum = 2 / 3

    exact_result = candidate_consensus("guinier", candidates, curve_count=3, min_coverage=exact_minimum)
    below_result = candidate_consensus("guinier", candidates, curve_count=3, min_coverage=exact_minimum + 0.0001)

    assert exact_result is not None
    assert exact_result.coverage == pytest.approx(exact_minimum)
    assert below_result is None


def test_candidate_consensus_prefers_higher_median_score_when_coverage_matches() -> None:
    candidates = [
        _candidate("low_score", 0.01, 0.02, 0.7),
        _candidate("high_score", 0.20, 0.30, 0.9),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=0.5)

    assert result is not None
    assert result.supporting_curve_ids == ("high_score",)
    assert result.median_score == pytest.approx(0.9)


def test_candidate_consensus_prefers_more_points_for_equal_score_candidates_from_one_curve() -> None:
    candidates = [
        _candidate("a", 0.01, 0.03, 0.8, n_points=float("nan")),
        _candidate("a", 0.011, 0.031, 0.8, n_points=10),
        _candidate("b", 0.012, 0.032, 0.8, n_points=8),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=1.0)

    assert result is not None
    assert result.q_range == pytest.approx((0.012, 0.031))
    assert result.median_n_points == pytest.approx(9.0)


def test_candidate_consensus_prefers_higher_median_points_after_coverage_and_score_ties() -> None:
    candidates = [
        _candidate("low_points", 0.01, 0.02, 0.8, n_points=5),
        _candidate("high_points", 0.20, 0.30, 0.8, n_points=25),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=2, min_coverage=0.5)

    assert result is not None
    assert result.supporting_curve_ids == ("high_points",)
    assert result.median_n_points == pytest.approx(25.0)


def test_candidate_consensus_rejects_none_ids_and_never_allows_coverage_above_one() -> None:
    valid_and_none = [
        _candidate("a", 0.01, 0.03, 0.8),
        _candidate(None, 0.011, 0.031, 0.9),
    ]
    too_many_supporters = [
        _candidate("a", 0.01, 0.03, 0.8),
        _candidate("b", 0.011, 0.031, 0.9),
    ]

    valid_result = candidate_consensus("guinier", valid_and_none, curve_count=1, min_coverage=1.0)
    too_many_result = candidate_consensus("guinier", too_many_supporters, curve_count=1, min_coverage=0.5)
    zero_count_result = candidate_consensus("guinier", valid_and_none, curve_count=0, min_coverage=0.5)

    assert valid_result is not None
    assert valid_result.supporting_curve_ids == ("a",)
    assert valid_result.coverage == pytest.approx(1.0)
    assert too_many_result is None
    assert zero_count_result is None


def test_candidate_consensus_accepts_only_boolean_true_fit_ready() -> None:
    candidates = [
        _candidate("valid", 0.01, 0.03, 0.8, fit_ready=True),
        _candidate("string_false", 0.011, 0.031, 0.99, fit_ready="False"),
        _candidate("string_zero", 0.012, 0.032, 0.99, fit_ready="0"),
        _candidate("nan", 0.013, 0.033, 0.99, fit_ready=float("nan")),
    ]

    result = candidate_consensus("guinier", candidates, curve_count=1, min_coverage=1.0)

    assert result is not None
    assert result.supporting_curve_ids == ("valid",)
    assert result.coverage == pytest.approx(1.0)


def test_resolve_consensus_regions_maps_real_auto_region_types_without_mutating_curves(monkeypatch) -> None:
    curves = [
        CurveData.create(name="frame_001", q=[0.01, 0.02, 0.03], intensity=[10.0, 5.0, 2.0], metadata={"step": 1}),
        CurveData.create(name="frame_002", q=[0.01, 0.02, 0.03], intensity=[12.0, 6.0, 2.4], metadata={"step": 2}),
    ]
    q_before = [curve.q.copy() for curve in curves]
    intensity_before = [curve.intensity.copy() for curve in curves]
    metadata_before = [deepcopy(curve.metadata) for curve in curves]
    candidates_by_id = {
        curve.curve_id: [
            _candidate(curve.curve_id, 0.01, 0.03, 0.8, region_type="guinier_candidate"),
            _candidate(curve.curve_id, 0.04, 0.08, 0.7, region_type="power_law_candidate"),
            _candidate(curve.curve_id, 0.10, 0.20, 0.9, region_type="porod_candidate"),
            _candidate(curve.curve_id, 0.21, 0.24, 0.6, region_type="peak_candidate"),
            _candidate(curve.curve_id, 0.001, 0.005, 0.99, region_type="low_q_upturn"),
        ]
        for curve in curves
    }

    def fake_detect_auto_regions(curve: CurveData, q_range=None) -> SimpleNamespace:
        return SimpleNamespace(results={"candidates": candidates_by_id[curve.curve_id]})

    monkeypatch.setattr(batch_consensus, "detect_auto_regions", fake_detect_auto_regions)

    result = resolve_consensus_regions(curves, AutoBatchConfig(batch_id="batch"))

    assert set(result) == {"guinier", "power_law", "porod", "peak"}
    assert all(isinstance(region, ConsensusRegion) for region in result.values())
    assert {key: region.region_type for key, region in result.items()} == {
        "guinier": "guinier",
        "power_law": "power_law",
        "porod": "porod",
        "peak": "peak",
    }
    assert all(region.coverage == pytest.approx(1.0) for region in result.values())
    assert all(region.supporting_curve_ids == tuple(sorted(curve.curve_id for curve in curves)) for region in result.values())
    for curve, expected_q, expected_intensity, expected_metadata in zip(curves, q_before, intensity_before, metadata_before):
        assert np.array_equal(curve.q, expected_q)
        assert np.array_equal(curve.intensity, expected_intensity)
        assert curve.metadata == expected_metadata


def test_resolve_consensus_regions_ignores_foreign_and_none_candidate_ids(monkeypatch) -> None:
    curves = [
        CurveData.create(name="frame_001", q=[0.01, 0.02, 0.03], intensity=[10.0, 5.0, 2.0]),
        CurveData.create(name="frame_002", q=[0.01, 0.02, 0.03], intensity=[12.0, 6.0, 2.4]),
    ]
    candidates_by_id = {
        curves[0].curve_id: [
            _candidate(curves[0].curve_id, 0.01, 0.03, 0.8),
            _candidate(curves[1].curve_id, 0.011, 0.031, 0.99),
            _candidate(None, 0.012, 0.032, 0.99),
        ],
        curves[1].curve_id: [
            _candidate(curves[0].curve_id, 0.011, 0.031, 0.99),
            _candidate(None, 0.012, 0.032, 0.99),
        ],
    }

    def fake_detect_auto_regions(curve: CurveData, q_range=None) -> SimpleNamespace:
        return SimpleNamespace(results={"candidates": candidates_by_id[curve.curve_id]})

    monkeypatch.setattr(batch_consensus, "detect_auto_regions", fake_detect_auto_regions)

    result = resolve_consensus_regions(curves, AutoBatchConfig(batch_id="batch"))

    assert result == {}


def test_candidate_consensus_returns_none_for_empty_candidates() -> None:
    assert candidate_consensus("guinier", [], curve_count=1, min_coverage=0.70) is None


def test_resolve_consensus_regions_returns_empty_mapping_for_no_curves() -> None:
    assert resolve_consensus_regions([], AutoBatchConfig(batch_id="empty")) == {}


def test_resolve_consensus_regions_bounds_coverage_and_deduplicates_support_for_duplicate_curve_ids(monkeypatch) -> None:
    curves = [
        CurveData.create(name="frame_001", q=[0.01, 0.02, 0.03], intensity=[10.0, 5.0, 2.0]),
        CurveData.create(name="frame_002", q=[0.01, 0.02, 0.03], intensity=[12.0, 6.0, 2.4]),
    ]
    curves[1].curve_id = curves[0].curve_id

    def fake_detect_auto_regions(curve: CurveData, q_range=None) -> SimpleNamespace:
        return SimpleNamespace(
            results={
                "candidates": [
                    _candidate(curve.curve_id, 0.01, 0.03, 0.8, region_type="guinier_candidate"),
                ]
            }
        )

    monkeypatch.setattr(batch_consensus, "detect_auto_regions", fake_detect_auto_regions)

    result = resolve_consensus_regions(curves, AutoBatchConfig(batch_id="duplicate-id"))

    assert set(result) == {"guinier"}
    region = result["guinier"]
    assert region.coverage <= 1.0
    assert region.coverage == pytest.approx(1.0)
    assert region.supporting_curve_ids == (curves[0].curve_id,)
