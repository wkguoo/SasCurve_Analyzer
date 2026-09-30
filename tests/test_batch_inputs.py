from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

import app.core.batch_inputs as batch_inputs
from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_inputs import collect_batch_inputs, discover_curve_files, sha256_file


def _write_curve(path: Path, intensity: float = 10.0) -> None:
    path.write_text(
        f"q,I\n0.01,{intensity}\n0.02,{intensity / 2}\n",
        encoding="utf-8",
    )


def test_discovery_uses_natural_sort_and_supported_extensions(tmp_path: Path) -> None:
    for name in ["sample_10.csv", "sample_2.dat", "sample_1.txt", "ignore.md"]:
        (tmp_path / name).write_text("q,I\n0.01,1\n0.02,2\n", encoding="utf-8")

    assert [path.name for path in discover_curve_files(tmp_path)] == [
        "sample_1.txt",
        "sample_2.dat",
        "sample_10.csv",
    ]


def test_selected_sample_ignores_out_of_scope_sidecar_rows(tmp_path: Path) -> None:
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        _write_curve(tmp_path / folder / "sample_1.csv")
    metadata = tmp_path / "metadata.csv"
    metadata.write_text("source_file,time_s\na\\sample_1.csv,0\nb/sample_1.csv,1\n", encoding="utf-8")
    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="a", metadata_path=metadata), input_paths=[tmp_path / "a" / "sample_1.csv"])
    assert result.curves[0].metadata["time_s"] == 0
    assert not any("did not match" in warning for warning in result.warnings)


def test_metadata_is_merged_without_modifying_source(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    original = b"q,I\n0.01,10\n0.02,5\n"
    curve_path.write_bytes(original)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": curve_path.name, "time_s": 5.0}]).to_csv(metadata_path, index=False)

    config = AutoBatchConfig(batch_id="sample", metadata_path=metadata_path)
    result = collect_batch_inputs(tmp_path, config)

    assert result.curves[0].metadata["time_s"] == 5.0
    assert result.curves[0].metadata["metadata_source"] == str(metadata_path.resolve())
    assert result.curves[0].metadata["metadata_sha256"] == sha256(metadata_path.read_bytes()).hexdigest()
    assert result.curves[0].metadata["metadata_match_column"] == "source_file"
    assert result.curves[0].metadata["metadata_match_key"] == curve_path.name
    assert result.curves[0].metadata["metadata_row_index"] == 0
    assert result.failed_inputs == []
    assert [item["source_file"] for item in result.manifest] == [curve_path.name]
    manifest = result.manifest[0]
    source_stat = curve_path.stat()
    assert manifest["source_path"] == str(curve_path.resolve())
    assert manifest["size_bytes"] == len(original)
    assert manifest["modified_time"] == pytest.approx(source_stat.st_mtime)
    assert manifest["sha256"] == sha256(original).hexdigest()
    assert manifest["manifest_status"] == "success"
    assert manifest["manifest_error"] is None
    assert curve_path.read_bytes() == original


def test_collect_batch_inputs_filters_q_at_ingestion_and_keeps_source_unchanged(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    original = b"q,I\n0.001,20\n0.01,10\n0.02,5\n0.05,2\n0.08,1\n"
    curve_path.write_bytes(original)

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample"))

    assert len(result.curves) == 1
    curve = result.curves[0]
    assert curve.q.tolist() == [0.01, 0.02, 0.05]
    assert curve.intensity.tolist() == [10.0, 5.0, 2.0]
    q_filter = curve.metadata["import_q_range_filter"]
    assert q_filter["enabled"] is True
    assert q_filter["q_min"] == 0.01
    assert q_filter["q_max"] == 0.05
    assert q_filter["raw_point_count"] == 5
    assert q_filter["imported_point_count"] == 3
    assert q_filter["filtered_out_point_count"] == 2
    assert result.import_summary["q_range_filter_enabled"] is True
    assert result.import_summary["raw_total_points"] == 5
    assert result.import_summary["imported_total_points"] == 3
    assert curve_path.read_bytes() == original


def test_q_unit_override_is_converted_before_canonical_range_filter(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    curve_path.write_text(
        "q_A_inv,I\n0.05,20\n0.1,10\n0.2,5\n0.5,2\n0.8,1\n",
        encoding="utf-8",
    )

    result = collect_batch_inputs(
        tmp_path,
        AutoBatchConfig(
            batch_id="sample",
            q_unit_override="nm^-1",
            intensity_unit_override="counts",
        ),
    )

    curve = result.curves[0]
    assert curve.q.tolist() == pytest.approx([0.01, 0.02, 0.05])
    assert curve.q_unit == "A^-1"
    assert curve.intensity_unit == "counts"
    assert curve.metadata["source_q_unit"] == "nm^-1"
    assert curve.metadata["source_intensity_unit"] == "counts"
    assert curve.metadata["q_unit_conversion_factor"] == 0.1
    assert result.import_summary["q_unit"] == "A^-1"


def test_explicit_nested_paths_sort_by_relative_path_and_match_full_metadata_keys(tmp_path: Path) -> None:
    first = tmp_path / "sample_2" / "curve_0001.csv"
    second = tmp_path / "sample_10" / "curve_0001.csv"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_curve(first)
    _write_curve(second, intensity=8.0)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {"source_file": "sample_10/curve_0001.csv", "time_s": 10.0},
            {"source_file": "sample_2/curve_0001.csv", "time_s": 2.0},
        ]
    ).to_csv(metadata_path, index=False)

    result = collect_batch_inputs(
        tmp_path,
        AutoBatchConfig(batch_id="nested", metadata_path=metadata_path),
        input_paths=[second, first],
    )

    assert [curve.metadata["source_relative_path"] for curve in result.curves] == [
        "sample_2/curve_0001.csv",
        "sample_10/curve_0001.csv",
    ]
    assert [curve.metadata["time_s"] for curve in result.curves] == [2.0, 10.0]
    assert all(curve.metadata["metadata_match_status"] == "matched" for curve in result.curves)
    assert [entry["source_relative_path"] for entry in result.manifest] == [
        "sample_2/curve_0001.csv",
        "sample_10/curve_0001.csv",
    ]
    assert all(entry["source_path"].endswith(entry["source_relative_path"].replace("/", "\\")) for entry in result.manifest)


def test_explicit_nested_paths_do_not_fallback_to_ambiguous_basename(tmp_path: Path) -> None:
    first = tmp_path / "a" / "curve_0001.csv"
    second = tmp_path / "b" / "curve_0001.csv"
    first.parent.mkdir()
    second.parent.mkdir()
    _write_curve(first)
    _write_curve(second)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": "curve_0001.csv", "time_s": 10.0}]).to_csv(metadata_path, index=False)

    result = collect_batch_inputs(
        tmp_path,
        AutoBatchConfig(batch_id="nested", metadata_path=metadata_path),
        input_paths=[first, second],
    )

    assert all("time_s" not in curve.metadata for curve in result.curves)
    assert sum("ambiguous basename metadata key" in warning for warning in result.warnings) == 2


def test_explicit_paths_must_be_unique_and_within_input_dir(tmp_path: Path) -> None:
    inside = tmp_path / "sample_0001.csv"
    outside = tmp_path.parent / "outside.csv"
    _write_curve(inside)
    _write_curve(outside)

    with pytest.raises(ValueError, match="Duplicate input path"):
        collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="x"), input_paths=[inside, inside])
    with pytest.raises(ValueError, match="must be within input_dir"):
        collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="x"), input_paths=[outside])


def test_sidecar_cannot_replace_reserved_provenance_or_units(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    source_bytes = b"q_nm_inv,I\n0.1,10\n0.2,5\n"
    curve_path.write_bytes(source_bytes)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {
                "source_file": curve_path.name,
                "time_s": 5.0,
                "sequence_order": 99,
                "source_path": "C:/fake.csv",
                "source_relative_path": "fake.csv",
                "source_sha256": "bad",
                "sha256": "bad",
                "q_unit": "nm^-1",
            }
        ]
    ).to_csv(metadata_path, index=False)

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))

    curve = result.curves[0]
    assert curve.metadata["time_s"] == 5.0
    assert curve.metadata["sequence_order"] == 0
    assert curve.metadata["source_file"] == curve_path.name
    assert curve.metadata["source_path"] == str(curve_path.resolve())
    assert curve.metadata["source_relative_path"] == curve_path.name
    assert curve.metadata["source_sha256"] == sha256(source_bytes).hexdigest()
    assert curve.q_unit == "A^-1"
    assert curve.metadata["source_q_unit"] == "nm^-1"
    assert any("reserved provenance or validation fields" in warning for warning in result.warnings)


def test_trusted_identity_metadata_is_applied_after_sidecar_and_before_return(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    _write_curve(curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": curve_path.name, "frame_index": 12, "sample_id": "sidecar"}]).to_csv(
        metadata_path, index=False
    )

    result = collect_batch_inputs(
        tmp_path,
        AutoBatchConfig(batch_id="sample", metadata_path=metadata_path),
        input_metadata={
            "sample_0001.csv": {
                "sample_id": "trusted-sample",
                "series_id": "trusted-series",
                "frame_index": 1,
                "frame_label": "001",
                "identity_source": "folder_regex",
            }
        },
    )

    assert result.curves[0].metadata["sample_id"] == "trusted-sample"
    assert result.curves[0].metadata["series_id"] == "trusted-series"
    assert result.curves[0].metadata["frame_index"] == 1
    assert result.curves[0].metadata["frame_label"] == "001"
    assert result.curves[0].metadata["identity_source"] == "folder_regex"


def test_manifest_hash_failure_is_isolated_per_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    good_path = tmp_path / "sample_0001.csv"
    failing_path = tmp_path / "sample_0002.csv"
    _write_curve(good_path, intensity=10.0)
    _write_curve(failing_path, intensity=8.0)
    original_sha256_file = batch_inputs.sha256_file

    def fail_one_hash(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
        if Path(path).name == failing_path.name:
            raise OSError("simulated hash failure")
        return original_sha256_file(path, chunk_size)

    monkeypatch.setattr(batch_inputs, "sha256_file", fail_one_hash)

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample"))

    assert [Path(curve.source_file or "").name for curve in result.curves] == [
        good_path.name,
        failing_path.name,
    ]
    manifest_by_name = {item["source_file"]: item for item in result.manifest}
    assert manifest_by_name[good_path.name]["manifest_status"] == "success"
    assert manifest_by_name[failing_path.name]["manifest_status"] == "failed"
    assert manifest_by_name[failing_path.name]["sha256"] is None
    assert manifest_by_name[failing_path.name]["manifest_error"] == "simulated hash failure"
    assert {
        "file": failing_path.name,
        "stage": "manifest",
        "error": "simulated hash failure",
    } in result.failed_inputs


def test_invalid_curve_import_failure_remains_in_manifest(tmp_path: Path) -> None:
    valid_path = tmp_path / "sample_0001.csv"
    invalid_path = tmp_path / "sample_0002.csv"
    _write_curve(valid_path)
    invalid_path.write_text("x,y\n1,2\n", encoding="utf-8")

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample"))

    assert [Path(curve.source_file or "").name for curve in result.curves] == [valid_path.name]
    assert any(item["file"] == invalid_path.name for item in result.failed_inputs)
    assert [item["source_file"] for item in result.manifest] == [valid_path.name, invalid_path.name]
    assert all(item["manifest_status"] == "success" for item in result.manifest)


def test_collect_batch_inputs_rejects_duplicate_nonempty_metadata_keys(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    _write_curve(curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame(
        [
            {"source_file": curve_path.name, "time_s": 1.0},
            {"source_file": curve_path.name, "time_s": 2.0},
        ]
    ).to_csv(metadata_path, index=False)

    with pytest.raises(ValueError, match="Duplicate metadata match key .*sample_0001.csv"):
        collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))


def test_collect_batch_inputs_requires_metadata_match_column(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    _write_curve(curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"not_source_file": curve_path.name, "time_s": 1.0}]).to_csv(metadata_path, index=False)

    with pytest.raises(ValueError, match="Metadata match column not found: source_file"):
        collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))


def test_collect_batch_inputs_warns_for_unmatched_metadata_key(tmp_path: Path) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    _write_curve(curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": "not_present.csv", "time_s": 5.0}]).to_csv(metadata_path, index=False)

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))

    assert (
        "Metadata key 'not_present.csv' in column 'source_file' did not match an imported curve."
        in result.warnings
    )


def test_collect_batch_inputs_marks_curves_without_metadata_rows(tmp_path: Path) -> None:
    matched_curve_path = tmp_path / "sample_0001.csv"
    unmatched_curve_path = tmp_path / "sample_0002.csv"
    _write_curve(matched_curve_path)
    _write_curve(unmatched_curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": matched_curve_path.name, "time_s": 5.0}]).to_csv(metadata_path, index=False)

    result = collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))
    curve_by_file = {Path(curve.source_file or "").name: curve for curve in result.curves}

    assert curve_by_file[matched_curve_path.name].metadata["metadata_match_status"] == "matched"
    assert curve_by_file[unmatched_curve_path.name].metadata["metadata_match_status"] == "no_matching_row"
    assert (
        "Curve 'sample_0002.csv' has no matching metadata row in column 'source_file'."
        in result.warnings
    )


def test_collect_batch_inputs_fails_clearly_when_metadata_hash_cannot_be_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve_path = tmp_path / "sample_0001.csv"
    _write_curve(curve_path)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": curve_path.name, "time_s": 5.0}]).to_csv(metadata_path, index=False)
    original_sha256_file = batch_inputs.sha256_file

    def fail_metadata_hash(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
        if Path(path).name == metadata_path.name:
            raise OSError("simulated metadata hash failure")
        return original_sha256_file(path, chunk_size)

    monkeypatch.setattr(batch_inputs, "sha256_file", fail_metadata_hash)

    with pytest.raises(RuntimeError, match="Could not calculate SHA-256 for metadata sidecar"):
        collect_batch_inputs(tmp_path, AutoBatchConfig(batch_id="sample", metadata_path=metadata_path))


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_sha256_file_rejects_non_positive_chunk_size(tmp_path: Path, chunk_size: int) -> None:
    source_path = tmp_path / "sample_0001.csv"
    _write_curve(source_path)

    with pytest.raises(ValueError, match="chunk_size must be positive"):
        sha256_file(source_path, chunk_size=chunk_size)
