from __future__ import annotations

import json

import pandas as pd

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


def test_project_save_and_load(tmp_path) -> None:
    project = ProjectState()
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    project.add_curve(curve)
    save_project(project, tmp_path)
    loaded = load_project(tmp_path)
    assert len(loaded.curves) == 1
    assert loaded.curves[0].name == "curve"

