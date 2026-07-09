from __future__ import annotations

from app.core.batch_import import (
    create_in_situ_group,
    import_in_situ_series,
    infer_curve_columns,
    parse_sequence_metadata,
)
from app.core.project import ProjectState


def _write_curve(path, intensity: float = 10.0) -> None:
    path.write_text(f"q_A_inv,intensity_cm_inv\n0.1,{intensity}\n0.2,{intensity / 2}\n", encoding="utf-8")


def _write_range_curve(path, q_values: list[float]) -> None:
    rows = ["q_A_inv,intensity_cm_inv"]
    rows.extend(f"{q},{10.0 - index}" for index, q in enumerate(q_values))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_parse_sequence_metadata_from_in_situ_filename() -> None:
    metadata = parse_sequence_metadata("ti15_00001_abs2d_cm-1.csv")
    assert metadata["series_id"] == "ti15"
    assert metadata["frame_label"] == "00001"
    assert metadata["frame_index"] == 1


def test_infer_curve_columns_for_abs_csv() -> None:
    columns = infer_curve_columns(["q_A_inv", "intensity_cm_inv"])
    assert columns.q_column == "q_A_inv"
    assert columns.intensity_column == "intensity_cm_inv"
    assert columns.error_column is None
    assert columns.q_unit == "A^-1"
    assert columns.intensity_unit == "cm^-1"


def test_import_in_situ_series_natural_sorts_and_sets_metadata(tmp_path) -> None:
    _write_curve(tmp_path / "ti15_00010_abs2d_cm-1.csv", intensity=10)
    _write_curve(tmp_path / "ti15_00002_abs2d_cm-1.csv", intensity=2)
    _write_curve(tmp_path / "ti15_00001_abs2d_cm-1.csv", intensity=1)

    result = import_in_situ_series(list(tmp_path.glob("*.csv")))

    assert result.import_summary["total_files"] == 3
    assert result.import_summary["imported_count"] == 3
    assert [curve.metadata["frame_index"] for curve in result.imported_curves] == [1, 2, 10]
    assert [curve.metadata["sequence_order"] for curve in result.imported_curves] == [0, 1, 2]
    assert all(curve.error is None for curve in result.imported_curves)


def test_import_in_situ_series_keeps_successes_when_one_file_fails(tmp_path) -> None:
    _write_curve(tmp_path / "ti15_00001_abs2d_cm-1.csv", intensity=1)
    (tmp_path / "ti15_00002_abs2d_cm-1.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    result = import_in_situ_series(list(tmp_path.glob("*.csv")))

    assert len(result.imported_curves) == 1
    assert len(result.failed_files) == 1
    assert "ti15_00002" in result.failed_files[0]["file"]


def test_create_in_situ_group_and_history_record(tmp_path) -> None:
    _write_curve(tmp_path / "ti15_00001_abs2d_cm-1.csv", intensity=1)
    _write_curve(tmp_path / "ti15_00002_abs2d_cm-1.csv", intensity=2)
    result = import_in_situ_series(list(tmp_path.glob("*.csv")))
    project = ProjectState()
    group, record = create_in_situ_group(project, result)

    assert [curve.curve_id for curve in project.curves] == group.curve_ids
    assert group.metadata["group_type"] == "in_situ_series"
    assert record.action_type == "batch_import_in_situ_series"
    assert record.parameters["imported_count"] == 2
    assert project.history_records[-1].record_id == record.record_id


def test_import_in_situ_series_applies_same_q_range_to_each_file(tmp_path) -> None:
    _write_range_curve(tmp_path / "ti15_00001_abs2d_cm-1.csv", [0.005, 0.01, 0.02, 0.06])
    _write_range_curve(tmp_path / "ti15_00002_abs2d_cm-1.csv", [0.004, 0.01, 0.03, 0.07])

    result = import_in_situ_series(list(tmp_path.glob("*.csv")), limit_q_range=True, q_min=0.01, q_max=0.05)

    assert len(result.imported_curves) == 2
    assert result.failed_files == []
    assert [curve.q.tolist() for curve in result.imported_curves] == [[0.01, 0.02], [0.01, 0.03]]
    assert all(curve.metadata["import_q_range_filter"]["raw_point_count"] == 4 for curve in result.imported_curves)
    assert all(curve.metadata["import_q_range_filter"]["imported_point_count"] == 2 for curve in result.imported_curves)
    assert result.import_summary["q_range_filter_enabled"] is True
    assert result.import_summary["raw_total_points"] == 8
    assert result.import_summary["imported_total_points"] == 4
    assert result.import_summary["filtered_out_total_points"] == 4


def test_import_in_situ_series_keeps_other_files_when_q_range_filters_one_file_out(tmp_path) -> None:
    _write_range_curve(tmp_path / "ti15_00001_abs2d_cm-1.csv", [0.005, 0.01, 0.02, 0.06])
    _write_range_curve(tmp_path / "ti15_00002_abs2d_cm-1.csv", [0.10, 0.20, 0.30])

    result = import_in_situ_series(list(tmp_path.glob("*.csv")), limit_q_range=True, q_min=0.01, q_max=0.05)

    assert len(result.imported_curves) == 1
    assert len(result.failed_files) == 1
    assert "ti15_00002" in result.failed_files[0]["file"]
    assert "q range filter" in result.failed_files[0]["error"]
    assert result.import_summary["imported_count"] == 1
    assert result.import_summary["failed_count"] == 1
    assert result.import_summary["raw_total_points"] == 7
    assert result.import_summary["imported_total_points"] == 2
    assert result.import_summary["filtered_out_total_points"] == 5
    assert result.import_summary["created_curve_total_points"] == 2
    assert result.import_summary["failed_q_range_would_import_total_points"] == 0
    failed = result.failed_files[0]
    assert failed["failure_type"] == "q_range_filter_too_few_points"
    assert failed["q_range_filter_enabled"] == "True"
    assert failed["q_range_filter_min"] == "0.01"
    assert failed["q_range_filter_max"] == "0.05"
    assert failed["raw_point_count"] == "3"
    assert failed["would_import_point_count"] == "0"
    assert failed["filtered_out_point_count"] == "3"
