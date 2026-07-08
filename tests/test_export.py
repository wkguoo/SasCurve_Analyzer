from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.core import export
from app.core.data_model import CurveData
from app.core.export import export_analysis_json, export_curve_csv, export_feature_table
from app.core.model_free import invariant_measured
from app.core.project import ProjectState, load_project, save_project
from app.core.report import generate_markdown_report


def test_curve_csv_export(tmp_path) -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20], error=[1, 2])
    path = export_curve_csv(curve, tmp_path / "curve.csv")
    df = pd.read_csv(path)
    assert list(df.columns) == ["q", "I", "error"]


def test_analysis_json_export(tmp_path) -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    result = invariant_measured(curve, (0.1, 0.2))
    path = export_analysis_json(result, tmp_path / "analysis.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["analysis_type"] == "invariant_measured"


def test_feature_table_and_markdown_report_export(tmp_path) -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    result = invariant_measured(curve, (0.1, 0.2))
    feature_path = export_feature_table([curve], [result], tmp_path / "feature_table.csv")
    report_path = generate_markdown_report(
        tmp_path / "report.md",
        project_name="test",
        curves=[curve],
        analyses=[result],
        history=[],
        formal_records=[],
    )
    assert feature_path.exists()
    assert "Analysis Results" in report_path.read_text(encoding="utf-8")


def test_origin_long_export_preserves_in_situ_metadata_and_points(tmp_path) -> None:
    curves = [
        CurveData.create(
            name="ti15_00010_abs2d_cm-1",
            q=[0.2, 0.1],
            intensity=[20.0, 10.0],
            error=[2.0, 1.0],
            q_unit="A^-1",
            intensity_unit="cm^-1",
            metadata={"series_id": "ti15", "frame_index": 10, "frame_label": "00010", "sequence_order": 2, "source_stem": "ti15_00010_abs2d_cm-1"},
        ),
        CurveData.create(
            name="ti15_00001_abs2d_cm-1",
            q=[0.1, 0.2],
            intensity=[1.0, 2.0],
            q_unit="A^-1",
            intensity_unit="cm^-1",
            metadata={"series_id": "ti15", "frame_index": 1, "frame_label": "00001", "sequence_order": 0, "source_stem": "ti15_00001_abs2d_cm-1"},
        ),
        CurveData.create(
            name="ti15_00002_abs2d_cm-1",
            q=[0.1, 0.2],
            intensity=[3.0, 4.0],
            q_unit="A^-1",
            intensity_unit="cm^-1",
            metadata={"series_id": "ti15", "frame_index": 2, "frame_label": "00002", "sequence_order": 1, "source_stem": "ti15_00002_abs2d_cm-1"},
        ),
    ]

    path = export.export_origin_long_csv(curves, tmp_path / "curves_long.csv")
    table = pd.read_csv(path)

    assert list(table.columns) == ["series_id", "frame_index", "sequence_order", "curve_id", "curve_name", "source_stem", "q", "I", "error", "q_unit", "intensity_unit"]
    assert len(table) == 6
    assert table["frame_index"].tolist() == [1, 1, 2, 2, 10, 10]
    assert table["sequence_order"].tolist() == [0, 0, 1, 1, 2, 2]
    assert table["q"].tolist() == [0.1, 0.2, 0.1, 0.2, 0.1, 0.2]
    assert table["I"].tolist() == [1.0, 2.0, 3.0, 4.0, 10.0, 20.0]
    assert table["q_unit"].unique().tolist() == ["A^-1"]
    assert table["intensity_unit"].unique().tolist() == ["cm^-1"]
    assert pd.isna(table.loc[0, "error"])
    assert table.loc[4, "error"] == 1.0


def test_origin_long_export_writes_beginner_guide_markdown(tmp_path) -> None:
    curve = CurveData.create(name="sample_00001", q=[0.1, 0.2], intensity=[10.0, 5.0], error=[0.5, 0.4])

    export.export_origin_long_csv([curve], tmp_path / "curves_long.csv")
    guide_path = tmp_path / "curves_long_guide.md"

    assert guide_path.exists()
    text = guide_path.read_text(encoding="utf-8")
    for column in export.ORIGIN_LONG_COLUMNS:
        assert f"| `{column}` |" in text
    assert "log-log" in text
    assert "Guinier" in text
    assert "heatmap" in text
    assert "d = 2\u03c0/q" in text


def test_origin_matrix_export_uses_frame_columns_for_matching_q_grid(tmp_path) -> None:
    curves = [
        CurveData.create(name="ti15_00001", q=[0.1, 0.2], intensity=[1.0, 2.0], metadata={"frame_label": "00001", "sequence_order": 0}),
        CurveData.create(name="ti15_00002", q=[0.1, 0.2], intensity=[3.0, 4.0], metadata={"frame_label": "00002", "sequence_order": 1}),
    ]

    path, warnings = export.export_origin_matrix_csv(curves, tmp_path / "curves_matrix.csv")
    table = pd.read_csv(path)

    assert warnings == []
    assert list(table.columns) == ["q", "frame_00001", "frame_00002"]
    assert table["q"].tolist() == [0.1, 0.2]
    assert table["frame_00001"].tolist() == [1.0, 2.0]
    assert table["frame_00002"].tolist() == [3.0, 4.0]


def test_origin_matrix_export_sorts_q_without_mutating_curves(tmp_path) -> None:
    first = CurveData.create(name="ti15_00001", q=[0.3, 0.1, 0.2], intensity=[30.0, 10.0, 20.0], metadata={"frame_label": "00001"})
    second = CurveData.create(name="ti15_00002", q=[0.1, 0.2, 0.3], intensity=[11.0, 22.0, 33.0], metadata={"frame_label": "00002"})
    original_q = first.q.copy()
    original_intensity = first.intensity.copy()

    path, warnings = export.export_origin_matrix_csv([first, second], tmp_path / "curves_matrix.csv")
    table = pd.read_csv(path)

    assert warnings == []
    assert table["q"].tolist() == [0.1, 0.2, 0.3]
    assert table["frame_00001"].tolist() == [10.0, 20.0, 30.0]
    assert table["frame_00002"].tolist() == [11.0, 22.0, 33.0]
    assert (first.q == original_q).all()
    assert (first.intensity == original_intensity).all()


def test_origin_matrix_export_warns_and_skips_mismatched_q_grid(tmp_path) -> None:
    curves = [
        CurveData.create(name="ti15_00001", q=[0.1, 0.2], intensity=[1.0, 2.0], metadata={"frame_label": "00001", "sequence_order": 0}),
        CurveData.create(name="ti15_00002", q=[0.1, 0.25], intensity=[3.0, 4.0], metadata={"frame_label": "00002", "sequence_order": 1}),
    ]

    path, warnings = export.export_origin_matrix_csv(curves, tmp_path / "curves_matrix.csv")

    assert path is None
    assert any("q grids differ" in warning for warning in warnings)
    assert not (tmp_path / "curves_matrix.csv").exists()


def test_first_hand_transform_table_preserves_rows_and_uses_user_visible_headers() -> None:
    curve = CurveData.create(name="mixed", q=[0.1, 0.2, -0.3, 0.4], intensity=[10.0, 20.0, 30.0, -40.0])

    table = export.build_first_hand_transform_table(curve)

    assert list(table.columns) == [
        "q",
        "I(q)",
        "q²",
        "ln q",
        "log10 q",
        "ln I(q)",
        "log10 I(q)",
        "q²I(q)",
        "q⁴I(q)",
        "qI(q)",
        "q³I(q)",
        "d = 2π/q",
    ]
    assert len(table) == 4
    np.testing.assert_allclose(table["q"], [0.1, 0.2, -0.3, 0.4])
    np.testing.assert_allclose(table["I(q)"], [10.0, 20.0, 30.0, -40.0])
    np.testing.assert_allclose(table["q²"], [0.01, 0.04, 0.09, 0.16])
    np.testing.assert_allclose(table["q²I(q)"], [0.1, 0.8, 2.7, -6.4])
    np.testing.assert_allclose(table["q⁴I(q)"], [0.001, 0.032, 0.243, -1.024])
    assert pd.isna(table.loc[2, "ln q"])
    assert pd.isna(table.loc[2, "log10 q"])
    assert pd.isna(table.loc[3, "ln I(q)"])
    assert pd.isna(table.loc[3, "log10 I(q)"])
    header_text = "\n".join(table.columns)
    for old_formula in ["q^2", "q^4", "2*pi", "alpha(q)"]:
        assert old_formula not in header_text


def test_export_first_hand_transform_csv_writes_numeric_wide_table(tmp_path) -> None:
    curve = CurveData.create(name="mixed", q=[0.1, 0.2, -0.3, 0.4], intensity=[10.0, 20.0, 30.0, -40.0])

    path = export.export_first_hand_transform_csv(curve, tmp_path / "mixed_transformed_data.csv")
    table = pd.read_csv(path, encoding="utf-8-sig")

    assert path.exists()
    assert len(table) == 4
    assert pd.api.types.is_numeric_dtype(table["q"])
    assert pd.api.types.is_numeric_dtype(table["I(q)"])
    assert pd.api.types.is_numeric_dtype(table["q²I(q)"])
    np.testing.assert_allclose(table["q²I(q)"], [0.1, 0.8, 2.7, -6.4])
    assert pd.isna(table.loc[2, "ln q"])
    assert pd.isna(table.loc[3, "ln I(q)"])


def test_removed_export_entry_functions_are_not_public_core_api() -> None:
    for removed_name in [
        "export_curve_derived_csv",
        "export_curves_derived_long_csv",
        "export_curves_derived_matrix_csv",
        "export_analysis_bundle",
        "export_plot_analysis_summary_csv",
        "export_plot_analysis_results_json",
        "export_plot_analysis_residual_tables",
    ]:
        assert not hasattr(export, removed_name)


def test_project_save_and_load(tmp_path) -> None:
    project = ProjectState()
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    project.add_curve(curve)
    save_project(project, tmp_path)
    loaded = load_project(tmp_path)
    assert len(loaded.curves) == 1
    assert loaded.curves[0].name == "curve"

