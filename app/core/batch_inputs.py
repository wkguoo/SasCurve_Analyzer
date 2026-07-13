from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

import pandas as pd

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_import import import_in_situ_series, natural_sort_key
from app.core.data_model import CurveData


SUPPORTED_CURVE_EXTENSIONS = {".csv", ".txt", ".dat"}


@dataclass
class BatchInputCollection:
    curves: list[CurveData]
    manifest: list[dict[str, Any]]
    failed_inputs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    import_summary: dict[str, Any] = field(default_factory=dict)


def discover_curve_files(input_dir: str | Path) -> list[Path]:
    """Return supported calibrated 1D curve files in natural filename order."""
    root = Path(input_dir)
    files = [
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_CURVE_EXTENSIONS
    ]
    return sorted(files, key=natural_sort_key)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a file hash incrementally without changing the source file."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata_table(path: str | Path) -> pd.DataFrame:
    """Read the supported, pre-Plan-4 CSV metadata sidecar into memory."""
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError(f"Unsupported metadata file before Plan 4: {source.suffix}")


def _metadata_key(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    key = str(value).strip()
    return key or None


def _build_metadata_rows(
    metadata: pd.DataFrame,
    match_column: str,
) -> dict[str, tuple[int, dict[str, Any]]]:
    if match_column not in metadata.columns:
        raise ValueError(f"Metadata match column not found: {match_column}")

    rows: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_index, row in metadata.iterrows():
        key = _metadata_key(row[match_column])
        if key is None:
            continue
        normalized_row_index = int(row_index)
        if key in rows:
            previous_row_index, _ = rows[key]
            raise ValueError(
                f"Duplicate metadata match key '{key}' in column '{match_column}' "
                f"at rows {previous_row_index} and {normalized_row_index}."
            )
        rows[key] = (normalized_row_index, row.to_dict())
    return rows


def _build_manifest_entry(path: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    entry: dict[str, Any] = {
        "source_file": path.name,
        "source_path": str(path.absolute()),
        "size_bytes": None,
        "modified_time": None,
        "sha256": None,
        "manifest_status": "success",
        "manifest_error": None,
    }
    try:
        resolved_path = path.resolve()
        source_stat = resolved_path.stat()
        entry.update(
            {
                "source_path": str(resolved_path),
                "size_bytes": source_stat.st_size,
                "modified_time": source_stat.st_mtime,
                "sha256": sha256_file(resolved_path),
            }
        )
        return entry, None
    except OSError as exc:
        error = str(exc)
        entry["manifest_status"] = "failed"
        entry["manifest_error"] = error
        return entry, {"file": path.name, "stage": "manifest", "error": error}


def collect_batch_inputs(input_dir: str | Path, config: AutoBatchConfig) -> BatchInputCollection:
    """Import calibrated curves and merge optional CSV metadata in memory only."""
    paths = discover_curve_files(input_dir)
    metadata_source_path = None if config.metadata_path is None else Path(config.metadata_path).absolute()
    if metadata_source_path is not None:
        paths = [path for path in paths if path.absolute() != metadata_source_path]
    # Apply the user-approved effective q range at ingestion time.  The
    # original files are only read; the returned CurveData objects contain
    # the selected q/I pairs and retain filter diagnostics in metadata.
    q_low, q_high = config.effective_q_range
    imported = import_in_situ_series(
        paths,
        limit_q_range=True,
        q_min=q_low,
        q_max=q_high,
    )

    metadata = None if config.metadata_path is None else load_metadata_table(config.metadata_path)
    metadata_sha256: str | None = None
    metadata_rows: dict[str, tuple[int, dict[str, Any]]] = {}
    if metadata is not None:
        try:
            metadata_sha256 = sha256_file(metadata_source_path)
        except OSError as exc:
            raise RuntimeError(
                f"Could not calculate SHA-256 for metadata sidecar '{metadata_source_path}': {exc}"
            ) from exc
        metadata_rows = _build_metadata_rows(metadata, config.metadata_match_column)

    warnings = list(imported.warnings)
    matched_metadata_keys: set[str] = set()
    reference_pattern = config.reference_filename_pattern.strip().lower()
    series_frame_indices: list[int] = []
    reference_names: list[str] = []
    for curve in imported.imported_curves:
        curve_file = Path(curve.source_file or "").name
        key = _metadata_key(curve_file)
        is_reference = bool(reference_pattern and reference_pattern in curve_file.lower())
        curve.metadata["sequence_role"] = "reference" if is_reference else "series"
        curve.metadata["is_reference"] = is_reference
        if is_reference:
            reference_names.append(curve_file)
        else:
            raw_frame = curve.metadata.get("frame_index")
            try:
                frame_index = int(raw_frame)
            except (TypeError, ValueError, OverflowError):
                match = re.search(r"_(\d{5})_", curve_file)
                frame_index = int(match.group(1)) if match else 0
            if frame_index > 0:
                curve.metadata["frame_index"] = frame_index
                series_frame_indices.append(frame_index)
        if config.q_unit_override:
            curve.q_unit = config.q_unit_override
            curve.metadata["q_unit_source"] = "batch_config_override"
        if config.intensity_unit_override:
            curve.intensity_unit = config.intensity_unit_override
            curve.metadata["intensity_unit_source"] = "batch_config_override"
        if metadata is not None:
            curve.metadata["metadata_match_status"] = "no_matching_row"
            if key in metadata_rows:
                row_index, row_values = metadata_rows[key]
                # Preserve batch role / frame fields after sidecar merge so a
                # metadata column cannot silently reclassify references.
                protected_role = {
                    "sequence_role": curve.metadata.get("sequence_role"),
                    "is_reference": curve.metadata.get("is_reference"),
                    "frame_index": curve.metadata.get("frame_index"),
                }
                curve.metadata.update(row_values)
                for field_name, field_value in protected_role.items():
                    if field_value is not None:
                        curve.metadata[field_name] = field_value
                curve.metadata["metadata_source"] = str(metadata_source_path)
                curve.metadata["metadata_sha256"] = metadata_sha256
                curve.metadata["metadata_match_column"] = config.metadata_match_column
                curve.metadata["metadata_match_key"] = key
                curve.metadata["metadata_row_index"] = row_index
                curve.metadata["metadata_match_status"] = "matched"
                matched_metadata_keys.add(key)
            else:
                warnings.append(
                    f"Curve '{curve_file}' has no matching metadata row in column "
                    f"'{config.metadata_match_column}'."
                )

    for key, (row_index, _) in metadata_rows.items():
        if key not in matched_metadata_keys:
            warnings.append(
                f"Metadata key '{key}' in column '{config.metadata_match_column}' "
                "did not match an imported curve."
            )

    manifest: list[dict[str, Any]] = []
    failed_inputs = list(imported.failed_files)
    for path in paths:
        entry, manifest_failure = _build_manifest_entry(path)
        manifest.append(entry)
        if manifest_failure is not None:
            failed_inputs.append(manifest_failure)

    import_summary = dict(imported.import_summary)
    unique_frames = sorted(set(series_frame_indices))
    missing_frames = (
        sorted(set(range(unique_frames[0], unique_frames[-1] + 1)) - set(unique_frames))
        if unique_frames
        else []
    )
    import_summary.update(
        {
            "series_curve_count": len(series_frame_indices),
            "reference_curve_count": len(reference_names),
            "reference_curve_names": reference_names,
            "series_frame_min": unique_frames[0] if unique_frames else None,
            "series_frame_max": unique_frames[-1] if unique_frames else None,
            "missing_series_frames": missing_frames,
        }
    )

    return BatchInputCollection(
        curves=imported.imported_curves,
        manifest=manifest,
        failed_inputs=failed_inputs,
        warnings=warnings,
        import_summary=import_summary,
    )
