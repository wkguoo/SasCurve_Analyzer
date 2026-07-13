from copy import deepcopy

import numpy as np
import pytest

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig, ParameterValue
from app.core.data_model import CurveData
from app.core.sequence_analysis import analyze_sequence


def _curve(index: int, scale: float = 1.0) -> CurveData:
    return CurveData.create(name=f"frame_{index:03d}", q=[0.01, 0.02, 0.03, 0.04], intensity=np.array([10, 7, 4, 2]) * scale, metadata={"frame_index": index})


def _analysis(curve: CurveData, value: float) -> AnalysisEnvelope:
    return AnalysisEnvelope(curve.curve_id, curve.name, f"{curve.curve_id}:guinier", "guinier", AnalysisStatus.SUCCESS, (0.01, 0.04), parameters=[ParameterValue("Rg", value, "nm")])


def test_sequence_analysis_orders_frames_and_preserves_inputs() -> None:
    curves = [_curve(2, 1.2), _curve(0), _curve(1, 1.1)]
    analyses = [_analysis(curve, float(curve.metadata["frame_index"] + 5)) for curve in curves]
    before = [(curve.q.copy(), curve.intensity.copy(), deepcopy(curve.metadata)) for curve in curves]

    result = analyze_sequence(curves, analyses, AutoBatchConfig(batch_id="b"))

    assert result["sequence_axis"] == "frame_index"
    assert [row["axis_value"] for row in result["frame_table"]] == [0.0, 1.0, 2.0]
    assert len(result["parameter_trajectories"]) == 3
    assert len(result["reference_comparisons"]) == 3
    for curve, expected in zip(curves, before):
        assert np.array_equal(curve.q, expected[0])
        assert np.array_equal(curve.intensity, expected[1])
        assert curve.metadata == expected[2]


def test_sequence_reference_comparison_uses_effective_q_range() -> None:
    curves = [_curve(0), _curve(1, 1.1)]
    config = AutoBatchConfig(batch_id="b", effective_q_range=(0.02, 0.03))

    result = analyze_sequence(curves, [], config)

    assert result["effective_q_range"] == [0.02, 0.03]
    assert result["reference_comparisons"][0]["overlap_q_start"] == pytest.approx(0.02)
    assert result["reference_comparisons"][0]["overlap_q_end"] == pytest.approx(0.03)


def test_sequence_analysis_flags_robust_parameter_jump() -> None:
    curves = [_curve(i) for i in range(6)]
    values = [1.0, 1.1, 1.2, 8.0, 8.1, 8.2]
    result = analyze_sequence(curves, [_analysis(c, v) for c, v in zip(curves, values)], AutoBatchConfig(batch_id="b"))
    assert result["change_flags"][0]["frame"] == 3
    assert result["change_flags"][0]["interpretation"] == "review_candidate_not_phase_transition_proof"


def test_sequence_analysis_keeps_dual_tracks_as_separate_trajectories() -> None:
    curves = [_curve(i) for i in range(4)]
    analyses: list[AnalysisEnvelope] = []
    for curve in curves:
        frame = float(curve.metadata["frame_index"])
        analyses.append(
            AnalysisEnvelope(
                curve.curve_id,
                curve.name,
                f"{curve.curve_id}:guinier:adaptive",
                "guinier",
                AnalysisStatus.SUCCESS,
                (0.01, 0.03),
                parameters=[ParameterValue("Rg", 10.0 + frame, "nm")],
                range_track="adaptive",
            )
        )
        analyses.append(
            AnalysisEnvelope(
                curve.curve_id,
                curve.name,
                f"{curve.curve_id}:guinier:common",
                "guinier",
                AnalysisStatus.SUCCESS,
                (0.01, 0.025),
                parameters=[ParameterValue("Rg", 20.0 + frame, "nm")],
                range_track="common",
            )
        )

    result = analyze_sequence(curves, analyses, AutoBatchConfig(batch_id="b", enable_kinetics=True))
    trajectories = result["parameter_trajectories"]
    adaptive_rows = [row for row in trajectories if row["range_track"] == "adaptive" and row["parameter"] == "Rg"]
    common_rows = [row for row in trajectories if row["range_track"] == "common" and row["parameter"] == "Rg"]

    assert len(trajectories) == 8  # 4 frames × 2 tracks
    assert len(adaptive_rows) == 4
    assert len(common_rows) == 4
    assert sorted(row["value"] for row in adaptive_rows) == pytest.approx([10.0, 11.0, 12.0, 13.0])
    assert sorted(row["value"] for row in common_rows) == pytest.approx([20.0, 21.0, 22.0, 23.0])
    # Trends must fit one value per frame per track, not 2N mixed points.
    trends = {(row["range_track"], row["parameter"]): row for row in result["linear_trends"]}
    assert trends[("adaptive", "Rg")]["point_count"] == 4
    assert trends[("common", "Rg")]["point_count"] == 4
    assert trends[("adaptive", "Rg")]["slope"] == pytest.approx(1.0)
    assert not result["change_flags"]


def test_optional_trends_and_exploratory_statistics_are_reproducible() -> None:
    curves = [_curve(i, 1 + i * 0.1) for i in range(4)]
    analyses = [_analysis(curve, 2.0 * i + 1.0) for i, curve in enumerate(curves)]
    config = AutoBatchConfig(batch_id="b", enable_kinetics=True, enable_exploratory_statistics=True, pca_components=2, cluster_count=2, random_seed=7)
    first = analyze_sequence(curves, analyses, config)
    second = analyze_sequence(curves, analyses, config)
    assert first["linear_trends"][0]["slope"] == pytest.approx(2.0)
    assert first["exploratory_statistics"] == second["exploratory_statistics"]
    assert len(first["exploratory_statistics"]["scores"]) == 4


def test_missing_selected_reference_is_explicit() -> None:
    curve = _curve(0)
    config = AutoBatchConfig(batch_id="b", reference_mode="selected", reference_curve_id="missing")
    result = analyze_sequence([curve], [_analysis(curve, 1.0)], config)
    assert result["reference_comparisons"] == []
    assert "not found" in result["warnings"][0]


def test_sequence_analysis_sorts_reversed_q_before_reference_integration() -> None:
    curves = [
        CurveData.create(name="reference", q=[0.01, 0.02, 0.03], intensity=[3.0, 2.0, 1.0]),
        CurveData.create(name="reversed", q=[0.03, 0.02, 0.01], intensity=[1.0, 2.0, 3.0]),
    ]

    result = analyze_sequence(curves, [], AutoBatchConfig(batch_id="b"))

    comparison = result["reference_comparisons"][1]
    assert comparison["relative_absolute_area"] == 0.0
    assert comparison["point_count"] == 3


def test_exploratory_statistics_handles_nan_intensity_without_svd_failure() -> None:
    curves = [
        CurveData.create(name="a", q=[0.01, 0.02, 0.03], intensity=[3.0, np.nan, 1.0]),
        CurveData.create(name="b", q=[0.01, 0.02, 0.03], intensity=[4.0, 2.0, 1.0]),
    ]

    result = analyze_sequence(
        curves,
        [],
        AutoBatchConfig(batch_id="b", enable_exploratory_statistics=True),
    )

    assert result["exploratory_statistics"]["status"] == "success"
    assert len(result["exploratory_statistics"]["scores"]) == 2
