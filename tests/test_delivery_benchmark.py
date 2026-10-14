from __future__ import annotations

import io
import csv
import hashlib
import json
from pathlib import Path
import uuid
import zipfile

import numpy as np
import pytest
from PIL import Image

from scripts.benchmark_study_delivery import compare_studies, verify_bundle_zip
from scripts.prepare_vtma_benchmark import curve_csv_text, select_entries, study_config


def test_vtma_entries_are_selected_by_numeric_frame_index() -> None:
    names = [
        "VTMA13b_2_870C_10min_0014_mrg",
        "VTMA13b_2_870C_0min_0004_mrg",
        "VTMA13b_2_870C_9min_0006_mrg",
        "VTMA13b_2_30C_0min_0003_mrg",
        "VTMA13b_2_870C_4min_0005_mrg",
    ]

    selected = select_entries(names, limit=4)

    assert [row[1] for row in selected] == [4, 5, 6, 14]
    assert [row[2] for row in selected] == [0, 4, 9, 10]


def test_generated_config_matches_the_benchmark_analysis_contract(tmp_path: Path) -> None:
    config = study_config(tmp_path / "metadata.csv")

    assert config["grouping"] == "metadata"
    assert config["analysis"]["sample_type"] == "unknown"
    assert config["analysis"]["enable_shape_models"] is False
    assert config["analysis"]["allow_per_frame_range_fallback"] is True
    assert config["analysis"]["sequence_axis"] == "time_s"
    assert config["analysis"]["enable_range_sensitivity"] is True
    assert config["figures"] == {"formats": ["png", "svg", "pdf"], "dpi": 200, "max_overlay_curves": 24}


def test_vtma_csv_round_trips_binary64_values_including_missing_data() -> None:
    values = np.array([
        [0.00010674384108649685, 2371362484.9774961, 55953274.677015036, -0.0],
        [0.2, np.nan, np.inf, -np.inf],
    ], dtype=np.float64)

    text = curve_csv_text(values)
    restored = np.loadtxt(io.StringIO(text), delimiter=",", skiprows=1, ndmin=2)
    non_nan = ~np.isnan(values)

    assert restored.shape == values.shape
    assert np.array_equal(np.isnan(restored), np.isnan(values))
    assert np.array_equal(np.ascontiguousarray(restored).view(np.uint64)[non_nan], np.ascontiguousarray(values).view(np.uint64)[non_nan])


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_study(output: Path, *, run_id: str, created_at: str, acquisition_at: str) -> None:
    sample_id = "VTMA13b_2_870C"
    package = output / "samples" / f"{sample_id}-test"
    curve_id = str(uuid.uuid4())
    suffix = uuid.UUID(run_id).hex[:12]
    figure_path = f"figures/fit_curve_data_{suffix}.png"
    transformed_path = f"data/transformed/curve_{suffix}.csv"
    (package / transformed_path).parent.mkdir(parents=True, exist_ok=True)
    (package / "data/plot_sources").mkdir(parents=True, exist_ok=True)
    (package / "analysis").mkdir(parents=True, exist_ok=True)
    (package / "figures").mkdir(parents=True, exist_ok=True)
    (package / "data/curves_long.csv").write_text(
        "sample_id,curve_id,q_A_inv,intensity_cm_inv,time_s\n"
        f"{sample_id},{curve_id},0.0125,42.0,240\n",
        encoding="utf-8",
    )
    (package / transformed_path).write_text(
        f"curve_id,q_A_inv,intensity_cm_inv\n{curve_id},0.0125,42.0\n",
        encoding="utf-8",
    )
    (package / "data/plot_sources/curve.csv").write_text("q_A_inv,intensity_cm_inv\n0.0125,42.0\n", encoding="utf-8")
    result = {
        "run_id": run_id,
        "curve_id": curve_id,
        "created_at": created_at,
        "acquisition_timestamp": acquisition_at,
        "output_path": str(output),
        "q_unit": "A^-1",
        "intensity_unit": "cm^-1",
        "error": None,
        "gate": "reliable",
    }
    _write_json(package / "analysis/result.json", result)
    _write_json(package / "analysis_envelopes.json", {"run_id": run_id, "curve_id": curve_id, "acquisition_timestamp": acquisition_at})
    (package / "README.md").write_text(f"Run ID: {run_id}\n", encoding="utf-8")
    Image.new("RGBA", (2, 2), (12, 34, 56, 255)).save(package / figure_path, format="PNG")
    with (package / "figures/figure_index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("figure_path", "source_file", "curve_id", "created_at"))
        writer.writerow((figure_path, "data/plot_sources/curve.csv", curve_id, created_at))

    data_members = {
        path.relative_to(package).as_posix()
        for folder in (package / "data", package / "analysis")
        for path in folder.rglob("*") if path.is_file()
    } | {"analysis_envelopes.json"}
    figure_members = {
        path.relative_to(package).as_posix()
        for path in (package / "figures").rglob("*") if path.is_file()
    } | {"data/plot_sources/curve.csv"}
    for archive_name, members in (("data_bundle.zip", data_members), ("figures_bundle.zip", figure_members)):
        with zipfile.ZipFile(package / archive_name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in sorted(members):
                archive.write(package / member, member)

    manifest_files = [
        {"path": path.relative_to(package).as_posix(), "size_bytes": path.stat().st_size, "sha256": _digest(path)}
        for path in sorted(package.rglob("*")) if path.is_file() and path.name != "package_manifest.json"
    ]
    _write_json(package / "package_manifest.json", {
        "schema": "sascurve.publication_bundle.v1", "status": "complete", "run_id": run_id, "files": manifest_files,
    })
    inventory = [
        {"file": path.relative_to(package).as_posix(), "size_bytes": path.stat().st_size, "sha256": _digest(path)}
        for path in sorted(package.rglob("*")) if path.is_file()
    ]
    (output / "samples").mkdir(parents=True, exist_ok=True)
    _write_json(output / "study.json", {
        "schema_version": 1, "status": "completed", "study_id": run_id,
        "fingerprint": "same-input-fingerprint", "started_at": created_at, "finished_at": created_at,
        "snapshot": {"input_root": "E:/shared/input", "inputs": [], "metadata": [], "software_version": "1", "algorithm_version": "1", "cache_schema_version": 1, "study_algorithm_version": 2},
        "samples": {sample_id: {"status": "completed", "package": f"samples/{sample_id}-test", "run_id": run_id, "output_inventory": inventory}},
    })
    with (output / "sample_index.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("sample_id", "status", "package", "curve_count", "failed_inputs", "error"))
        writer.writerow((sample_id, "completed", f"samples/{sample_id}-test", 1, 0, ""))
    (output / "README.md").write_text("Open sample_index.csv.\n", encoding="utf-8")


def test_compare_studies_normalizes_run_identity_but_preserves_acquisition_metadata(tmp_path: Path) -> None:
    before, after, changed = tmp_path / "before", tmp_path / "after-with-a-longer-name", tmp_path / "changed"
    _write_study(before, run_id="55e6d0f7-1fb7-43e4-a68a-6870269bb44c", created_at="2026-10-12T04:12:08Z", acquisition_at="2018-02-07T00:00:00Z")
    _write_study(after, run_id="8d05e62a-77bf-402e-9d34-2da08cfc7730", created_at="2026-10-12T04:16:33Z", acquisition_at="2018-02-07T00:00:00Z")
    _write_study(changed, run_id="c7b2448e-cfdc-4cf8-804e-a3e20d1ef115", created_at="2026-10-12T04:18:33Z", acquisition_at="2018-02-08T00:00:00Z")

    equivalent = compare_studies(before, after)
    changed_metadata = compare_studies(before, changed)

    assert equivalent["ok"], equivalent["mismatches"]
    assert equivalent["csv_files"] > 0 and equivalent["json_files"] > 0 and equivalent["png_files"] == 1
    assert not changed_metadata["ok"]
    assert any("analysis/result.json" in mismatch for mismatch in changed_metadata["mismatches"])


def test_zip_member_bytes_must_match_package_file(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    member = package / "data.csv"
    member.write_bytes(b"q,I\n0.1,2\n")
    archive_path = package / "data_bundle.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(member, "data.csv")

    assert verify_bundle_zip(package, archive_path, {"data.csv"})["ok"]
    member.write_bytes(b"q,I\n0.1,3\n")
    report = verify_bundle_zip(package, archive_path, {"data.csv", "missing.csv"})
    assert not report["ok"]
    assert any("differs from package file" in error for error in report["errors"])
    assert any("member set differs" in error for error in report["errors"])


def test_comparison_rejects_same_output_and_receipt_inside_output(tmp_path):
    from scripts.benchmark_study_delivery import main

    before, after = tmp_path / "before", tmp_path / "after"
    for root in (before, after):
        _write_study(root, run_id=str(uuid.uuid4()), created_at="2026-10-13T00:00:00Z", acquisition_at="2018-02-07T00:00:00Z")
    with pytest.raises(ValueError, match="distinct"):
        compare_studies(before, before)
    receipt = before / "comparison.json"
    assert main(["--compare", str(before), str(after), "--receipt", str(receipt)]) == 1
    assert not receipt.exists()


def test_generated_analysis_table_hash_is_normalized_without_hiding_source_names(tmp_path):
    from scripts.benchmark_study_delivery import _ContentNormalizer

    normalize = _ContentNormalizer(tmp_path)
    assert normalize.path("analysis/details/analysis_tables/frame__power_law__parameter_records__a123bc45.csv") == normalize.path("analysis/details/analysis_tables/frame__power_law__parameter_records__f456de78.csv")
    assert normalize.path("data/source_inputs/source__a123bc45.csv") != normalize.path("data/source_inputs/source__f456de78.csv")


def test_consensus_and_related_ids_preserve_source_relationships_and_counts(tmp_path):
    from scripts.benchmark_study_delivery import _ContentNormalizer, _csv_value

    ids = [str(uuid.uuid4()) for _ in range(4)]
    normals, paths = [], []
    for index in range(2):
        first, second = ids[2 * index:2 * index + 2]
        normal = _ContentNormalizer(tmp_path)
        normal.ids.update({first: "<FRAME_1>", second: "<FRAME_2>"})
        normals.append(normal)
        path = tmp_path / f"consensus-{index}.csv"
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["supporting_curve_ids", "execution_n_points_by_curve", "related_analysis_ids", "time_s"])
            writer.writerow([str(sorted([first, second])), str({first: 44, second: 43}), first + ":shoulders", "240"])
        paths.append(path)
    assert _csv_value(paths[0], normals[0]) == _csv_value(paths[1], normals[1])
    paths[1].write_text(paths[1].read_text().replace(": 43", ": 42"))
    assert _csv_value(paths[0], normals[0]) != _csv_value(paths[1], normals[1])


def test_runtime_snapshot_upgrade_requires_matching_attested_versions(tmp_path):
    before, after = tmp_path / "before", tmp_path / "after"
    versions = {"numpy": "2.1.2", "scipy": "1.18.0", "pandas": "2.2.3", "matplotlib": "3.11.1"}
    states, receipts = [], []
    for index, root in enumerate((before, after)):
        _write_study(root, run_id=str(uuid.uuid4()), created_at="2026-10-13T00:00:00Z", acquisition_at="2018-02-07T00:00:00Z")
        state = json.loads((root / "study.json").read_text())
        if index:
            state["snapshot"]["runtime_dependencies"] = dict(versions, python="3.12.10")
        state["fingerprint"] = hashlib.sha256(json.dumps(state["snapshot"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        _write_json(root / "study.json", state)
        states.append(state)
        receipt = tmp_path / f"timing-{index}.json"
        _write_json(receipt, {"parameters": {"output": str(root), "config_sha256": "same-config"},
                              "dependencies": versions, "python": {"version": "3.12.10"},
                              "source_snapshot": {"fingerprint": state["fingerprint"]}})
        receipts.append(receipt)
    with pytest.raises(ValueError, match="requires"):
        compare_studies(before, after)
    report = compare_studies(before, after, before_receipt=receipts[0], after_receipt=receipts[1])
    assert report["ok"], report["mismatches"]
    assert report["provenance_change"]["change"] == "added_runtime_dependencies"
    changed = json.loads(receipts[1].read_text())
    changed["dependencies"]["scipy"] = "changed"
    _write_json(receipts[1], changed)
    with pytest.raises(ValueError, match="dependencies"):
        compare_studies(before, after, before_receipt=receipts[0], after_receipt=receipts[1])


def test_svg_comparison_keeps_vector_geometry_and_ignores_generated_metadata(tmp_path):
    from scripts.benchmark_study_delivery import _svg_content

    files = [tmp_path / f"{i}.svg" for i in range(3)]
    for index, path in enumerate(files):
        path.write_text(f'<svg xmlns="http://www.w3.org/2000/svg"><metadata>date-{index}</metadata>'
                        f'<defs><path id="random{index}" d="M 0 0 L {2 if index == 2 else 1} 1"/></defs>'
                        f'<use href="#random{index}"/></svg>')
    assert _svg_content(files[0]) == _svg_content(files[1])
    assert _svg_content(files[0]) != _svg_content(files[2])


def test_pdf_comparison_keeps_drawings_and_pixels(tmp_path):
    fitz = pytest.importorskip("fitz")
    from scripts.benchmark_study_delivery import _pdf_content_equal

    files = [tmp_path / f"{i}.pdf" for i in range(3)]
    for index, path in enumerate(files):
        with fitz.open() as document:
            page = document.new_page(width=100, height=100)
            page.draw_line((10, 10), (20 if index == 2 else 40, 40))
            document.set_metadata({"title": str(index)})
            document.save(path)
    assert _pdf_content_equal(files[0], files[1])
    assert not _pdf_content_equal(files[0], files[2])


def test_pdf_comparison_missing_dependency_fails_with_actionable_error(monkeypatch, tmp_path):
    import builtins
    from scripts.benchmark_study_delivery import _pdf_content_equal

    original = builtins.__import__
    def no_pdf(name, *args, **kwargs):
        if name == "fitz":
            raise ModuleNotFoundError("fitz")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pdf)
    with pytest.raises(RuntimeError, match="optional PyMuPDF"):
        _pdf_content_equal(tmp_path / "before.pdf", tmp_path / "after.pdf")
