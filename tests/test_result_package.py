import json

import pandas as pd
import pytest

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchRun, ParameterValue
from app.core.result_package import export_result_package


def _run() -> AutoBatchRun:
    run = AutoBatchRun(batch_id="demo", status="completed")
    run.analyses = [
        AnalysisEnvelope(
            "c1",
            "frame_001",
            "c1:guinier",
            "guinier",
            AnalysisStatus.SUCCESS,
            (0.01, 0.03),
            parameters=[ParameterValue("Rg", 12.3, "nm")],
            fit_quality={"R2": 0.99},
            tables={"residuals": [{"q": 0.01, "residual": 0.1}]},
        )
    ]
    run.rankings = [{"model_name": "sphere", "coverage": 1.0}]
    run.sequence_results = {
        "frame_table": [{"frame": 0, "curve_id": "c1"}],
        "parameter_trajectories": [],
        "reference_comparisons": [],
        "change_flags": [],
        "linear_trends": [],
        "exploratory_statistics": {"status": "not_enabled"},
    }
    return run


def test_result_package_exports_summary_tables_and_details(tmp_path) -> None:
    target = export_result_package(_run(), tmp_path / "demo_results")
    assert json.loads((target / "run_summary.json").read_text(encoding="utf-8"))["batch_id"] == "demo"
    assert pd.read_csv(target / "parameters.csv").loc[0, "name"] == "Rg"
    assert pd.read_csv(target / "fit_quality.csv").loc[0, "R2"] == pytest.approx(0.99)
    index = pd.read_csv(target / "analysis_tables_index.csv")
    assert (target / index.loc[0, "file"]).exists()
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "不能证明" in readme
    assert "科研解释限制" in readme


def test_result_package_refuses_existing_target(tmp_path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_result_package(_run(), target)
    assert marker.read_text(encoding="utf-8") == "keep"


def test_cancelled_result_package_is_explicitly_incomplete(tmp_path) -> None:
    run = _run()
    run.status = "cancelled"

    target = export_result_package(run, tmp_path / "demo_results")

    assert target.name == "demo_results_incomplete"
    assert target.is_dir()
    assert not (tmp_path / "demo_results").exists()
