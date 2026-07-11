from __future__ import annotations

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, ParameterValue
from app.core.model_selection import (
    flag_possible_model_transitions,
    rank_models,
    select_batch_main_model,
)


def _model_envelope(
    frame: int,
    model_name: str,
    *,
    aicc: float | None,
    bic: float | None,
    success: bool = True,
    residual_pass: bool = True,
    bound_hit: bool = False,
    uncertainty: float | None = 0.1,
    reliability_label: str = "medium",
    reliability_score: float = 0.8,
) -> AnalysisEnvelope:
    return AnalysisEnvelope(
        curve_id=f"curve-{frame}",
        curve_name=f"frame-{frame}",
        analysis_id=f"curve-{frame}:shape_models:{model_name}",
        analysis_type="shape_models",
        status=AnalysisStatus.SUCCESS if success else AnalysisStatus.FIT_FAILED,
        q_range=(0.01, 0.2),
        parameters=[
            ParameterValue(name="model_name", value=model_name),
            ParameterValue(name="radius", value=10.0, stderr=uncertainty, bound_hit=bound_hit),
        ],
        fit_quality={
            "AICc": aicc,
            "BIC": bic,
            "residual_pass": residual_pass,
            "uncertainty_score": uncertainty,
        },
        reliability_label=reliability_label,
        reliability_score=reliability_score,
    )


def test_ranking_retains_low_coverage_model_but_never_selects_it_as_main() -> None:
    envelopes = [
        *[_model_envelope(frame, "sphere", aicc=20.0, bic=22.0) for frame in range(8)],
        *[_model_envelope(frame, "cylinder", aicc=1.0, bic=2.0) for frame in range(6)],
    ]

    rankings = rank_models(envelopes, total_frames=10)
    by_name = {item["model_name"]: item for item in rankings}

    assert by_name["sphere"]["coverage"] == 0.8
    assert by_name["sphere"]["eligible_for_main_model"] is True
    assert by_name["cylinder"]["coverage"] == 0.6
    assert by_name["cylinder"]["eligible_for_main_model"] is False
    assert select_batch_main_model(rankings) == "sphere"


def test_zero_residual_pass_rate_is_not_eligible_for_main_model() -> None:
    """Coverage alone must not promote a model with failed residual checks."""

    envelopes = [
        *[
            _model_envelope(frame, "lamellar_peak_stack", aicc=5.0, bic=6.0, residual_pass=False, uncertainty=0.05)
            for frame in range(10)
        ],
        *[_model_envelope(frame, "sphere", aicc=20.0, bic=22.0, residual_pass=True, uncertainty=0.05) for frame in range(10)],
    ]

    rankings = rank_models(envelopes, total_frames=10)
    by_name = {item["model_name"]: item for item in rankings}

    assert by_name["lamellar_peak_stack"]["coverage"] == 1.0
    assert by_name["lamellar_peak_stack"]["residual_pass_rate"] == 0.0
    assert by_name["lamellar_peak_stack"]["eligible_for_main_model"] is False
    assert "residual_pass_rate_below_threshold" in by_name["lamellar_peak_stack"]["eligibility_failures"]
    assert by_name["sphere"]["eligible_for_main_model"] is True
    assert select_batch_main_model(rankings) == "sphere"


def test_high_bound_hit_or_missing_uncertainty_blocks_main_model() -> None:
    bound_hit_model = [_model_envelope(frame, "cylinder", aicc=8.0, bic=9.0, bound_hit=True) for frame in range(10)]
    no_uncertainty = [
        _model_envelope(frame, "ellipsoid", aicc=7.0, bic=8.0, uncertainty=None) for frame in range(10)
    ]
    good = [_model_envelope(frame, "sphere", aicc=15.0, bic=16.0, uncertainty=0.05) for frame in range(10)]

    rankings = rank_models([*bound_hit_model, *no_uncertainty, *good], total_frames=10)
    by_name = {item["model_name"]: item for item in rankings}

    assert by_name["cylinder"]["eligible_for_main_model"] is False
    assert "bound_hit_rate_above_threshold" in by_name["cylinder"]["eligibility_failures"]
    assert by_name["ellipsoid"]["eligible_for_main_model"] is False
    assert "uncertainty_missing" in by_name["ellipsoid"]["eligibility_failures"]
    assert select_batch_main_model(rankings) == "sphere"


def test_possible_transition_requires_three_consecutive_frames_without_switching_main_model() -> None:
    envelopes = []
    for frame in range(4):
        envelopes.append(_model_envelope(frame, "sphere", aicc=20.0, bic=22.0))
        envelopes.append(
            _model_envelope(
                frame,
                "cylinder",
                aicc=10.0 if frame < 3 else 30.0,
                bic=12.0 if frame < 3 else 32.0,
            )
        )

    flags = flag_possible_model_transitions(envelopes, main_model="sphere")

    assert [flag["frame_best_model"] for flag in flags] == ["cylinder", "cylinder", "cylinder", "sphere"]
    assert [flag["possible_model_transition"] for flag in flags] == [False, False, True, False]
    assert flags[2]["candidate_model"] == "cylinder"
    assert flags[2]["consecutive_frames"] == 3
    assert all(flag["main_model"] == "sphere" for flag in flags)
