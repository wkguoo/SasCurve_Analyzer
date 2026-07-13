from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from scripts.analyze_ti15_sequence import (
    HARD_Q_RANGE,
    build_config,
    discover_ti15_inputs,
    main,
    source_integrity_rows,
    source_snapshot,
    validate_standard_layout,
)


def _touch(path: Path, text: str = "q,I\n0.01,1\n") -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_discovery_keeps_real_frame_numbers_and_always_selects_rt_reference(tmp_path: Path) -> None:
    _touch(tmp_path / "ti15_00001_abs2d_cm-1.csv")
    _touch(tmp_path / "TI15_00002_abs2d_cm-1.csv")
    _touch(tmp_path / "ti15_00004_abs2d_cm-1.csv")
    reference = _touch(tmp_path / "TI15-rt_00001_abs2d_cm-1.csv")
    _touch(tmp_path / "unrelated.csv")

    selection = discover_ti15_inputs(tmp_path, limit=2)

    assert selection.selected_frame_numbers == [1, 2]
    assert selection.all_series_frames == (1, 2, 4)
    assert selection.missing_frames == (3,)
    assert selection.references == (reference.resolve(),)
    assert len(selection.selected_paths) == 3


def test_zero_limit_selects_every_series_curve(tmp_path: Path) -> None:
    for frame in (1, 2, 4):
        _touch(tmp_path / f"ti15_{frame:05d}_abs2d_cm-1.csv")
    _touch(tmp_path / "ti15-rt_00001_abs2d_cm-1.csv")

    selection = discover_ti15_inputs(tmp_path, limit=0)

    assert selection.selected_frame_numbers == [1, 2, 4]
    assert len(selection.references) == 1


def test_strict_layout_rejects_nonstandard_fixture(tmp_path: Path) -> None:
    _touch(tmp_path / "ti15_00001_abs2d_cm-1.csv")
    _touch(tmp_path / "ti15-rt_00001_abs2d_cm-1.csv")

    selection = discover_ti15_inputs(tmp_path, limit=0)

    with pytest.raises(ValueError, match="expected 117 in-situ frames"):
        validate_standard_layout(selection)


def test_model_free_config_matches_ti15_contract() -> None:
    config = build_config(limit=10)

    assert config.effective_q_range == HARD_Q_RANGE
    assert config.range_mode == "dual"
    assert config.enable_shape_models is False
    assert config.allowed_models == []
    assert config.enable_pr is False
    assert config.enable_correlation is False
    assert config.enable_sequence_analysis is False
    assert config.enable_kinetics is False
    assert config.enable_exploratory_statistics is False
    assert config.enable_bootstrap is True
    assert config.bootstrap_samples == 200
    assert config.bootstrap_mode == "moving_block_residual"
    assert config.enable_range_sensitivity is True
    assert config.create_archives is False
    assert config.reference_filename_pattern == "-rt_"


def test_source_snapshot_detects_no_change_and_hash_change(tmp_path: Path) -> None:
    series = _touch(tmp_path / "ti15_00001_abs2d_cm-1.csv")
    _touch(tmp_path / "ti15-rt_00001_abs2d_cm-1.csv")
    selection = discover_ti15_inputs(tmp_path, limit=0)
    before = source_snapshot(selection)

    unchanged = source_integrity_rows(before, source_snapshot(selection))
    assert all(row["unchanged_after_analysis"] for row in unchanged)

    series.write_text("q,I\n0.01,2\n", encoding="utf-8")
    changed = source_integrity_rows(before, source_snapshot(selection))
    changed_series = next(row for row in changed if row["sequence_role"] == "series")
    assert changed_series["unchanged_after_analysis"] is False


def test_workbook_builder_uses_dynamic_data_quality_range_and_no_default_compaction() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_summary_workbook.mjs"
    ).read_text(encoding="utf-8")

    assert "A2:A${lastDataQualityRow}" in source
    assert 'const compactAfterExport = cliArgs.includes("--compact")' in source
    assert "if (compactAfterExport)" in source


def test_nonstandard_trial_run_exports_without_changing_sources(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    result_root = tmp_path / "results"
    input_dir.mkdir()
    q = np.geomspace(0.005, 0.06, 90)
    for frame, scale in ((1, 1.0), (3, 1.1)):
        intensity = scale * q ** -3.2
        rows = ["q_A_inv,intensity_cm_inv", *[f"{x:.12g},{y:.12g}" for x, y in zip(q, intensity)]]
        _touch(input_dir / f"ti15_{frame:05d}_abs2d_cm-1.csv", "\n".join(rows) + "\n")
    rows = ["q_A_inv,intensity_cm_inv", *[f"{x:.12g},{0.8 * x ** -3.2:.12g}" for x in q]]
    _touch(input_dir / "ti15-rt_00001_abs2d_cm-1.csv", "\n".join(rows) + "\n")
    before = {path.name: path.read_bytes() for path in input_dir.glob("*.csv")}

    exit_code = main(
        [
            "--input-dir",
            str(input_dir),
            "--results-root",
            str(result_root),
            "--limit",
            "2",
            "--allow-nonstandard-layout",
            "--skip-workbook",
            "--detail-level",
            "none",
        ]
    )

    assert exit_code == 0
    result_dirs = list(result_root.glob("17_Ti15_300_2_iso_model_free_*"))
    assert len(result_dirs) == 1
    result_dir = result_dirs[0]
    assert (result_dir / "final_report_zh.md").is_file()
    assert (result_dir / "final_results.csv").is_file()
    assert (result_dir / "summary" / "missing_frames.csv").is_file()
    assert (result_dir / "summary" / "room_temperature_reference.csv").is_file()
    assert (result_dir / "summary" / "adaptive_parameters.csv").is_file()
    assert (result_dir / "summary" / "common_parameters.csv").is_file()
    assert (result_dir / "summary" / "dual_track_differences.csv").is_file()
    assert (result_dir / "summary" / "robustness.csv").is_file()
    assert (result_dir / "audit" / "range_audit.csv").is_file()
    assert (result_dir / "audit" / "consensus_regions.csv").is_file()
    assert (result_dir / "audit" / "all_parameters_audit.csv").is_file()
    assert (result_dir / "audit" / "workbook_sources" / "analysis_inventory_workbook.csv").is_file()
    assert {path.name for path in result_dir.iterdir()} <= {
        "README.md",
        "final_report_zh.md",
        "final_results.csv",
        "run_config.json",
        "summary_tables.xlsx",
        "validation_summary.json",
        "audit",
        "details",
        "figures",
        "summary",
    }
    assert not list(result_dir.glob("*.zip"))
    assert before == {path.name: path.read_bytes() for path in input_dir.glob("*.csv")}


def test_artifact_workbook_builder_renders_and_exports_without_compacting(tmp_path: Path) -> None:
    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (result_dir / "summary").mkdir()
    (result_dir / "summary" / "data_quality.csv").write_text(
        "frame_index,sequence_role,curve_name,source_file,q_unit,point_count,finite_pair_count,"
        "nan_or_inf_pair_count,negative_intensity_count,zero_intensity_count,duplicate_q_count,"
        "strictly_increasing_q,log_usable_count,q_min_A^-1,q_max_A^-1,I_min_cm^-1,I_max_cm^-1,"
        "hard_q_low_A^-1,hard_q_high_A^-1,raw_source_point_count,filtered_out_point_count,"
        "has_measurement_error_column\n"
        "1,series,ti15_00001,ti15_00001_abs2d_cm-1.csv,A^-1,214,214,0,0,0,0,true,214,"
        "0.01,0.5,1,10,0.01,0.5,5500,5286,false\n",
        encoding="utf-8",
    )
    (result_dir / "run_config.json").write_text(
        '{"effective_q_range":[0.01,0.5],"input_selection":'
        '{"limit":10,"selected_series_count":1,"reference_count":1}}\n',
        encoding="utf-8",
    )
    marker = result_dir / "must_remain.txt"
    marker.write_text("not compacted", encoding="utf-8")
    builder = Path(__file__).resolve().parents[1] / "scripts" / "build_summary_workbook.mjs"

    completed = subprocess.run(
        ["node", str(builder), str(result_dir)],
        cwd=builder.parent.parent,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    assert (result_dir / "summary_tables.xlsx").is_file()
    assert (result_dir / "audit" / "workbook_validation.json").is_file()
    assert marker.is_file()
    assert not (result_dir / "review").exists()
    assert "FORMULA_ERRORS=" in completed.stdout
    assert "Cell search matched 0 entries" in completed.stdout
    assert "COMPACT_PACKAGE=disabled" in completed.stdout
