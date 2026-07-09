from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.io import load_curve, QImportRangeFilterError


def test_csv_import() -> None:
    path = Path("examples/example_absolute_sas_curve.csv")
    curve = load_curve(path, q_column="q", intensity_column="I", error_column="error")
    assert curve.q.size == 30
    assert curve.error is not None
    assert curve.source_file is not None
    assert curve.processing_history[0]["action"] == "import"


def test_txt_dat_separator_detection(tmp_path: Path) -> None:
    txt_path = tmp_path / "curve.dat"
    txt_path.write_text("# comment\nq I sigma\n0.1 10 0.2\n0.2 5 0.1\n", encoding="utf-8")
    curve = load_curve(txt_path, q_column="q", intensity_column="I", error_column="sigma")
    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])
    assert curve.error is not None


def test_import_without_error_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.1,10\n0.2,5\n", encoding="utf-8")
    curve = load_curve(csv_path, q_column="q", intensity_column="I", error_column=None)
    assert curve.error is None
    assert curve.q.size == 2


def test_blank_error_column_is_treated_as_missing(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.1,10\n0.2,5\n", encoding="utf-8")
    curve = load_curve(csv_path, q_column="q", intensity_column="I", error_column="")
    assert curve.error is None


def test_import_reads_gbk_encoded_curve(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve_gbk.csv"
    csv_path.write_bytes("# 样品\nq,I\n0.1,10\n0.2,5\n".encode("gbk"))

    curve = load_curve(csv_path, q_column="q", intensity_column="I")

    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])


def test_import_reads_utf16_encoded_curve(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve_utf16.csv"
    csv_path.write_text("# sample\nq,I\n0.1,10\n0.2,5\n", encoding="utf-16")

    curve = load_curve(csv_path, q_column="q", intensity_column="I")

    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])


def test_load_curve_filters_closed_raw_q_range_and_error(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text(
        "q,I,error\n"
        "0.005,1,0.01\n"
        "0.01,10,0.1\n"
        "0.03,8,0.2\n"
        "0.05,6,0.3\n"
        "0.06,4,0.4\n",
        encoding="utf-8",
    )

    curve = load_curve(
        csv_path,
        q_column="q",
        intensity_column="I",
        error_column="error",
        limit_q_range=True,
        q_min=0.01,
        q_max=0.05,
    )

    assert np.allclose(curve.q, [0.01, 0.03, 0.05])
    assert np.allclose(curve.intensity, [10.0, 8.0, 6.0])
    assert curve.error is not None
    assert np.allclose(curve.error, [0.1, 0.2, 0.3])
    q_filter = curve.metadata["import_q_range_filter"]
    assert q_filter["enabled"] is True
    assert q_filter["raw_point_count"] == 5
    assert q_filter["imported_point_count"] == 3
    assert q_filter["filtered_out_point_count"] == 2
    assert curve.processing_history[0]["q_range_filter_enabled"] is True
    assert curve.processing_history[0]["raw_point_count"] == 5


def test_load_curve_preserves_old_behavior_when_q_range_filter_disabled(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.005,1\n0.01,10\n0.05,6\n0.06,4\n", encoding="utf-8")

    curve = load_curve(csv_path, q_column="q", intensity_column="I", limit_q_range=False, q_min=0.01, q_max=0.05)

    assert np.allclose(curve.q, [0.005, 0.01, 0.05, 0.06])
    assert "import_q_range_filter" not in curve.metadata
    assert "q_range_filter_enabled" not in curve.processing_history[0]


def test_load_curve_rejects_invalid_q_import_range(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.01,10\n0.02,8\n", encoding="utf-8")

    with pytest.raises(ValueError, match="q_min=0.05"):
        load_curve(csv_path, q_column="q", intensity_column="I", limit_q_range=True, q_min=0.05, q_max=0.01)


def test_load_curve_rejects_q_range_with_too_few_points(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.01,10\n0.02,8\n0.10,5\n", encoding="utf-8")

    with pytest.raises(ValueError, match="kept 1 points"):
        load_curve(csv_path, q_column="q", intensity_column="I", limit_q_range=True, q_min=0.015, q_max=0.025)


def test_q_range_filter_error_carries_diagnostics(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.01,10\n0.02,8\n0.10,5\n", encoding="utf-8")

    with pytest.raises(QImportRangeFilterError, match="kept 1 points") as excinfo:
        load_curve(csv_path, q_column="q", intensity_column="I", limit_q_range=True, q_min=0.015, q_max=0.025)

    assert isinstance(excinfo.value, ValueError)
    assert excinfo.value.diagnostics["q_range_filter_enabled"] is True
    assert excinfo.value.diagnostics["q_range_filter_min"] == 0.015
    assert excinfo.value.diagnostics["q_range_filter_max"] == 0.025
    assert excinfo.value.diagnostics["raw_point_count"] == 3
    assert excinfo.value.diagnostics["imported_point_count"] == 1
    assert excinfo.value.diagnostics["filtered_out_point_count"] == 2

