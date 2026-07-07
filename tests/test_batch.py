from __future__ import annotations

import numpy as np

import pandas as pd

from app.core.batch import average_replicates, build_sequence_index, export_sequence_index_csv
from app.core.data_model import CurveData


def test_average_matching_q_grid() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20], error=[1, 1])
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[14, 22], error=[1, 1])
    averaged, record = average_replicates([c1, c2], interpolate=False)
    assert np.allclose(averaged.q, [0.1, 0.2])
    assert np.allclose(averaged.intensity, [12, 21])
    assert record.action_type == "average_replicates"


def test_average_interpolates_mismatched_q_grid() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2, 0.3], intensity=[10, 20, 30])
    c2 = CurveData.create(name="b", q=[0.15, 0.25, 0.35], intensity=[15, 25, 35])
    averaged, record = average_replicates([c1, c2], interpolate=True)
    assert averaged.q.min() >= 0.15
    assert averaged.q.max() <= 0.3
    assert record.warnings


def test_average_interpolates_after_sorting_unsorted_q() -> None:
    c1 = CurveData.create(name="a", q=[0.3, 0.1, 0.2], intensity=[30, 10, 20])
    c2 = CurveData.create(name="b", q=[0.1, 0.2, 0.3], intensity=[11, 22, 33])

    averaged, record = average_replicates([c1, c2], interpolate=True)

    assert np.allclose(averaged.q, [0.1, 0.2, 0.3])
    assert np.allclose(averaged.intensity, [10.5, 21.0, 31.5])
    assert not record.warnings


def test_average_does_not_modify_original_curves() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20])
    original = c1.intensity.copy()
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[14, 22])
    averaged, _record = average_replicates([c1, c2])
    assert np.allclose(c1.intensity, original)
    assert averaged.curve_id != c1.curve_id


def test_build_sequence_index_uses_metadata_and_warns_about_q_grid() -> None:
    c1 = CurveData.create(
        name="sample_00001",
        q=[0.1, 0.2],
        intensity=[10, 20],
        metadata={"sequence_order": 0, "series_id": "sample", "frame_label": "00001", "frame_index": 1, "source_stem": "sample_00001"},
    )
    c2 = CurveData.create(
        name="sample_00002",
        q=[0.1, 0.25],
        intensity=[8, -1],
        metadata={"sequence_order": 1, "series_id": "sample", "frame_label": "00002", "frame_index": 2, "source_stem": "sample_00002"},
    )

    rows = build_sequence_index([c1, c2])

    assert rows[0]["sequence_order"] == 0
    assert rows[0]["frame_label"] == "00001"
    assert rows[0]["warnings"] == "OK"
    assert "q grid differs" in rows[1]["warnings"]
    assert "non-positive intensity" in rows[1]["warnings"]


def test_build_sequence_index_handles_curves_without_metadata() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[1, 2])
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[3, 4])

    rows = build_sequence_index([c1, c2])

    assert [row["project_order"] for row in rows] == [0, 1]
    assert [row["sequence_order"] for row in rows] == [0, 1]
    assert rows[0]["frame_label"] is None


def test_export_sequence_index_csv(tmp_path) -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[1, 2], metadata={"sequence_order": 0})
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[3, 4], metadata={"sequence_order": 1})

    path = export_sequence_index_csv([c1, c2], tmp_path / "sequence_index.csv")
    table = pd.read_csv(path)

    assert path.exists()
    assert table["curve_name"].tolist() == ["a", "b"]
    assert "warnings" in table.columns

