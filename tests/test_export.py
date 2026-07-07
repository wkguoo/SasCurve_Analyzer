from __future__ import annotations

import json

import pandas as pd

from app.core import export
from app.core.data_model import CurveData
from app.core.export import export_analysis_json, export_curve_csv, export_feature_table
from app.core.model_fitting import fit_shape_model
from app.core.model_free import invariant_measured
from app.core.project import ProjectState, load_project, save_project
from app.core.report import generate_markdown_report
from app.core.settings import AppSettings
from app.core.shape_models import sphere_model


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


def test_export_summary_includes_curve_units_parameters_and_fit_parameter_table(tmp_path) -> None:
    q = pd.Series([0.003, 0.01, 0.02, 0.04, 0.08], dtype=float)
    q_values = q.to_numpy()
    curve = CurveData.create(
        name="sphere",
        q=q_values,
        intensity=sphere_model(q_values, 35.0, 120.0, 2.0),
        q_unit="A^-1",
        intensity_unit="cm^-1",
    )
    result = fit_shape_model(curve, (float(q_values.min()), float(q_values.max())), "sphere", initial_parameters={"radius": 34.0})

    feature_path = export_feature_table([curve], [result], tmp_path / "feature_table.csv")
    outputs = export.export_analysis_bundle([curve], [result], tmp_path / "bundle")
    report_path = generate_markdown_report(
        tmp_path / "report.md",
        project_name="test",
        curves=[curve],
        analyses=[result],
        history=[],
        formal_records=[],
    )

    feature_table = pd.read_csv(feature_path)
    summary_table = pd.read_csv(outputs["analysis_summary"])
    parameter_table = pd.read_csv(outputs["fit_parameters"])
    report_text = report_path.read_text(encoding="utf-8")

    assert feature_table.loc[0, "q_unit"] == "A^-1"
    assert feature_table.loc[0, "intensity_unit"] == "cm^-1"
    assert "parameters_json" in summary_table.columns
    assert summary_table.loc[0, "curve_name"] == "sphere"
    assert summary_table.loc[0, "q_unit"] == "A^-1"
    assert "initial_parameters" in summary_table.loc[0, "parameters_json"]
    assert {"analysis_id", "curve_id", "parameter", "value", "stderr", "unit"}.issubset(parameter_table.columns)
    assert parameter_table.loc[parameter_table["parameter"] == "radius", "unit"].iloc[0] == "1/q"
    assert "- parameters:" in report_text
    assert "radius" in report_text
    assert "1/q" in report_text


def test_analysis_bundle_writes_reproducibility_manifest_readme_settings_and_warnings(tmp_path) -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20], q_unit="A^-1", intensity_unit="cm^-1")
    result = invariant_measured(curve, (0.1, 0.2))
    settings = AppSettings(default_q_unit="A^-1", default_export_dir="exports")

    outputs = export.export_analysis_bundle([curve], [result], tmp_path / "bundle", project_name="test_project", settings=settings)

    assert outputs["manifest"].exists()
    assert outputs["README_export"].exists()
    assert outputs["settings_snapshot"].exists()
    assert outputs["bundle_warnings"].exists()

    manifest = json.loads(outputs["manifest"].read_text(encoding="utf-8"))
    settings_payload = json.loads(outputs["settings_snapshot"].read_text(encoding="utf-8"))
    readme = outputs["README_export"].read_text(encoding="utf-8")
    warnings = outputs["bundle_warnings"].read_text(encoding="utf-8")

    assert manifest["software"]["name"] == "SAS Curve Analyzer"
    assert manifest["project"]["name"] == "test_project"
    assert manifest["project"]["curve_count"] == 1
    assert manifest["project"]["analysis_count"] == 1
    assert manifest["inputs"][0]["curve_name"] == "curve"
    assert manifest["analyses"][0]["analysis_type"] == result.analysis_type
    assert manifest["settings_snapshot"] == "settings_snapshot.json"
    assert "manifest" in manifest["outputs"]
    assert settings_payload["default_q_unit"] == "A^-1"
    assert "does not modify original experimental data" in readme
    assert "No bundle-level warnings" in warnings


def test_project_save_and_load(tmp_path) -> None:
    project = ProjectState()
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    project.add_curve(curve)
    save_project(project, tmp_path)
    loaded = load_project(tmp_path)
    assert len(loaded.curves) == 1
    assert loaded.curves[0].name == "curve"

