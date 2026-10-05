import json

import numpy as np

from app.core.auto_batch_schema import AutoBatchRun
from app.core.batch_import import import_in_situ_series
from app.core.import_preview import preview_curve_file
from app.core.io import load_curve
from app.core.result_package import export_result_package


def test_beamline_mean_std_headers_import_without_measured_errors(tmp_path):
    path = tmp_path / "sample_002.csv"
    path.write_text("q_nm_inv,mean_intensity,std_intensity,n_frames\n0.1,10,0.5,20\n0.2,8,0.4,20\n0.3,-1,0.3,20\n", encoding="utf-8")
    before = path.read_bytes()
    preview = preview_curve_file(path)
    assert preview.can_import
    assert preview.diagnostics["uncertainty_kind"] == "series_std"
    result = import_in_situ_series([path], target_q_unit="A^-1")
    assert not result.failed_files
    curve = result.imported_curves[0]
    np.testing.assert_allclose(curve.q, [0.01, 0.02, 0.03])
    np.testing.assert_allclose(curve.intensity, [10, 8, -1])
    assert curve.error is None
    assert curve.metadata["uncertainty_kind"] == "series_std"
    assert curve.metadata["non_measurement_error"]["values"] == [0.5, 0.4, 0.3]
    run = AutoBatchRun(batch_id="series", status="completed", curves=[curve])
    target = export_result_package(run, tmp_path / "package")
    import pandas as pd
    index = pd.read_csv(target / "audit/input_uncertainties_index.csv")
    table = pd.read_csv(target / index.iloc[0]["file"])
    np.testing.assert_allclose(table["q"], curve.q)
    np.testing.assert_allclose(table["value"], [0.5, 0.4, 0.3])
    assert table["q_unit"].tolist() == ["A^-1"] * 3
    assert path.read_bytes() == before


def test_explicit_series_std_column_is_not_a_sigma(tmp_path):
    path = tmp_path / "explicit.csv"
    path.write_text("q,I,std_intensity\n0.01,10,0.5\n0.02,8,0.4\n", encoding="utf-8")
    curve = load_curve(path, error_column="std_intensity")
    assert curve.error is None
    assert curve.metadata["uncertainty_kind"] == "series_std"


def test_result_summary_retains_units_and_source_processing_metadata(tmp_path):
    path = tmp_path / "measured.csv"
    path.write_text("q,I,error\n0.01,10,0.5\n0.02,8,0.4\n", encoding="utf-8")
    curve = load_curve(path, error_column="error", metadata={"sample_id": "sample #1", "processing_branch": "native_1d", "acquisition_time": "2026-10-01T01:02:03Z"})
    run = AutoBatchRun(batch_id="contract", status="completed", curves=[curve])
    target = export_result_package(run, tmp_path / "package")
    row = json.loads((target / "summary/run_summary.json").read_text(encoding="utf-8"))["curves"][0]
    assert row["metadata"]["processing_branch"] == "native_1d"
    assert row["metadata"]["uncertainty_kind"] == "measurement"
    assert row["metadata"]["sample_id"] == "sample #1"


def test_unknown_std_is_preserved_and_filter_keeps_q_value_alignment(tmp_path):
    path = tmp_path / "sample_002.csv"
    path.write_text("q_nm_inv,I,std\n0.1,10,0.5\n0.2,8,0.4\n0.3,6,0.3\n", encoding="utf-8")
    result = import_in_situ_series([path], target_q_unit="A^-1", limit_q_range=True, q_min=0.015, q_max=0.035)
    curve = result.imported_curves[0]
    assert curve.error is None
    assert curve.metadata["uncertainty_kind"] == "unknown"
    np.testing.assert_allclose(curve.q, [0.02, 0.03])
    assert curve.metadata["non_measurement_error"]["values"] == [0.4, 0.3]


def test_declared_pointwise_uncertainty_override_is_retained(tmp_path):
    path = tmp_path / "explicit.csv"
    path.write_text("q,I,std\n0.01,10,0.5\n0.02,8,0.4\n", encoding="utf-8")
    curve = load_curve(path, error_column="std", metadata={"uncertainty_kind": "measurement"})
    np.testing.assert_allclose(curve.error, [0.5, 0.4])


def test_method_tables_bind_window_to_curve_units_and_uncertainty(tmp_path):
    from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, ParameterValue
    import pandas as pd

    path = tmp_path / "measured.csv"
    path.write_text("q,I,error\n0.01,10,0.5\n0.02,8,0.4\n", encoding="utf-8")
    curve = load_curve(path, error_column="error", q_unit="nm^-1", metadata={"processing_branch": "native"})
    envelope = AnalysisEnvelope(curve.curve_id, curve.name, "fit", "guinier", AnalysisStatus.SUCCESS, (0.01, 0.02),
                                parameters=[ParameterValue("Rg", 2.0, "nm")],
                                tables={"residuals": [{"q": 0.01, "residual": 0.1}]})
    run = AutoBatchRun(batch_id="method", status="completed", curves=[curve], analyses=[envelope])
    target = export_result_package(run, tmp_path / "package")
    for name in ("parameters", "fit_quality", "analysis_tables_index"):
        table = pd.read_csv(target / f"audit/{name}.csv")
        assert table.iloc[0]["q_unit"] == "nm^-1"
        assert table.iloc[0]["uncertainty_kind"] == "measurement"
        assert table.iloc[0]["processing_branch"] == "native"
