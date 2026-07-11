import json

import pandas as pd
import pytest

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchRun, ParameterValue
from app.core.batch_cache import load_run_checkpoint, save_run_checkpoint
from app.core.result_package import _json_default, export_result_package, export_result_package_from_checkpoint


def test_json_default_serializes_multi_element_numpy_arrays() -> None:
    import numpy as np

    assert _json_default(np.array([1.0, 2.0])) == [1.0, 2.0]


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
            reliability_label="medium",
            reliability_score=0.8,
        ),
        AnalysisEnvelope(
            "c1",
            "frame_001",
            "c1:porod",
            "porod",
            AnalysisStatus.MISSING_PREREQUISITE,
            None,
            parameters=[ParameterValue("alpha", None, "")],
            tables={"noise": [{"q": 0.5, "value": 1.0}]},
            reliability_label="invalid",
            reliability_score=0.0,
        ),
    ]
    run.rankings = [{"model_name": "sphere", "coverage": 1.0, "eligible_for_main_model": True}]
    run.main_model = "sphere"
    run.sequence_results = {
        "frame_table": [{"frame": 0, "curve_id": "c1"}],
        "parameter_trajectories": [],
        "reference_comparisons": [],
        "change_flags": [],
        "linear_trends": [],
        "exploratory_statistics": {"status": "not_enabled"},
    }
    return run


def test_result_package_exports_tiered_summary_tables_and_details(tmp_path) -> None:
    target = export_result_package(_run(), tmp_path / "demo_results")
    assert json.loads((target / "summary" / "run_summary.json").read_text(encoding="utf-8"))["batch_id"] == "demo"
    assert pd.read_csv(target / "audit" / "parameters.csv").loc[0, "name"] == "Rg"
    assert pd.read_csv(target / "audit" / "fit_quality.csv").loc[0, "R2"] == pytest.approx(0.99)
    assert pd.read_csv(target / "summary" / "reliable_parameters.csv").loc[0, "name"] == "Rg"
    index = pd.read_csv(target / "audit" / "analysis_tables_index.csv")
    assert len(index) == 1
    assert "guinier" in index.loc[0, "file"]
    assert (target / index.loc[0, "file"]).exists()
    # missing_prerequisite tables are omitted at default detail_level=usable
    detail_files = list((target / "details" / "analysis_tables").glob("*.csv"))
    assert len(detail_files) == 1
    assert not list((target / "details" / "analysis_tables").glob("*porod*"))
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "summary/" in readme
    assert "不能证明" in readme
    assert "科研解释限制" in readme
    assert (target / "summary" / "sequence_frame_table.csv").exists()
    assert not (target / "audit" / "sequence_linear_trends.csv").exists()


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


def test_run_summary_omits_curve_arrays_and_table_bodies(tmp_path) -> None:
    import numpy as np

    from app.core.data_model import CurveData

    q = np.linspace(0.01, 1.0, 4000)
    intensity = np.exp(-q * 3.0)
    curve = CurveData.create(name="long_curve", q=q, intensity=intensity)
    run = _run()
    run.curves = [curve]
    run.analyses[0].tables = {
        "residuals": [{"q": float(x), "residual": 0.01} for x in q[:500]],
    }

    target = export_result_package(run, tmp_path / "slim_results")
    summary = json.loads((target / "summary" / "run_summary.json").read_text(encoding="utf-8"))
    text = (target / "summary" / "run_summary.json").read_text(encoding="utf-8")

    assert "q" not in summary["curves"][0]
    assert "intensity" not in summary["curves"][0]
    assert summary["curves"][0]["n_points"] == 4000
    assert summary["curves"][0]["name"] == "long_curve"
    assert summary["analyses"][0]["tables"]["residuals"] == {"row_count": 500}
    assert summary["analyses"][0]["tables_exported"] is True
    assert len(text) < 200_000
    assert "不含完整 q/I" in (target / "README.md").read_text(encoding="utf-8") or "summary" in (
        target / "README.md"
    ).read_text(encoding="utf-8")


def test_export_from_checkpoint_without_recompute(tmp_path) -> None:
    run = _run()
    cache = tmp_path / "cache"
    save_run_checkpoint(cache, run)
    restored = load_run_checkpoint(cache)
    assert restored.batch_id == "demo"
    assert len(restored.analyses) == 2

    target = export_result_package_from_checkpoint(cache, tmp_path / "from_cache")
    assert (target / "summary" / "run_summary.json").exists()
    assert pd.read_csv(target / "audit" / "parameters.csv").loc[0, "name"] == "Rg"
