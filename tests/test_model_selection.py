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
