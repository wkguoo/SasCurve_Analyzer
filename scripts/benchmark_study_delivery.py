"""Measure real headless study delivery and verify completed study packages.

Example (run from any directory)::

    py -3 scripts/benchmark_study_delivery.py --repo E:/Vibe_coding/SasCurve_Analyzer `
      --input E:/Vibe_coding/_artifacts/SasCurve_Analyzer/performance-20261012/inputs `
      --output E:/Vibe_coding/_artifacts/SasCurve_Analyzer/performance-20261012/fresh-study `
      --config E:/Vibe_coding/_artifacts/SasCurve_Analyzer/performance-20261012/config.json `
      --threads 1 `
      --receipt E:/Vibe_coding/_artifacts/SasCurve_Analyzer/performance-20261012/fresh.receipt.json

The measured interval is immediately before ``Popen`` through ``wait`` return.
Receipts and captured streams are siblings of the study output. Resource counters
are sampled across the CLI process tree; process I/O bytes are logical OS counters,
not physical disk traffic. Benchmark use requires the optional ``psutil`` package.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any
import zipfile
import xml.etree.ElementTree as ET


THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
SAMPLE_INTERVAL_S = 0.10
COMPLETE_STATUSES = {"completed", "completed_with_limitations"}
UUID_PATTERN = re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b")
ISO_TIME_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b")
GENERATED_TIME_KEYS = {"created_at", "created_at_utc", "updated_at", "updated_at_utc", "started_at", "started_at_utc", "finished_at", "finished_at_utc", "generated_at", "generated_at_utc", "exported_at", "exported_at_utc"}
GENERATED_ID_KEYS = {"study_id", "run_id", "curve_id", "curve_ids", "analysis_id", "analysis_ids", "record_id", "formal_id", "group_id", "uuid", "reference_curve_id", "selected_curve_id", "supporting_curve_ids", "source_detection_analysis_id", "related_analysis_ids"}
PATH_KEYS = {"path", "file", "filename", "source_file", "source_path", "package", "output", "output_dir"}
STABLE_SOURCE_PATH_KEYS = {"config_path", "input_path", "input_root", "metadata_path", "source_file", "source_path", "source_relative_path", "source_relative"}
RANDOM_PATH_SUFFIX = re.compile(r"(?i)_([0-9a-f]{12})(?=\.)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe relative path in study inventory: {value}")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Study path escapes its output directory: {value}")
    return path


def verify_bundle_zip(package: Path, archive_path: Path, expected_members: set[str] | None = None) -> dict[str, Any]:
    """Check ZIP CRCs, safe member names, and byte alignment with package files."""
    failures: list[str] = []
    members_checked = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                failures.append("duplicate member names")
            if expected_members is not None and set(names) != expected_members:
                missing = sorted(expected_members - set(names))
                unexpected = sorted(set(names) - expected_members)
                failures.append(f"member set differs (missing={missing}, unexpected={unexpected})")
            for name in names:
                try:
                    source = _safe_relative(package, name)
                except ValueError as exc:
                    failures.append(str(exc))
                    continue
                if not source.is_file():
                    failures.append(f"missing package file for ZIP member: {name}")
                    continue
                aligned = True
                with archive.open(name) as member, source.open("rb") as actual:
                    while True:
                        archived_chunk = member.read(1024 * 1024)
                        actual_chunk = actual.read(1024 * 1024)
                        if archived_chunk != actual_chunk:
                            aligned = False
                        if not archived_chunk:
                            if actual_chunk:
                                aligned = False
                            break
                if not aligned:
                    failures.append(f"ZIP member differs from package file: {name}")
                    continue
                members_checked += 1
    except (OSError, RuntimeError, NotImplementedError, EOFError, zipfile.BadZipFile) as exc:
        failures.append(f"cannot read archive: {exc}")
    return {"path": archive_path.name, "members_checked": members_checked, "errors": failures, "ok": not failures}


def verify_package(package: Path, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify study inventory, publication manifest, and all bundled ZIP bytes."""
    errors: list[str] = []
    file_count = 0
    zip_members = 0
    if not package.is_dir():
        return {"ok": False, "files_checked": 0, "zip_members_checked": 0, "errors": ["package directory is missing"]}
    expected = {str(row.get("file")): row for row in inventory}
    if len(expected) != len(inventory):
        errors.append("study output_inventory contains duplicate file paths")
    actual_paths = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()}
    if set(expected) != actual_paths:
        errors.append("study output_inventory file set differs from package contents")
    observed: dict[str, tuple[int, str]] = {}
    for relative, row in expected.items():
        try:
            path = _safe_relative(package, relative)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing inventory file: {relative}")
            continue
        actual_size, actual_sha = path.stat().st_size, sha256_file(path)
        observed[relative] = (actual_size, actual_sha)
        if actual_size != row.get("size_bytes") or actual_sha != row.get("sha256"):
            errors.append(f"study output_inventory mismatch: {relative}")
        file_count += 1

    manifest_path = package / "package_manifest.json"
    if not manifest_path.is_file():
        errors.append("package_manifest.json is missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "complete":
                errors.append("package manifest status is not complete")
            listed = {row.get("path"): row for row in manifest.get("files", [])}
            if len(listed) != len(manifest.get("files", [])):
                errors.append("package manifest contains duplicate file paths")
            actual_payload = {name for name in actual_paths if Path(name).name != "package_manifest.json"}
            if set(listed) != actual_payload:
                errors.append("package manifest file set differs from package contents")
            for relative, row in listed.items():
                try:
                    path = _safe_relative(package, str(relative))
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                actual = observed.get(str(relative))
                if not path.is_file() or actual != (row.get("size_bytes"), row.get("sha256")):
                    errors.append(f"package manifest mismatch: {relative}")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"cannot validate package manifest: {exc}")

    data_members = {name for name in actual_paths if name.startswith(("data/", "analysis/"))}
    data_members.add("analysis_envelopes.json")
    figure_members = {
        name for name in actual_paths
        if name.startswith("figures/") and name != "figures/figure_index.csv"
    }
    figure_members.update(name for name in actual_paths if name.startswith("data/plot_sources/"))
    figure_members.add("figures/figure_index.csv")
    for archive_path, expected_members in (
        (package / "data_bundle.zip", data_members),
        (package / "figures_bundle.zip", figure_members),
    ):
        if not archive_path.is_file():
            errors.append(f"{archive_path.name} is missing")
            continue
        report = verify_bundle_zip(package, archive_path, expected_members)
        errors.extend(f"{archive_path.name}: {message}" for message in report["errors"])
        zip_members += int(report["members_checked"])
    return {"ok": not errors, "files_checked": file_count, "zip_members_checked": zip_members, "errors": errors}


def verify_study_output(output: Path) -> dict[str, Any]:
    """Check study checkpoint/index and every published sample package."""
    root = output.resolve()
    errors: list[str] = []
    packages: dict[str, Any] = {}
    checkpoint = root / "study.json"
    if not checkpoint.is_file():
        return {"ok": False, "status": None, "packages": packages, "errors": ["study.json is missing"]}
    try:
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "status": None, "packages": packages, "errors": [f"cannot read study.json: {exc}"]}
    if not isinstance(state, dict) or not isinstance(state.get("samples"), dict):
        return {"ok": False, "status": None, "packages": packages, "errors": ["study.json has an unsupported structure"]}
    index_path = root / "sample_index.csv"
    if not index_path.is_file():
        errors.append("sample_index.csv is missing")
    else:
        try:
            with index_path.open("r", encoding="utf-8-sig", newline="") as stream:
                parsed_index = list(csv.DictReader(stream))
            index_rows = {row.get("sample_id", ""): row for row in parsed_index}
            if len(index_rows) != len(parsed_index):
                errors.append("sample_index.csv contains duplicate sample IDs")
            if set(index_rows) != set(state.get("samples", {})):
                errors.append("sample_index.csv sample set differs from study.json")
            for sample_id, record in state.get("samples", {}).items():
                row = index_rows.get(sample_id)
                if row is None or row.get("status") != record.get("status") or row.get("package") != record.get("package"):
                    errors.append(f"sample_index.csv does not match study.json for {sample_id}")
        except (OSError, csv.Error) as exc:
            errors.append(f"cannot read sample_index.csv: {exc}")
    if not (root / "README.md").is_file():
        errors.append("study README.md is missing")

    for sample_id, record in state.get("samples", {}).items():
        package_name = record.get("package")
        if not package_name:
            errors.append(f"sample has no package: {sample_id} (status={record.get('status')})")
            packages[sample_id] = {"ok": False, "errors": ["no package published"]}
            continue
        try:
            package = _safe_relative(root, str(package_name))
        except ValueError as exc:
            errors.append(f"{sample_id}: {exc}")
            packages[sample_id] = {"ok": False, "errors": [str(exc)]}
            continue
        report = verify_package(package, record.get("output_inventory", []))
        packages[sample_id] = report
        errors.extend(f"{sample_id}: {message}" for message in report["errors"])
    state_status = state.get("status")
    if state_status not in COMPLETE_STATUSES:
        errors.append(f"study status is not complete: {state_status}")
    elif any(not row.get("ok") for row in packages.values()):
        errors.append("completed study contains an invalid or missing package")
    return {
        "ok": not errors,
        "status": state_status,
        "study_fingerprint": state.get("fingerprint"),
        "sample_count": len(state.get("samples", {})),
        "packages": packages,
        "errors": errors,
    }


class _ContentNormalizer:
    """Normalize run IDs, ISO timestamps and the compared output-root path."""

    def __init__(self, output_root: Path):
        self.output_root = str(output_root.resolve())
        self.output_root_posix = output_root.resolve().as_posix()
        self.ids: dict[str, str] = {}

    def seed_identities(self, state: dict[str, Any]) -> None:
        """Bind curve UUIDs to source identity before UUID-sorted consensus rows."""
        self.ids[str(state["study_id"]).lower()] = "<STUDY>"
        for sample_id, record in sorted(state["samples"].items()):
            self.ids[str(record["run_id"]).lower()] = f"<RUN:{sample_id}>"
            summary = Path(self.output_root) / record["package"] / "analysis/summary/run_summary.json"
            if not summary.is_file():
                continue
            for curve in json.loads(summary.read_text(encoding="utf-8")).get("curves", []):
                label = "<CURVE:" + json.dumps([sample_id, curve.get("source_file"), curve["name"]], ensure_ascii=False) + ">"
                key = str(curve["curve_id"]).lower()
                if key in self.ids and self.ids[key] != label:
                    raise ValueError("Generated curve identity collision")
                self.ids[key] = label

    def text(self, value: str, *, normalize_uuid: bool = False, normalize_time: bool = False) -> str:
        value = value.replace(self.output_root, "<OUTPUT_ROOT>").replace(self.output_root_posix, "<OUTPUT_ROOT>")

        def canonical_id(match: re.Match[str]) -> str:
            value = match.group(0).lower()
            return self.ids.setdefault(value, f"<UUID_{len(self.ids) + 1}>")

        if normalize_uuid:
            value = UUID_PATTERN.sub(canonical_id, value)
        return ISO_TIME_PATTERN.sub("<ISO_TIME>", value) if normalize_time else value

    def path(self, value: str) -> str:
        value = self.text(value, normalize_uuid=True, normalize_time=True)
        if "analysis_tables/" in value:
            value = re.sub(r"__[0-9a-f]{8}(?=\.csv$)", "__<ANALYSIS_ID_HASH>", value)
        return RANDOM_PATH_SUFFIX.sub("_<ID_HASH>", value)

    def json_value(self, value: Any, *, omit_output_inventory: bool = False) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, child in sorted(value.items()):
                if key == "output_inventory" and omit_output_inventory:
                    continue  # Hashes are validated individually; compare package contents below.
                if key == "files" and value.get("schema") == "sascurve.publication_bundle.v1":
                    result[key] = sorted(self.path(row.get("path", "")) for row in child)
                elif key.lower() in GENERATED_ID_KEYS:
                    if isinstance(child, str):
                        result[key] = self.text(child, normalize_uuid=True)
                    elif isinstance(child, list):
                        result[key] = [self.text(item, normalize_uuid=True) if isinstance(item, str) else self.json_value(item, omit_output_inventory=omit_output_inventory) for item in child]
                        if key == "supporting_curve_ids":
                            result[key].sort()  # Consensus support is a set, exported in random-UUID order.
                    else:
                        result[key] = self.json_value(child, omit_output_inventory=omit_output_inventory)
                elif key.lower() in GENERATED_TIME_KEYS and isinstance(child, str):
                    result[key] = self.text(child, normalize_time=True)
                elif key.lower() in STABLE_SOURCE_PATH_KEYS:
                    result[key] = self.text(child) if isinstance(child, str) else self.json_value(child, omit_output_inventory=omit_output_inventory)
                elif key.lower() in PATH_KEYS or key.lower().endswith(("_path", "_file", "_filename")):
                    result[key] = self.path(child) if isinstance(child, str) else self.json_value(child, omit_output_inventory=omit_output_inventory)
                else:
                    result[self.text(key, normalize_uuid=True) if UUID_PATTERN.fullmatch(key) else key] = self.json_value(child, omit_output_inventory=omit_output_inventory)
            return result
        if isinstance(value, list):
            return [self.json_value(item, omit_output_inventory=omit_output_inventory) for item in value]
        if isinstance(value, str):
            return self.text(value)
        return value


def _csv_value(path: Path, normalizer: _ContentNormalizer) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    if not rows:
        return []
    generated_time_columns = {index for index, name in enumerate(rows[0]) if name.strip().lower() in GENERATED_TIME_KEYS}
    generated_id_columns = {index for index, name in enumerate(rows[0]) if name.strip().lower() in GENERATED_ID_KEYS}
    path_columns = {index for index, name in enumerate(rows[0]) if name.strip().lower() in PATH_KEYS or name.strip().lower().endswith(("_path", "_file", "_filename"))}
    stable_source_columns = {index for index, name in enumerate(rows[0]) if name.strip().lower() in STABLE_SOURCE_PATH_KEYS}
    structured = {"supporting_curve_ids", "execution_n_points_by_curve", "q_selection_evidence"}

    def cell(value: str, row_index: int, column_index: int) -> str:
        name = rows[0][column_index].strip().lower()
        if row_index and name in structured and value:
            try:
                decoded = json.loads(value)
            except ValueError:
                decoded = ast.literal_eval(value)
            return json.dumps(normalizer.json_value({name: decoded}), sort_keys=True, ensure_ascii=False)
        if row_index and column_index in stable_source_columns:
            return normalizer.text(value)
        if row_index and column_index in path_columns:
            return normalizer.path(value)
        return normalizer.text(value, normalize_uuid=bool(row_index and column_index in generated_id_columns),
                               normalize_time=bool(row_index and column_index in generated_time_columns))

    return [
        [cell(value, row_index, column_index) for column_index, value in enumerate(row)]
        for row_index, row in enumerate(rows)
    ]


def _json_value(path: Path, normalizer: _ContentNormalizer, *, omit_output_inventory: bool = False) -> Any:
    return normalizer.json_value(json.loads(path.read_text(encoding="utf-8")), omit_output_inventory=omit_output_inventory)


def _png_pixels(path: Path):
    from PIL import Image
    import numpy as np

    with Image.open(path) as image:
        return np.asarray(image.convert("RGBA"))


def _svg_content(path: Path) -> Any:
    """Compare vector structure after only generated IDs/RDF metadata removal."""
    root = ET.parse(path).getroot()
    ids = {node.attrib["id"]: f"id_{index}" for index, node in enumerate(root.iter()) if "id" in node.attrib}

    def value(text: str) -> str:
        if text in ids:
            return ids[text]
        return re.sub(r"(?<=#)[A-Za-z0-9_]+", lambda match: ids.get(match.group(), match.group()), text)

    def node_value(node):
        return (node.tag, sorted((key, value(item)) for key, item in node.attrib.items()),
                (node.text or "").strip(), [node_value(child) for child in node if child.tag.rsplit("}", 1)[-1] != "metadata"])

    return node_value(root)


def _pdf_content_equal(left: Path, right: Path) -> bool:
    """Check page geometry, text, drawing commands and 200-dpi rendered pixels."""
    try:
        import fitz  # Optional verification dependency, not an application dependency.
    except ImportError as exc:
        raise RuntimeError("PDF verification requires the optional PyMuPDF package (pip install PyMuPDF)") from exc

    with fitz.open(left) as a, fitz.open(right) as b:
        if len(a) != len(b):
            return False
        for x, y in zip(a, b):
            if x.rect != y.rect or x.get_text("dict") != y.get_text("dict") or x.get_drawings() != y.get_drawings():
                return False
            px, py = x.get_pixmap(dpi=200), y.get_pixmap(dpi=200)
            if (px.width, px.height, px.samples) != (py.width, py.height, py.samples):
                return False
    return True


def _attest_runtime_upgrade(before_state, after_state, before_root, after_root, before_receipt, after_receipt):
    """Permit the added dependency snapshot only with matching timed receipts."""
    if before_receipt is None or after_receipt is None:
        raise ValueError("Runtime snapshot upgrade comparison requires --before-receipt and --after-receipt")
    receipts = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (before_receipt, after_receipt)]
    for receipt, state, root in zip(receipts, (before_state, after_state), (before_root, after_root)):
        if Path(receipt["parameters"]["output"]).resolve() != root or receipt["source_snapshot"]["fingerprint"] != state["fingerprint"]:
            raise ValueError("Timing receipt does not identify the compared study")
        digest = hashlib.sha256(json.dumps(state["snapshot"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if state["fingerprint"] != digest:
            raise ValueError("Study snapshot fingerprint is invalid")
    versions = [dict(r["dependencies"], python=r["python"]["version"]) for r in receipts]
    if versions[0] != versions[1] or receipts[0]["parameters"]["config_sha256"] != receipts[1]["parameters"]["config_sha256"]:
        raise ValueError("Before/after runtime dependencies or configuration differ")
    expected = {name: versions[1][name] for name in ("python", "numpy", "scipy", "pandas", "matplotlib")}
    a, b = before_state["snapshot"], after_state["snapshot"]
    if "runtime_dependencies" in a or b.get("runtime_dependencies") != expected:
        raise ValueError("Only addition of the attested runtime snapshot is supported")
    if a != {key: item for key, item in b.items() if key != "runtime_dependencies"}:
        raise ValueError("Study input/config/version differs beyond the runtime snapshot addition")
    return {"change": "added_runtime_dependencies", "verified_dependencies": expected,
            "before_fingerprint": before_state["fingerprint"], "after_fingerprint": after_state["fingerprint"]}


def compare_studies(before: Path, after: Path, *, before_receipt: Path | None = None, after_receipt: Path | None = None) -> dict[str, Any]:
    """Compare complete studies after validating inventories and bundle archives.

    CSV/JSON values are exact after UUID, ISO-time and output-root normalization.
    PNG pixels must match exactly. SVG vector structure and PDF page geometry,
    text, drawings and rendered pixels must match; document metadata may differ.
    """
    before_root, after_root = before.resolve(strict=True), after.resolve(strict=True)
    if before_root == after_root:
        raise ValueError("Before and after must be distinct study directories")
    before_check = verify_study_output(before_root)
    after_check = verify_study_output(after_root)
    report: dict[str, Any] = {
        "before": str(before_root), "after": str(after_root),
        "before_integrity": before_check, "after_integrity": after_check,
        "csv_files": 0, "json_files": 0, "png_files": 0,
        "vector_artifacts": [], "mismatches": [],
    }
    if not before_check["ok"] or not after_check["ok"] or before_check.get("status") not in COMPLETE_STATUSES or after_check.get("status") not in COMPLETE_STATUSES:
        report["mismatches"].append("both studies must be complete and pass integrity checks")
        report["ok"] = False
        return report

    before_state = json.loads((before_root / "study.json").read_text(encoding="utf-8"))
    after_state = json.loads((after_root / "study.json").read_text(encoding="utf-8"))
    if before_state.get("snapshot", {}).get("runtime_dependencies") != after_state.get("snapshot", {}).get("runtime_dependencies"):
        report["provenance_change"] = _attest_runtime_upgrade(before_state, after_state, before_root, after_root, before_receipt, after_receipt)
        # Work on private decoded copies. The files/receipts remain intact.
        after_state["snapshot"].pop("runtime_dependencies")
        after_state["fingerprint"] = before_state["fingerprint"]
    before_samples, after_samples = before_state["samples"], after_state["samples"]
    before_norm, after_norm = _ContentNormalizer(before_root), _ContentNormalizer(after_root)
    before_norm.seed_identities(before_state)
    after_norm.seed_identities(after_state)
    before_sample_keys = {before_norm.text(sample_id, normalize_uuid=True): sample_id for sample_id in before_samples}
    after_sample_keys = {after_norm.text(sample_id, normalize_uuid=True): sample_id for sample_id in after_samples}
    if set(before_sample_keys) != set(after_sample_keys):
        report["mismatches"].append("sample sets differ")
        report["ok"] = False
        return report

    for relative in ("study.json", "sample_index.csv", "README.md"):
        left, right = before_root / relative, after_root / relative
        if not left.is_file() or not right.is_file():
            report["mismatches"].append(f"study-level file missing: {relative}")
            continue
        if relative.endswith(".json"):
            same = before_norm.json_value(before_state, omit_output_inventory=True) == after_norm.json_value(after_state, omit_output_inventory=True)
            report["json_files"] += 1
        elif relative.endswith(".csv"):
            same = _csv_value(left, before_norm) == _csv_value(right, after_norm)
            report["csv_files"] += 1
        else:
            same = before_norm.text(left.read_text(encoding="utf-8"), normalize_uuid=True) == after_norm.text(right.read_text(encoding="utf-8"), normalize_uuid=True)
        if not same:
            report["mismatches"].append(f"study-level content differs: {relative}")

    for sample_id in sorted(before_samples):
        left_record, right_record = before_samples[sample_id], after_samples[sample_id]
        normalized_sample_id = before_norm.text(sample_id, normalize_uuid=True)
        right_sample_id = after_sample_keys[normalized_sample_id]
        right_record = after_samples[right_sample_id]
        left_package = _safe_relative(before_root, str(left_record["package"]))
        right_package = _safe_relative(after_root, str(right_record["package"]))
        left_files = {before_norm.path(row["file"]): row["file"] for row in left_record["output_inventory"]}
        right_files = {after_norm.path(row["file"]): row["file"] for row in right_record["output_inventory"]}
        if len(left_files) != len(left_record["output_inventory"]) or len(right_files) != len(right_record["output_inventory"]):
            report["mismatches"].append(f"randomized path normalization caused collisions: {sample_id}")
            continue
        if set(left_files) != set(right_files):
            report["mismatches"].append(f"package file sets differ: {sample_id}")
            continue
        for relative in sorted(left_files):
            left = _safe_relative(left_package, left_files[relative])
            right = _safe_relative(right_package, right_files[relative])
            if not left.is_file() or not right.is_file():
                report["mismatches"].append(f"package file missing: {sample_id}/{relative}")
                continue
            suffix = left.suffix.lower()
            try:
                if suffix == ".csv":
                    same = _csv_value(left, before_norm) == _csv_value(right, after_norm)
                    report["csv_files"] += 1
                elif suffix == ".json":
                    same = _json_value(left, before_norm) == _json_value(right, after_norm)
                    report["json_files"] += 1
                elif suffix == ".png":
                    import numpy as np

                    same = bool(np.array_equal(_png_pixels(left), _png_pixels(right)))
                    report["png_files"] += 1
                elif suffix in {".svg", ".pdf"}:
                    byte_equal = left.stat().st_size == right.stat().st_size and sha256_file(left) == sha256_file(right)
                    content_equal = _svg_content(left) == _svg_content(right) if suffix == ".svg" else _pdf_content_equal(left, right)
                    report["vector_artifacts"].append({
                        "sample_id": normalized_sample_id,
                        "path": relative,
                        "byte_equal": byte_equal,
                        "sha256_equal": byte_equal,
                        "content_equal": content_equal,
                        "check": "SVG structure excluding generated IDs/RDF metadata" if suffix == ".svg" else "PDF geometry/text/drawings and 200-dpi pixels",
                    })
                    if not content_equal:
                        report["mismatches"].append(f"vector content differs: {normalized_sample_id}/{relative}")
                    continue
                elif suffix == ".zip":
                    with zipfile.ZipFile(left) as a, zipfile.ZipFile(right) as b:
                        same = sorted(before_norm.path(name) for name in a.namelist()) == sorted(after_norm.path(name) for name in b.namelist())
                    # Members were byte-aligned against each package during the integrity pass.
                else:
                    same = before_norm.text(left.read_text(encoding="utf-8"), normalize_uuid=True) == after_norm.text(right.read_text(encoding="utf-8"), normalize_uuid=True) if suffix in {".md", ".txt"} else left.read_bytes() == right.read_bytes()
            except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as exc:
                same = False
                report["mismatches"].append(f"cannot compare {normalized_sample_id}/{relative}: {exc}")
            if not same:
                report["mismatches"].append(f"content differs: {normalized_sample_id}/{relative}")
    report["csv_json_png_content_equal"] = not report["mismatches"]
    report["vector_artifact_bytes_equal"] = all(row["byte_equal"] for row in report["vector_artifacts"])
    report["vector_artifact_content_equal"] = all(row["content_equal"] for row in report["vector_artifacts"])
    report["full_output_equivalence"] = report["csv_json_png_content_equal"] and report["vector_artifact_content_equal"]
    report["comparison_limit"] = "Generated IDs/timestamps and SVG RDF/PDF document metadata may differ; scientific table values and vector content must match"
    report["ok"] = report["full_output_equivalence"]
    return report


class _ProcessTreeSampler:
    """Sample a process tree and retain cumulative counters for exited children."""

    def __init__(self, process, psutil_module, interval: float = SAMPLE_INTERVAL_S):
        self.process = process
        self.psutil = psutil_module
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="study-resource-sampler", daemon=True)
        self.peak_rss = 0
        self.peak_processes = 0
        self.peak_threads = 0
        self.samples = 0
        self.cpu_by_pid: dict[tuple[int, float], tuple[float, float]] = {}
        self.io_by_pid: dict[tuple[int, float], tuple[int, int]] = {}
        self.io_samples = 0

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(1.0, self.interval * 3))

    def _run(self) -> None:
        try:
            root = self.psutil.Process(self.process.pid)
        except self.psutil.Error:
            return
        while not self.stop_event.is_set():
            processes = [root]
            try:
                processes.extend(root.children(recursive=True))
            except self.psutil.Error:
                pass
            rss = 0
            living = 0
            for process in processes:
                try:
                    rss += process.memory_info().rss
                    living += 1
                    self.peak_threads = max(self.peak_threads, process.num_threads())
                except self.psutil.Error:
                    pass
                try:
                    identity = (process.pid, process.create_time())
                    cpu = process.cpu_times()
                    previous = self.cpu_by_pid.get(identity, (0.0, 0.0))
                    self.cpu_by_pid[identity] = (max(previous[0], cpu.user), max(previous[1], cpu.system))
                except self.psutil.Error:
                    identity = None
                try:
                    if identity is None:
                        continue
                    counters = process.io_counters()
                    previous_io = self.io_by_pid.get(identity, (0, 0))
                    self.io_by_pid[identity] = (max(previous_io[0], counters.read_bytes), max(previous_io[1], counters.write_bytes))
                    self.io_samples += 1
                except (self.psutil.Error, AttributeError):
                    pass
            self.peak_rss = max(self.peak_rss, rss)
            self.peak_processes = max(self.peak_processes, living)
            self.samples += 1
            self.stop_event.wait(self.interval)

    def result(self, wall_seconds: float, logical_cpus: int | None) -> dict[str, Any]:
        cpu_user = sum(item[0] for item in self.cpu_by_pid.values())
        cpu_system = sum(item[1] for item in self.cpu_by_pid.values())
        io_read = sum(item[0] for item in self.io_by_pid.values())
        io_write = sum(item[1] for item in self.io_by_pid.values())
        return {
            "sample_interval_seconds": self.interval,
            "resource_samples": self.samples,
            "sampled_peak_process_tree_rss_bytes": self.peak_rss,
            "sampled_peak_process_tree_rss_mib": round(self.peak_rss / (1024 ** 2), 3),
            "sampled_peak_process_count_including_cli": self.peak_processes,
            "sampled_peak_threads_in_one_process": self.peak_threads,
            "process_tree_cpu_user_seconds": round(cpu_user, 4),
            "process_tree_cpu_system_seconds": round(cpu_system, 4),
            "process_tree_cpu_total_seconds": round(cpu_user + cpu_system, 4),
            "cpu_percent_of_one_core": round(100 * (cpu_user + cpu_system) / wall_seconds, 2) if wall_seconds else None,
            "cpu_percent_of_host_capacity": round(100 * (cpu_user + cpu_system) / (wall_seconds * logical_cpus), 2) if wall_seconds and logical_cpus else None,
            "process_tree_logical_read_bytes": io_read,
            "process_tree_logical_write_bytes": io_write,
            "process_io_counter_observations": self.io_samples,
            "process_io_note": "sampled OS process counters for the CLI and observed descendants; logical bytes, not physical disk traffic; short-lived children and the final sampling interval may be missed",
        }


def _git_state(repo: Path) -> dict[str, Any]:
    def git(*args: str) -> bytes:
        return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    head = git("rev-parse", "HEAD").decode("ascii").strip()
    top = Path(git("rev-parse", "--show-toplevel").decode("utf-8", "surrogateescape").strip()).resolve()
    if top != repo.resolve():
        raise ValueError(f"--repo must be the Git root directory, got {repo}")
    patch = git("diff", "--binary", "HEAD")
    untracked = []
    for encoded in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if not encoded:
            continue
        relative = os.fsdecode(encoded)
        path = repo / relative
        if path.is_file():
            untracked.append({"path": relative.replace("\\", "/"), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    dirty = hashlib.sha256(patch + json.dumps(untracked, sort_keys=True).encode("utf-8")).hexdigest()
    status = git("status", "--short", "--branch").decode("utf-8", "replace").splitlines()
    return {"head": head, "dirty_diff_sha256": dirty, "git_status": status, "untracked_file_count": len(untracked)}


def _dependency_versions() -> dict[str, str | None]:
    names = {"numpy": "numpy", "pandas": "pandas", "scipy": "scipy", "matplotlib": "matplotlib", "psutil": "psutil",
             "pillow": "Pillow", "pymupdf": "PyMuPDF", "h5py": "h5py"}
    result = {}
    for key, distribution in names.items():
        try:
            result[key] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            result[key] = None
    return result


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot_from_output(output: Path) -> dict[str, Any] | None:
    checkpoint = output / "study.json"
    if not checkpoint.is_file():
        return None
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    snapshot = state.get("snapshot")
    if not isinstance(snapshot, dict):
        return None
    # Hashes were captured by the real study snapshot inside the timed run.
    return {
        "fingerprint": state.get("fingerprint"),
        "software_version": snapshot.get("software_version"),
        "algorithm_version": snapshot.get("algorithm_version"),
        "cache_schema_version": snapshot.get("cache_schema_version"),
        "study_algorithm_version": snapshot.get("study_algorithm_version"),
        "runtime_dependencies": snapshot.get("runtime_dependencies"),
        "inputs": snapshot.get("inputs", []),
        "metadata": snapshot.get("metadata", []),
    }


def _profile_run(repo: Path, input_dir: Path, config: Path, evidence_root: Path, receipt_stem: str, env: dict[str, str]) -> dict[str, Any]:
    pstats_path = evidence_root / f"{receipt_stem}.profile.pstats"
    stdout_path = evidence_root / f"{receipt_stem}.profile.stdout.log"
    stderr_path = evidence_root / f"{receipt_stem}.profile.stderr.log"
    for path in (pstats_path, stdout_path, stderr_path):
        if path.exists():
            raise FileExistsError(f"Profile evidence already exists: {path}")
    code = (
        "import cProfile,sys; from app.cli import main; "
        "profile=cProfile.Profile(); status=profile.runcall(main, sys.argv[2:]); "
        "profile.dump_stats(sys.argv[1]); raise SystemExit(status)"
    )
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f".{receipt_stem}.profile-study-", dir=evidence_root) as temporary:
        profile_output = Path(temporary) / "study"
        command = [sys.executable, "-c", code, str(pstats_path), "run", "--input", str(input_dir), "--output", str(profile_output), "--config", str(config), "--quiet"]
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = subprocess.run(command, cwd=repo, env=env, stdout=stdout, stderr=stderr, check=False)
    return {
        "return_code": completed.returncode,
        "profile_seconds_unmeasured": round(time.perf_counter() - started, 4),
        "pstats": str(pstats_path),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "note": "separate fresh cProfile run; excluded from the formal wall-time interval",
    }


def benchmark(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    try:
        import psutil
    except ImportError as exc:
        raise RuntimeError("Benchmarking requires psutil; install it in the analysis environment only") from exc

    repo = args.repo.resolve(strict=True)
    input_dir = args.input.resolve(strict=True)
    config = args.config.resolve(strict=True)
    output = args.output.resolve()
    receipt = args.receipt.resolve()
    evidence_root = receipt.parent
    stdout_path = evidence_root / f"{receipt.stem}.stdout.log"
    stderr_path = evidence_root / f"{receipt.stem}.stderr.log"
    if receipt == output:
        raise ValueError("Benchmark receipt path cannot equal the study output directory")
    if evidence_root.resolve().is_relative_to(output.resolve()) or evidence_root.resolve().is_relative_to(input_dir):
        raise ValueError("Receipt and captured streams must be outside the study output and input trees")
    if output.resolve().is_relative_to(input_dir) or input_dir.is_relative_to(output.resolve()):
        raise ValueError("Study input and output must be disjoint")
    if output.resolve().is_relative_to(repo) or input_dir.is_relative_to(repo):
        raise ValueError("Generated studies and measurements must remain outside the repository")
    if evidence_root.resolve().is_relative_to(repo):
        raise ValueError("Benchmark evidence must remain outside the repository")
    if receipt.exists():
        raise FileExistsError(f"Refusing to replace benchmark receipt: {receipt}")
    if stdout_path.exists() or stderr_path.exists():
        raise FileExistsError("Refusing to replace existing benchmark stdout/stderr evidence")
    if output.exists() and not args.resume:
        raise FileExistsError("Fresh benchmark output already exists; select a new output directory")
    if args.resume and not (output / "study.json").is_file():
        raise FileNotFoundError("--resume requires an existing study.json")
    if args.resume and not args.retry_failed:
        state = json.loads((output / "study.json").read_text(encoding="utf-8"))
        if state.get("status") not in COMPLETE_STATUSES:
            raise ValueError("Completed-resume benchmark requires an already completed study")
    if args.retry_failed and not args.resume:
        raise ValueError("--retry-failed requires --resume")
    evidence_root.mkdir(parents=True, exist_ok=True)

    git = _git_state(repo)
    input_config_sha = sha256_file(config)
    environment = os.environ.copy()
    for name in THREAD_ENV:
        environment[name] = "1"
    command = [sys.executable, "-m", "app.cli", "run", "--input", str(input_dir), "--output", str(output), "--config", str(config), "--quiet"]
    if args.resume:
        command.append("--resume")
    if args.retry_failed:
        command.append("--retry-failed")

    logical_cpus = psutil.cpu_count(logical=True)
    physical_cpus = psutil.cpu_count(logical=False)
    memory = psutil.virtual_memory()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        start = time.perf_counter()
        process = subprocess.Popen(command, cwd=repo, env=environment, stdout=stdout, stderr=stderr)
        sampler = _ProcessTreeSampler(process, psutil)
        sampler.start()
        return_code = process.wait()
        wall_seconds = time.perf_counter() - start
        sampler.stop()

    try:
        cli_stdout = json.loads(stdout_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cli_stdout = None
    verification_started = time.perf_counter()
    try:
        verification = verify_study_output(output) if (output / "study.json").is_file() else {
            "ok": False, "status": None, "packages": {}, "errors": ["CLI did not create study.json"],
        }
    except Exception as exc:
        verification = {"ok": False, "status": None, "packages": {}, "errors": [f"external output verification raised {type(exc).__name__}: {exc}"]}
    if not isinstance(cli_stdout, dict):
        verification["ok"] = False
        verification.setdefault("errors", []).append("CLI stdout was not a JSON result")
    elif verification.get("status") is not None and cli_stdout.get("status") != verification.get("status"):
        verification["ok"] = False
        verification.setdefault("errors", []).append("CLI result status differs from final study.json")
    verification_seconds = time.perf_counter() - verification_started
    try:
        source_snapshot = _snapshot_from_output(output)
    except Exception as exc:
        source_snapshot = {"error": f"could not read CLI study snapshot: {type(exc).__name__}: {exc}"}
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "resume_retry_failed" if args.retry_failed else "completed_resume" if args.resume else "fresh",
        "started_at_utc": started_utc,
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": str(repo),
        "git": git,
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "platform": platform.platform(),
        "dependencies": _dependency_versions(),
        "resources": {
            "logical_cpu_count": logical_cpus,
            "physical_cpu_count": physical_cpus,
            "total_memory_bytes": memory.total,
            "thread_environment": {name: environment[name] for name in THREAD_ENV},
            **sampler.result(wall_seconds, logical_cpus),
        },
        "parameters": {
            "command": command,
            "input": str(input_dir),
            "output": str(output),
            "config": str(config),
            "config_sha256": input_config_sha,
            "resume": args.resume,
            "retry_failed": args.retry_failed,
            "quiet": True,
            "threads": args.threads,
            "analysis_worker_count": 1,
            "thread_control": "analysis jobs are sequential; BLAS/OpenMP thread environment capped at 1 (app.cli has no --threads option)",
        },
        "measurement": {
            "wall_seconds_popen_to_wait": round(wall_seconds, 6),
            "verification_seconds_outside_timed_interval": round(verification_seconds, 6),
            "wall_plus_external_verification_seconds": round(wall_seconds + verification_seconds, 6),
            "cli_return_code": return_code,
        },
        "cli_result": cli_stdout,
        "output_verification": verification,
        "source_snapshot": source_snapshot,
        "evidence": {"stdout": str(stdout_path), "stderr": str(stderr_path), "receipt": str(receipt)},
    }
    _atomic_json(receipt, result)
    if args.profile:
        try:
            result["profile"] = _profile_run(repo, input_dir, config, evidence_root, receipt.stem, environment)
        except Exception as exc:
            result["profile"] = {"status": "error", "error": str(exc), "note": "profile work is separate and excluded from formal wall time"}
        _atomic_json(receipt, result)
    return result, return_code if return_code else (0 if verification["ok"] else 4)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="Git repository root")
    parser.add_argument("--input", type=Path, help="Prepared study input directory")
    parser.add_argument("--output", type=Path, help="Study output directory")
    parser.add_argument("--config", type=Path, help="Study JSON config")
    parser.add_argument("--receipt", type=Path, help="Output receipt outside the study directory")
    parser.add_argument("--resume", action="store_true", help="Measure CLI --resume on an existing study")
    parser.add_argument("--retry-failed", action="store_true", help="Pass CLI --retry-failed (requires --resume)")
    parser.add_argument("--profile", action="store_true", help="Run a separate fresh cProfile study after the measured run")
    parser.add_argument("--threads", type=int, choices=(1,), default=1, help="Analysis is sequential; one thread is the only supported setting")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"), help="Compare two completed studies instead of running the CLI")
    parser.add_argument("--before-receipt", type=Path, help="Original timing receipt for runtime snapshot upgrade comparison")
    parser.add_argument("--after-receipt", type=Path, help="Optimized timing receipt for runtime snapshot upgrade comparison")
    args = parser.parse_args(argv)
    try:
        if args.compare:
            if args.receipt and any(args.receipt.resolve().is_relative_to(path.resolve()) for path in args.compare):
                raise ValueError("Comparison receipt must be outside both study directories")
            if args.receipt and args.receipt.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
                raise ValueError("Comparison evidence must remain outside the repository")
            report = compare_studies(args.compare[0], args.compare[1], before_receipt=args.before_receipt, after_receipt=args.after_receipt)
            if args.receipt:
                target = args.receipt.resolve()
                if target.exists():
                    raise FileExistsError(f"Refusing to replace comparison receipt: {target}")
                target.parent.mkdir(parents=True, exist_ok=True)
                report["receipt"] = str(target)
                _atomic_json(target, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 4
        missing = [name for name in ("repo", "input", "output", "config", "receipt") if getattr(args, name) is None]
        if missing:
            parser.error(f"benchmark mode requires --{' --'.join(missing)}")
        result, code = benchmark(args)
        print(json.dumps({
            "status": "recorded",
            "mode": result["mode"],
            "wall_seconds": result["measurement"]["wall_seconds_popen_to_wait"],
            "wall_plus_external_verification_seconds": result["measurement"]["wall_plus_external_verification_seconds"],
            "cli_return_code": result["measurement"]["cli_return_code"],
            "receipt": result["evidence"]["receipt"],
            "output_verification_ok": result["output_verification"]["ok"],
        }, ensure_ascii=False, indent=2))
        return code
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
