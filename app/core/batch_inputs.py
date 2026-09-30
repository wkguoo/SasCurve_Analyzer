from __future__ import annotations

import os
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def _resolve_input_paths(
    input_dir: str | Path,
    input_paths: Sequence[str | Path] | None,
) -> tuple[Path, list[Path]]:
    root = Path(input_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"Input directory does not exist or is not a directory: {root}")
    if input_paths is None:
        candidates = [path.resolve() for path in discover_curve_files(root)]
    else:
        candidates = []
        seen: set[str] = set()
        for supplied in input_paths:
            candidate = Path(supplied)
            resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Input path must be within input_dir: {supplied}") from exc
            if not resolved.is_file():
                raise ValueError(f"Input path is not a file: {supplied}")
            if resolved.suffix.lower() not in SUPPORTED_CURVE_EXTENSIONS:
                raise ValueError(f"Unsupported curve file extension: {resolved.suffix}")
            key = os.path.normcase(str(resolved))
            if key in seen:
                raise ValueError(f"Duplicate input path: {supplied}")
            seen.add(key)
            candidates.append(resolved)

    candidates.sort(key=lambda path: natural_sort_key(path.relative_to(root).as_posix()))
    return root, candidates


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
        return pd.read_csv(source, dtype={"sample_id": str, "source_file": str}, keep_default_na=False)
    raise ValueError(f"Unsupported metadata file before Plan 4: {source.suffix}")


def _metadata_key(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    key = str(value).strip().replace("\\", "/")
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


def _build_manifest_entry(path: Path, root: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    relative_path = path.relative_to(root).as_posix()
    entry: dict[str, Any] = {
        "source_file": path.name,
        "source_relative_path": relative_path,
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
        return entry, {"file": relative_path, "stage": "manifest", "error": error}


_RESERVED_METADATA_KEYS = {
    "curve_id",
    "source_file",
    "source_path",
    "source_relative_path",
    "source_stem",
    "series_id",
    "frame_label",
    "identity_source",
    "sequence_order",
    "import_mode",
    "source_q_unit",
    "source_intensity_unit",
    "q_unit",
    "intensity_unit",
    "q_unit_source",
    "intensity_unit_source",
    "q_unit_target",
    "q_unit_conversion_factor",
    "source_sha256",
    "source_hash",
    "sha256",
    "size_bytes",
    "modified_time",
    "manifest_status",
    "manifest_error",
    "import_q_range_filter",
    "validity_checks",
    "validation_status",
    "validation_warnings",
    "metadata_source",
    "metadata_sha256",
    "metadata_match_column",
    "metadata_match_key",
    "metadata_row_index",
    "metadata_match_status",
}


def _is_reserved_metadata_key(value: Any) -> bool:
    key = str(value).casefold()
    return (
        key in _RESERVED_METADATA_KEYS
        or key.startswith(("source_", "manifest_", "metadata_", "validation_", "validity_"))
        or key.endswith(("_unit", "_units", "_sha256", "_hash"))
    )


def collect_batch_inputs(
    input_dir: str | Path,
    config: AutoBatchConfig,
    *,
    input_paths: Sequence[str | Path] | None = None,
    input_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> BatchInputCollection:
    """Import calibrated curves and merge optional CSV metadata in memory only."""
    root, paths = _resolve_input_paths(input_dir, input_paths)
    metadata_source_path = None if config.metadata_path is None else Path(config.metadata_path).resolve()
    if metadata_source_path is not None:
        paths = [path for path in paths if path != metadata_source_path]
    relative_paths = {path.relative_to(root).as_posix() for path in paths}
    trusted_identity_keys = {"sample_id", "series_id", "frame_index", "frame_label", "identity_source"}
    if input_metadata is not None:
        unknown_paths = sorted(set(input_metadata) - relative_paths)
        if unknown_paths:
            raise ValueError(f"Identity metadata contains paths outside the selected inputs: {unknown_paths}")
        for relative_path, values in input_metadata.items():
            invalid_keys = sorted(set(values) - trusted_identity_keys)
            if invalid_keys:
                raise ValueError(
                    f"Identity metadata for '{relative_path}' contains unsupported keys: {invalid_keys}"
                )
    # Apply the user-approved effective q range at ingestion time.  The
    # source q unit is converted to canonical A^-1 before comparing to the
    # configured bounds, which are always expressed in A^-1.
    q_low, q_high = config.effective_q_range
    imported = import_in_situ_series(
        paths,
        limit_q_range=True,
        q_min=q_low,
        q_max=q_high,
        source_q_unit_override=config.q_unit_override,
        source_intensity_unit_override=config.intensity_unit_override,
        target_q_unit="A^-1",
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
    basename_counts: dict[str, int] = {}
    for path in paths:
        basename_counts[path.name] = basename_counts.get(path.name, 0) + 1
    for curve in imported.imported_curves:
        curve_path = Path(curve.source_file or "").resolve()
        relative_path = curve_path.relative_to(root).as_posix()
        curve.metadata.update(
            {
                "source_file": curve_path.name,
                "source_path": str(curve_path),
                "source_relative_path": relative_path,
            }
        )
        if metadata is not None:
            curve.metadata["metadata_match_status"] = "no_matching_row"
            key = relative_path if relative_path in metadata_rows else None
            if key is None and basename_counts.get(curve_path.name) == 1 and curve_path.name in metadata_rows:
                key = curve_path.name
            if key is not None:
                row_index, row_values = metadata_rows[key]
                reserved = sorted(
                    str(column)
                    for column in row_values
                    if _is_reserved_metadata_key(column)
                    and str(column).casefold() != config.metadata_match_column.casefold()
                )
                curve.metadata.update(
                    {
                        column: value
                        for column, value in row_values.items()
                        if not _is_reserved_metadata_key(column)
                    }
                )
                curve.metadata["metadata_source"] = str(metadata_source_path)
                curve.metadata["metadata_sha256"] = metadata_sha256
                curve.metadata["metadata_match_column"] = config.metadata_match_column
                curve.metadata["metadata_match_key"] = key
                curve.metadata["metadata_row_index"] = row_index
                curve.metadata["metadata_match_status"] = "matched"
                matched_metadata_keys.add(key)
                if reserved:
                    warnings.append(
                        f"Metadata row '{key}' attempted to replace reserved provenance or validation "
                        f"fields {reserved}; those fields were ignored."
                    )
            else:
                if curve_path.name in metadata_rows and basename_counts.get(curve_path.name, 0) > 1:
                    warnings.append(
                        f"Curve '{relative_path}' has an ambiguous basename metadata key "
                        f"'{curve_path.name}'; use its relative POSIX path in column "
                        f"'{config.metadata_match_column}'."
                    )
                else:
                    warnings.append(
                        f"Curve '{relative_path}' has no matching metadata row in column "
                        f"'{config.metadata_match_column}'."
                    )
        if input_metadata is not None and relative_path in input_metadata:
            curve.metadata.update(dict(input_metadata[relative_path]))

    for key, (row_index, _) in metadata_rows.items():
        if input_paths is not None and key not in relative_paths and key not in basename_counts:
            continue  # a shared study sidecar also describes other samples
        if key not in matched_metadata_keys:
            warnings.append(
                f"Metadata key '{key}' in column '{config.metadata_match_column}' "
                "did not match an imported curve."
            )

    manifest: list[dict[str, Any]] = []
    failed_inputs = list(imported.failed_files)
    manifest_by_relative_path: dict[str, dict[str, Any]] = {}
    for path in paths:
        entry, manifest_failure = _build_manifest_entry(path, root)
        manifest.append(entry)
        manifest_by_relative_path[entry["source_relative_path"]] = entry
        if manifest_failure is not None:
            failed_inputs.append(manifest_failure)

    for curve in imported.imported_curves:
        entry = manifest_by_relative_path.get(str(curve.metadata.get("source_relative_path")))
        if entry is not None:
            curve.metadata["source_sha256"] = entry["sha256"]

    return BatchInputCollection(
        curves=imported.imported_curves,
        manifest=manifest,
        failed_inputs=failed_inputs,
        warnings=warnings,
        import_summary=dict(imported.import_summary),
    )
