from __future__ import annotations

from types import SimpleNamespace

import app.core.auto_batch as auto_batch
from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig
from app.core.batch_consensus import ConsensusRegion
from app.core.batch_inputs import BatchInputCollection
from app.core.data_model import CurveData


def _envelope(curve: CurveData, method_id: str, q_range):
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}",
        analysis_type=method_id,
        status=AnalysisStatus.SUCCESS,
        q_range=q_range,
    )


def test_dual_mode_keeps_adaptive_and_common_results_separate(monkeypatch) -> None:
    main = CurveData.create(
        name="Ti15_00001",
        q=[0.01, 0.012, 0.016, 0.018, 0.025, 0.05],
        intensity=[10, 9, 7, 6, 4, 2],
        metadata={"sequence_role": "series", "is_reference": False},
    )
    reference = CurveData.create(
        name="Ti15-rt_00001",
        q=[0.01, 0.012, 0.016, 0.018, 0.025, 0.05],
        intensity=[11, 10, 8, 7, 5, 3],
        metadata={"sequence_role": "reference", "is_reference": True},
    )
    monkeypatch.setattr(
        auto_batch,
        "collect_batch_inputs",
        lambda *_args: BatchInputCollection(curves=[main, reference], manifest=[]),
    )
    monkeypatch.setattr(auto_batch, "applicable_method_ids", lambda _config: ["guinier"])
    monkeypatch.setattr(
        auto_batch,
        "resolve_consensus_regions",
        lambda *_args: {
            "guinier": ConsensusRegion(
                region_type="guinier",
                q_range=(0.012, 0.018),
                coverage=1.0,
                median_score=0.9,
                supporting_curve_ids=(main.curve_id,),
                median_n_points=4.0,
                candidate_n_points_min=4.0,
                candidate_n_points_max=4.0,
                log_median_q_range=(0.012, 0.018),
            )
        },
    )

    def detection(curve, q_range=None):
        adaptive = (0.01, 0.016) if curve is main else (0.016, 0.025)
        return SimpleNamespace(
            results={
                "candidates": [
                    {
                        "region_type": "guinier_candidate",
                        "q_start": adaptive[0],
                        "q_end": adaptive[1],
                        "score": 0.95,
                        "n_points": 4,
                        "fit_ready": True,
                    }
                ]
            }
        )

    monkeypatch.setattr(auto_batch, "detect_auto_regions", detection)
    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="dual", range_mode="dual"),
        analysis_runner=lambda curve, method, q_range, config: [_envelope(curve, method, q_range)],
    )

    assert len(run.analyses) == 4
    assert len({item.analysis_id for item in run.analyses}) == 4
    assert {item.range_track for item in run.analyses} == {"adaptive", "common"}
    main_common = next(item for item in run.analyses if item.curve_id == main.curve_id and item.range_track == "common")
    reference_common = next(
        item for item in run.analyses if item.curve_id == reference.curve_id and item.range_track == "common"
    )
    assert main_common.q_range == (0.012, 0.018)
    assert main_common.common_range_supported is True
    assert reference_common.q_range == (0.012, 0.018)
    assert reference_common.common_range_supported is None


def test_dual_mode_leaves_missing_common_track_empty_without_borrowing_adaptive(monkeypatch) -> None:
    curve = CurveData.create(name="frame", q=[0.01, 0.02, 0.03, 0.05], intensity=[4, 3, 2, 1])
    monkeypatch.setattr(
        auto_batch,
        "collect_batch_inputs",
        lambda *_args: BatchInputCollection(curves=[curve], manifest=[]),
    )
    monkeypatch.setattr(auto_batch, "applicable_method_ids", lambda _config: ["power_law"])
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda *_args: {})
    monkeypatch.setattr(
        auto_batch,
        "detect_auto_regions",
        lambda *_args, **_kwargs: SimpleNamespace(
            results={
                "candidates": [
                    {
                        "region_type": "power_law_candidate",
                        "q_start": 0.01,
                        "q_end": 0.03,
                        "score": 0.9,
                        "n_points": 3,
                        "fit_ready": True,
                    }
                ]
            }
        ),
    )
    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="dual-empty", range_mode="dual"),
        analysis_runner=lambda item, method, q_range, config: [_envelope(item, method, q_range)],
    )

    adaptive = next(item for item in run.analyses if item.range_track == "adaptive")
    common = next(item for item in run.analyses if item.range_track == "common")
    assert adaptive.q_range == (0.01, 0.03)
    assert common.q_range is None
    assert common.status is AnalysisStatus.SUCCESS
    assert "common_track_not_executed" in common.range_reason_codes

