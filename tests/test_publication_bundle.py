from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchRun, ParameterValue
from app.core.data_model import CurveData
from app.core.plotting import create_curve_figure
from app.core.publication_bundle import export_publication_bundle


def _curve(
    frame: int,
    *,
    q: list[float] | None = None,
    intensity: list[float] | None = None,
    error: list[float] | None = None,
    source_file: Path | None = None,
    q_unit: str = "A^-1",
    intensity_unit: str = "a.u.",
) -> CurveData:
    return CurveData.create(
        name=f"sample_{frame:03d}",
        q=q or [0.01, 0.02, 0.03],
        intensity=intensity or [10.0, 5.0, 2.0],
        error=error,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        source_file=source_file,
        metadata={
            "sample_id": "sample-A",
            "series_id": "sample-A",
            "frame_index": frame,
            "frame_label": f"{frame:03d}",
            "sequence_order": frame - 1,
            "source_relative_path": f"raw/sample_{frame:03d}.csv",
        },
    )


def _envelope(
    curve: CurveData,
    *,
    value: float | None,
    status: AnalysisStatus = AnalysisStatus.SUCCESS,
    analysis_type: str = "guinier",
    analysis_id: str | None = None,
    parameter_name: str = "Rg",
    unit: str = "A",
    reliability_status: str = "reliable",
    reporting_status: str = "reportable",
    tables: dict | None = None,
    parameters: list[ParameterValue] | None = None,
) -> AnalysisEnvelope:
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=analysis_id or f"{curve.curve_id}:{analysis_type}",
        analysis_type=analysis_type,
        status=status,
        q_range=(0.01, 0.03),
        parameters=parameters or [
            ParameterValue(parameter_name, value, unit, status=status, invalid_reason=None if value is not None else "fit failed")
        ],
        tables=tables or {},
        reliability_label="medium" if reliability_status != "invalid" else "invalid",
        reliability_score=0.9 if reliability_status == "reliable" else 0.0,
        reliability_status=reliability_status,
        reporting_status=reporting_status,
    )


def _export(run: AutoBatchRun, destination: Path) -> Path:
    return export_publication_bundle(run, destination, formats=("png",), dpi=40, max_overlay_curves=2)


def test_plot_source_matches_application_transformed_coordinates_and_keeps_error_absence(tmp_path: Path) -> None:
    curve = _curve(
        1,
        q=[-0.1, 0.0, 0.1, 0.2, 0.3],
        intensity=[10.0, 8.0, 4.0, 0.0, -1.0],
        error=None,
    )
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve])

    target = _export(run, tmp_path / "bundle")
    index = pd.read_csv(target / "figures" / "figure_index.csv")
    source = index[(index["view"] == "semilog") & (index["figure_kind"] == "sample_overview")].iloc[0]
    exported = pd.read_csv(target / source["source_csv"])
    actual, _ = create_curve_figure(curve, plot_type="semilog", show_error=True)
    plotted = actual.axes[0].lines[0]

    np.testing.assert_allclose(exported["x"], plotted.get_xdata())
    np.testing.assert_allclose(exported["y"], plotted.get_ydata())
    assert exported["q"].tolist() == [-0.1, 0.0, 0.1]
    assert exported["error"].isna().all()
    assert exported["yerr"].isna().all()
    assert set(exported["analysis_status"]) == {"raw_curve"}

    loglog = index[(index["view"] == "loglog") & (index["figure_kind"] == "sample_overview")].iloc[0]
    log_data = pd.read_csv(target / loglog["source_csv"])
    assert log_data["q"].tolist() == [0.1]
    assert log_data["I"].tolist() == [4.0]
    assert "I(q) <= 0" in str(loglog["warnings"])
    assert "q <= 0" in str(loglog["warnings"])


def test_matrix_is_skipped_for_varying_q_grids_and_raw_inputs_are_hash_verified(tmp_path: Path) -> None:
    raw_a = tmp_path / "raw_a" / "frame.csv"
    raw_b = tmp_path / "raw_b" / "frame.csv"
    raw_a.parent.mkdir()
    raw_b.parent.mkdir()
    raw_a.write_bytes(b"q,I\n0.01,10\n0.02,5\n")
    raw_b.write_bytes(b"q,I\n0.01,8\n0.03,4\n")
    a, b = _curve(1, q=[0.01, 0.02], intensity=[10, 5], source_file=raw_a), _curve(2, q=[0.01, 0.03], intensity=[8, 4], source_file=raw_b)
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[a, b])
    run.input_manifest = [
        {"source_file": "frame.csv", "source_relative_path": "one/frame.csv", "source_path": str(raw_a), "sha256": hashlib.sha256(raw_a.read_bytes()).hexdigest(), "manifest_status": "success"},
        {"source_file": "frame.csv", "source_relative_path": "two/frame.csv", "source_path": str(raw_b), "sha256": hashlib.sha256(raw_b.read_bytes()).hexdigest(), "manifest_status": "success"},
    ]

    target = _export(run, tmp_path / "bundle")

    matrix = json.loads((target / "data" / "matrix_status.json").read_text(encoding="utf-8"))
    assert matrix["included"] is False
    assert "not exactly equal" in matrix["reason"]
    assert not (target / "data" / "curves_matrix.csv").exists()
    source_index = pd.read_csv(target / "data" / "source_inputs" / "source_input_index.csv")
    assert source_index["archive_path"].nunique() == 2
    assert set(source_index["copy_status"]) == {"verified"}
    for row in source_index.to_dict(orient="records"):
        archived = target / "data" / row["archive_path"]
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == row["sha256"]
    assert raw_a.read_bytes() == b"q,I\n0.01,10\n0.02,5\n"


def test_evolution_keeps_failed_metrics_and_reliable_trajectory_gaps(tmp_path: Path) -> None:
    curves = [_curve(frame) for frame in (1, 2, 3)]
    envelopes = [
        _envelope(curves[0], value=10.0),
        _envelope(
            curves[1], value=None, status=AnalysisStatus.FIT_FAILED,
            reliability_status="invalid", reporting_status="not_reportable",
        ),
        _envelope(curves[2], value=14.0),
    ]
    run = AutoBatchRun(batch_id="sample-A", status="partial_success", curves=curves, analyses=envelopes)

    target = _export(run, tmp_path / "bundle")
    evolution = pd.read_csv(target / "data" / "analysis_evolution.csv")
    rg_rows = evolution[evolution["parameter_name"] == "Rg"].sort_values("frame_index")
    assert rg_rows["value"].tolist()[0] == 10.0
    assert pd.isna(rg_rows["value"].tolist()[1])
    assert rg_rows["envelope_status"].tolist() == ["success", "fit_failed", "success"]
    assert rg_rows["reliable_reportable"].tolist() == [True, False, True]

    index = pd.read_csv(target / "figures" / "figure_index.csv")
    trajectory = index[index["figure_kind"] == "reliable_parameter_evolution"].iloc[0]
    source = pd.read_csv(target / trajectory["source_csv"])
    assert source["x"].tolist() == [1.0, 2.0, 3.0]
    np.testing.assert_allclose(source["y"].to_numpy(), [10.0, np.nan, 14.0], equal_nan=True)
    assert source["analysis_status"].tolist() == ["success", "fit_failed", "success"]


def test_shape_model_parameter_records_remain_separate_by_model(tmp_path: Path) -> None:
    curve = _curve(1)
    envelopes = [
        _envelope(
            curve,
            value=None,
            analysis_type="shape_models",
            analysis_id=f"{curve.curve_id}:shape_models:sphere",
            tables={"parameter_records": [{"name": "radius", "value": 8.0, "unit": "A"}]},
            parameters=[],
        ),
        _envelope(
            curve,
            value=None,
            analysis_type="shape_models",
            analysis_id=f"{curve.curve_id}:shape_models:cylinder",
            tables={"parameter_records": [{"name": "radius", "value": 12.0, "unit": "A"}]},
            parameters=[],
        ),
    ]
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve], analyses=envelopes)

    target = _export(run, tmp_path / "bundle")

    evolution = pd.read_csv(target / "data" / "analysis_evolution.csv")
    radius = evolution[evolution["parameter_name"] == "radius"]
    assert radius.set_index("model_name")["value"].to_dict() == {"cylinder": 12.0, "sphere": 8.0}
    model_table = pd.read_csv(target / "data" / "model_parameter_records.csv")
    assert model_table["model_name"].tolist() == ["sphere", "cylinder"]


def test_dimensionless_kratky_requires_reliable_reportable_positive_compatible_pair(tmp_path: Path) -> None:
    curve = _curve(1, q_unit="A^-1", intensity_unit="a.u.")
    envelope = _envelope(
        curve,
        value=4.0,
        parameters=[
            ParameterValue("Rg", 4.0, "A", status=AnalysisStatus.SUCCESS),
            ParameterValue("I0", 10.0, "a.u.", status=AnalysisStatus.SUCCESS),
        ],
    )
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve], analyses=[envelope])

    target = _export(run, tmp_path / "bundle")

    prerequisite = pd.read_csv(target / "data" / "dimensionless_kratky_prerequisites.csv").iloc[0]
    assert prerequisite["status"] == "available"
    values = pd.read_csv(target / "data" / "dimensionless_kratky.csv")
    np.testing.assert_allclose(values["x"], np.asarray(curve.q) * 4.0)
    np.testing.assert_allclose(values["y"], values["x"] ** 2 * np.asarray(curve.intensity) / 10.0)
    assert set(values["formula"]) == {"(q*Rg)^2 * I(q) / I0"}

    unknown = _curve(2, q_unit="q_unknown", intensity_unit="a.u.")
    unknown_env = _envelope(
        unknown,
        value=4.0,
        parameters=[
            ParameterValue("Rg", 4.0, "unknown_length", status=AnalysisStatus.SUCCESS),
            ParameterValue("I0", 10.0, "a.u.", status=AnalysisStatus.SUCCESS),
        ],
    )
    blocked = _export(AutoBatchRun(batch_id="sample-B", status="completed", curves=[unknown], analyses=[unknown_env]), tmp_path / "blocked")
    blocked_prerequisite = pd.read_csv(blocked / "data" / "dimensionless_kratky_prerequisites.csv").iloc[0]
    assert blocked_prerequisite["status"] == "missing_prerequisite"
    assert "unknown" in blocked_prerequisite["reason"]


def test_fit_residual_pr_and_correlation_views_use_only_supplied_tables(tmp_path: Path) -> None:
    curve = _curve(1)
    envelope = _envelope(
        curve,
        value=10.0,
        tables={
            "fit_curves": [{"q": 0.01, "I_observed": 10.0, "I_fit": 9.0, "residual": 1.0}],
            "residual_rows": [{
                "q": 0.01, "observed": 0.4, "fitted": 0.35, "residual": 0.05,
                "transformed_x": 0.00012, "fit_coordinate": "ln(I) versus q^2",
                "intensity": 10.0, "error": 0.3, "original_index": 1,
            }],
            "pr_distribution": [{"r": 1.0, "P(r)": 0.5}],
            "correlation_function": [{"r": 2.0, "correlation": 0.25}],
        },
    )
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve], analyses=[envelope])

    target = _export(run, tmp_path / "bundle")
    index = pd.read_csv(target / "figures" / "figure_index.csv")
    assert set(index["figure_kind"]) >= {"fit_and_residual", "reported_distribution"}
    assert set(index["table_name"].dropna()) >= {"fit_curves", "pr_distribution", "correlation_function"}
    fit = index[index["table_name"] == "fit_curves"].iloc[0]
    fit_source = pd.read_csv(target / fit["source_csv"])
    assert set(fit_source["plot_type"]) == {"fit_curves:experimental", "fit_curves:fit", "fit_curves:residual"}
    transformed = index[index["table_name"] == "residual_rows"].iloc[0]
    transformed_source = pd.read_csv(target / transformed["source_csv"])
    assert transformed_source["x"].tolist() == [0.00012, 0.00012, 0.00012]
    assert transformed_source["I"].tolist() == [10.0, 10.0, 10.0]
    assert transformed_source["y_unit"].str.contains("ln(I numeric value", regex=False).all()
    assert set(transformed_source["error_unit"]) == {curve.intensity_unit}
    assert set(transformed_source["q_unit"]) == {curve.q_unit}


def test_hash_manifest_and_completed_bundle_are_written_after_all_artifacts(tmp_path: Path) -> None:
    curve = _curve(1)
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve])
    target = _export(run, tmp_path / "bundle")

    manifest = json.loads((target / "package_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["manifest_self_hash"].startswith("omitted")
    for record in manifest["files"]:
        path = target / record["path"]
        assert path.stat().st_size == record["size_bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    assert (target / "data_bundle.zip").is_file()
    assert (target / "figures_bundle.zip").is_file()
    with pytest.raises(FileExistsError):
        _export(run, target)


def test_failed_figure_save_preserves_evidence_and_never_publishes_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.publication_bundle_plots as publication_plots

    curve = _curve(1)
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve])

    def fail_save(*args, **kwargs):
        raise OSError("simulated figure backend failure")

    monkeypatch.setattr(publication_plots, "_save_figure", fail_save)
    target = tmp_path / "never-complete"
    with pytest.raises(OSError, match="simulated figure"):
        _export(run, target)

    assert not target.exists()
    incomplete = list(tmp_path.glob(".never-complete.staging-*"))
    assert len(incomplete) == 1
    assert json.loads((incomplete[0] / "export_failure.json").read_text(encoding="utf-8"))["status"] == "incomplete"
    assert not (incomplete[0] / "package_manifest.json").exists()


def test_source_copy_hash_mismatch_fails_without_publishing_target(tmp_path: Path) -> None:
    raw = tmp_path / "frame.csv"
    raw.write_text("q,I\n0.01,10\n", encoding="utf-8")
    curve = _curve(1, source_file=raw)
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve])
    run.input_manifest = [{
        "source_file": raw.name,
        "source_relative_path": "frame.csv",
        "source_path": str(raw),
        "sha256": "0" * 64,
    }]
    target = tmp_path / "bad-hash"

    with pytest.raises(ValueError, match="Source input hash mismatch"):
        _export(run, target)

    assert not target.exists()
    incomplete = list(tmp_path.glob(".bad-hash.staging-*"))
    assert len(incomplete) == 1
    assert (incomplete[0] / "export_failure.json").is_file()


def test_mixed_unit_curves_cannot_publish_a_mislabeled_overlay(tmp_path: Path) -> None:
    curves = [_curve(1, intensity_unit="cm^-1"), _curve(2, intensity_unit="counts")]
    target = tmp_path / "mixed-units"
    with pytest.raises(ValueError, match="intensity units differ"):
        _export(AutoBatchRun(batch_id="mixed", status="completed", curves=curves), target)
    assert not target.exists()


def test_exploratory_parameters_have_evolution_without_status_promotion(tmp_path: Path) -> None:
    curves = [_curve(frame) for frame in (1, 2, 3)]
    envelopes = [_envelope(curve, value=4.0 + index, reporting_status="exploratory",
                           status=AnalysisStatus.ASSUMPTION_DEPENDENT if index != 1 else AnalysisStatus.FIT_FAILED)
                 for index, curve in enumerate(curves)]
    target = _export(AutoBatchRun(batch_id="sample-A", status="partial_success", curves=curves, analyses=envelopes), tmp_path / "exploratory")
    index = pd.read_csv(target / "figures/figure_index.csv")
    candidate = index[index["figure_kind"] == "exploratory_parameter_evolution"].iloc[0]
    source = pd.read_csv(target / candidate["source_csv"])
    assert source["x"].tolist() == [1.0, 2.0, 3.0]
    assert source["y"].iloc[0] == 4.0 and np.isnan(source["y"].iloc[1]) and source["y"].iloc[2] == 6.0
    assert set(source["reporting_status"]) == {"exploratory"}
    assert not (index["figure_kind"] == "reliable_parameter_evolution").any()


def test_planned_import_failure_is_retained_as_a_null_trajectory_gap(tmp_path: Path) -> None:
    files = [tmp_path / f"sample_{frame:04d}.csv" for frame in (1, 2, 3)]
    for frame, path in zip((1, 2, 3), files):
        path.write_text(f"q,I\n0.01,{10 - frame}\n0.02,2\n", encoding="utf-8")
    first, third = _curve(1, source_file=files[0]), _curve(3, source_file=files[2])
    for curve, relative, sequence_order in ((first, files[0].name, 0), (third, files[2].name, 2)):
        curve.metadata["source_relative_path"] = relative
        curve.metadata["sequence_order"] = sequence_order
    planned = [
        {"source_relative_path": path.name, "source_file": path.name, "sample_id": "sample-A", "series_id": "sample-A", "frame_index": frame, "sequence_order": frame - 1}
        for frame, path in zip((1, 2, 3), files)
    ]
    run = AutoBatchRun(
        batch_id="sample-A",
        status="partial_success",
        curves=[first, third],
        analyses=[_envelope(first, value=10.0), _envelope(third, value=14.0)],
        failed_inputs=[{"file": files[1].name, "error": "Malformed numeric columns"}],
        input_manifest=[
            {"source_file": path.name, "source_relative_path": path.name, "source_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in files
        ],
        config_snapshot={"planned_frames": planned},
    )

    target = _export(run, tmp_path / "bundle")

    failed_index = pd.read_csv(target / "data" / "failed_frame_index.csv")
    assert failed_index["frame_index"].tolist() == [2]
    assert failed_index["status"].tolist() == ["import_failed"]
    evolution = pd.read_csv(target / "data" / "analysis_evolution.csv")
    rg_rows = evolution[evolution["parameter_name"] == "Rg"].sort_values("frame_index")
    assert rg_rows["envelope_status"].tolist() == ["success", "import_failed", "success"]
    assert pd.isna(rg_rows.iloc[1]["value"])
    index = pd.read_csv(target / "figures" / "figure_index.csv")
    trajectory = index[index["figure_kind"] == "reliable_parameter_evolution"].iloc[0]
    source = pd.read_csv(target / trajectory["source_csv"])
    assert source["x"].tolist() == [1.0, 2.0, 3.0]
    np.testing.assert_allclose(source["y"].to_numpy(), [10.0, np.nan, 14.0], equal_nan=True)


def test_selected_sequence_axis_is_used_and_invalid_declared_axis_has_no_frame_fallback(tmp_path: Path) -> None:
    curves = [_curve(1), _curve(2)]
    for curve, temperature in zip(curves, (25.0, 75.0)):
        curve.metadata["temperature_C"] = temperature
    analyses = [_envelope(curve, value=5.0 + i) for i, curve in enumerate(curves)]
    valid = AutoBatchRun(
        batch_id="sample-A", status="completed", curves=curves, analyses=analyses,
        config_snapshot={"sequence_axis": "temperature_C"},
        sequence_results={"sequence_axis": "temperature_C", "sequence_axis_valid": True},
    )
    target = _export(valid, tmp_path / "valid-axis")
    evolution = pd.read_csv(target / "data" / "analysis_evolution.csv")
    assert sorted(evolution[evolution["parameter_name"] == "Rg"]["frame_x"].tolist()) == [25.0, 75.0]

    invalid = AutoBatchRun(
        batch_id="sample-B", status="completed", curves=curves, analyses=analyses,
        config_snapshot={"sequence_axis": "temperature_C"},
        sequence_results={"sequence_axis": "temperature_C", "sequence_axis_valid": False},
    )
    blocked = _export(invalid, tmp_path / "invalid-axis")
    blocked_evolution = pd.read_csv(blocked / "data" / "analysis_evolution.csv")
    assert blocked_evolution[blocked_evolution["parameter_name"] == "Rg"]["frame_x"].isna().all()


def test_shape_bound_hit_and_uncertainty_fields_are_preserved_and_gate_reliable_plot(tmp_path: Path) -> None:
    curve = _curve(1)
    envelope = _envelope(
        curve,
        value=None,
        analysis_type="shape_models",
        analysis_id=f"{curve.curve_id}:shape_models:sphere",
        tables={"parameter_records": [{
            "name": "radius", "value": 8.0, "unit": "A", "stderr": 0.4,
            "ci95_low": 7.2, "ci95_high": 8.8, "bound_hit": True,
            "reason": "optimizer reached upper bound",
        }]},
        parameters=[],
    )
    run = AutoBatchRun(batch_id="sample-A", status="completed", curves=[curve], analyses=[envelope])

    target = _export(run, tmp_path / "bundle")

    evolution = pd.read_csv(target / "data" / "analysis_evolution.csv")
    radius = evolution[evolution["parameter_name"] == "radius"].iloc[0]
    assert radius["stderr"] == pytest.approx(0.4)
    assert radius["ci95_low"] == pytest.approx(7.2)
    assert radius["ci95_high"] == pytest.approx(8.8)
    assert bool(radius["bound_hit"])
    assert radius["reliable_reportable"] == False
    assert radius["reliability_gate_reason"] == "parameter_bound_hit"
    assert "upper bound" in radius["invalid_reason"]
    model = pd.read_csv(target / "data" / "model_parameter_records.csv").iloc[0]
    assert model["stderr"] == pytest.approx(0.4)
    assert bool(model["bound_hit"])
