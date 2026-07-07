from __future__ import annotations

from app.core.import_preview import format_import_preview, preview_curve_file


def test_import_preview_ok_for_normal_csv(tmp_path) -> None:
    path = tmp_path / "curve.csv"
    path.write_text("q_A_inv,intensity_cm_inv,error\n0.1,10,0.2\n0.2,5,0.1\n", encoding="utf-8")

    preview = preview_curve_file(path)

    assert preview.status == "ok"
    assert preview.can_import
    assert preview.q_column == "q_A_inv"
    assert preview.intensity_column == "intensity_cm_inv"
    assert preview.error_column == "error"
    assert preview.diagnostics["q_min"] == 0.1
    assert preview.diagnostics["q_max"] == 0.2
    assert "OK" in format_import_preview(preview)


def test_import_preview_reports_missing_required_columns(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("x,y\n1,2\n", encoding="utf-8")

    preview = preview_curve_file(path)

    assert preview.status == "error"
    assert not preview.can_import
    assert any("无法导入" in message for message in preview.messages)


def test_import_preview_warns_for_nan_duplicates_negative_intensity_and_error(tmp_path) -> None:
    path = tmp_path / "warn.csv"
    path.write_text(
        "q,I,error\n"
        "0.2,10,0.1\n"
        "0.1,-1,-0.2\n"
        "0.1,NaN,NaN\n"
        "0.0,5,0.3\n",
        encoding="utf-8",
    )

    preview = preview_curve_file(path, q_column="q", intensity_column="I", error_column="error")

    assert preview.status == "warning"
    assert preview.can_import
    assert preview.diagnostics["q_duplicate_count"] == 1
    assert preview.diagnostics["q_non_positive_count"] == 1
    assert preview.diagnostics["intensity_negative_count"] == 1
    assert preview.diagnostics["error_negative_count"] == 1
    assert any("重复 q" in message for message in preview.messages)
    assert any("I(q) <= 0" in message for message in preview.messages)


def test_import_preview_uses_explicit_units_when_columns_are_manual(tmp_path) -> None:
    path = tmp_path / "manual.csv"
    path.write_text("angle,signal\n0.1,10\n0.2,5\n", encoding="utf-8")

    preview = preview_curve_file(
        path,
        q_column="angle",
        intensity_column="signal",
        q_unit="nm^-1",
        intensity_unit="counts",
    )

    assert preview.status == "ok"
    assert preview.q_unit == "nm^-1"
    assert preview.intensity_unit == "counts"
    assert preview.diagnostics["q_unit"] == "nm^-1"
    assert preview.diagnostics["intensity_unit"] == "counts"


def test_import_preview_infers_units_when_units_not_explicit(tmp_path) -> None:
    path = tmp_path / "inferred.csv"
    path.write_text("q_nm_inv,intensity_cm_inv\n0.1,10\n0.2,5\n", encoding="utf-8")

    preview = preview_curve_file(path)

    assert preview.status == "ok"
    assert preview.q_unit == "nm^-1"
    assert preview.intensity_unit == "cm^-1"


def test_import_preview_errors_for_empty_file(tmp_path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("# only comment\n", encoding="utf-8")

    preview = preview_curve_file(path)

    assert preview.status == "error"
    assert not preview.can_import
    assert any("无法读取表格数据" in message for message in preview.messages)
