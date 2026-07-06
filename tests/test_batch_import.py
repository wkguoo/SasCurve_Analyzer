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
