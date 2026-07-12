import json
import zipfile

import pandas as pd
import pytest

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchRun, ParameterValue
from app.core.batch_cache import load_run_checkpoint, save_run_checkpoint
from app.core.result_package import (
    _json_default,
    _reliable_parameter_rows,
    export_details_archive,
    export_result_package,
    export_result_package_from_checkpoint,
)
from scripts.analyze_ti15_first10 import build_full_audit_zip


def test_json_default_serializes_multi_element_numpy_arrays() -> None:
    import numpy as np

    assert _json_default(np.array([1.0, 2.0])) == [1.0, 2.0]


@pytest.mark.parametrize(
    ("parameter_status", "reliability_score"),
    [
        (AnalysisStatus.INVALID, 0.8),
        (AnalysisStatus.SUCCESS, None),
    ],
)
def test_reliable_parameters_reject_invalid_parameters_and_missing_scores(
    parameter_status: AnalysisStatus,
    reliability_score: float | None,
) -> None:
    run = AutoBatchRun(batch_id="reliable-gate")
    run.analyses = [
        AnalysisEnvelope(
            curve_id="c1",
            curve_name="curve",
            analysis_id="c1:test",
            analysis_type="test",
            status=AnalysisStatus.SUCCESS,
            q_range=(0.01, 0.02),
            parameters=[ParameterValue("value", 123.0, status=parameter_status)],
            reliability_label="medium",
            reliability_score=reliability_score,
        )
    ]

    assert _reliable_parameter_rows(run) == []


@pytest.mark.parametrize("value", [{"radius": 12.3}, ["radius"], float("nan"), float("inf")])
def test_reliable_parameters_reject_non_scalar_and_non_finite_values(value: object) -> None:
    run = AutoBatchRun(batch_id="reliable-scalars")
    run.analyses = [
        AnalysisEnvelope(
            curve_id="c1",
            curve_name="curve",
            analysis_id="c1:test",
            analysis_type="test",
            status=AnalysisStatus.SUCCESS,
            q_range=(0.01, 0.02),
            parameters=[ParameterValue("value", value, status=AnalysisStatus.SUCCESS)],
            reliability_label="medium",
            reliability_score=0.8,
        )
    ]

    assert _reliable_parameter_rows(run) == []


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


def test_slim_result_package_keeps_only_nonempty_effective_q_invariant_tables(tmp_path) -> None:
    run = _run()
    run.config_snapshot = {"effective_q_range": (0.01, 0.05)}
    run.analyses[0].q_range = (0.01, 0.05)
    run.analyses[0].tables = {
        "derived_coordinates": [
            {"q": 0.01, "q2I": 1.0},
            {"q": 0.2, "q2I": 2.0},
        ],
        "invariant_integrand": [
            {"q": 0.01, "q_squared_I": 1.0},
            {"q": 0.05, "q_squared_I": 2.0},
        ],
        "crossovers": [],
    }

    target = export_result_package(run, tmp_path / "slim_results", detail_level="slim")

    index = pd.read_csv(target / "audit" / "analysis_tables_index.csv")
    assert index["table_name"].tolist() == ["invariant_integrand"]
    assert index.loc[0, "row_count"] == 2
    detail_files = list((target / "details" / "analysis_tables").glob("*.csv"))
    assert len(detail_files) == 1
    assert not list((target / "details" / "analysis_tables").glob("*derived_coordinates*"))


def test_details_archive_keeps_all_tables_but_filters_q_rows(tmp_path) -> None:
    run = _run()
    run.config_snapshot = {"effective_q_range": (0.01, 0.05)}
    run.analyses[0].tables = {
        "derived_coordinates": [
            {"q": 0.01, "value": 1.0},
            {"q": 0.20, "value": 2.0},
        ],
        "crossovers": [],
    }

    archive_path = export_details_archive(run, tmp_path / "details_full.zip")

    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(archive.namelist())
        assert "README_details_full.md" in names
        assert "details_index.csv" in names
        detail_name = next(name for name in names if name.endswith("derived_coordinates.csv"))
        assert len(pd.read_csv(archive.open(detail_name))) == 1
        crossover_name = next(name for name in names if name.endswith("crossovers.csv"))
        crossover = pd.read_csv(archive.open(crossover_name))
        assert crossover.empty
        assert crossover.columns.tolist() == [
            "crossover_q",
            "crossover_d",
            "slope_difference",
            "confidence",
        ]


def test_audit_archive_does_not_nest_detail_archive(tmp_path) -> None:
    run = _run()
    run.config_snapshot = {"effective_q_range": (0.01, 0.05)}
    run.analyses[0].tables = {
        "invariant_integrand": [{"q": 0.01, "value": 1.0}],
    }
    exported = export_result_package(run, tmp_path / "result", detail_level="slim")

    detail_zip, audit_zip = build_full_audit_zip(run, exported)

    assert detail_zip.exists()
    with zipfile.ZipFile(audit_zip) as archive:
        assert "details_full.zip" not in archive.namelist()
        assert "audit/fit_quality.csv" in archive.namelist()


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
