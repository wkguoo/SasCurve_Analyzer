from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from app.core.data_model import CurveData, CurveGroup, HistoryRecord
from app.core.io import load_curve, read_table
from app.core.project import ProjectState


Q_CANDIDATES = ("q", "Q", "q_A_inv", "q_A^-1", "q_inv_A", "q_nm_inv", "q_nm^-1", "q_inv_nm")
I_CANDIDATES = ("I", "intensity", "Intensity", "I(q)", "intensity_cm_inv", "I_cm_inv", "I_cm^-1")
ERROR_CANDIDATES = ("error", "sigma", "err", "std", "uncertainty")


@dataclass
class ColumnInference:
    q_column: str
    intensity_column: str
    error_column: str | None
    q_unit: str
    intensity_unit: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class BatchImportResult:
    imported_curves: list[CurveData] = field(default_factory=list)
    failed_files: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    import_summary: dict[str, Any] = field(default_factory=dict)


def natural_sort_key(value: str | Path) -> list[Any]:
    text = Path(value).name if isinstance(value, Path) else str(value)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def parse_sequence_metadata(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    stem = file_path.stem
    match = re.search(r"_(\d+)_", stem)
    if match is None:
        match = re.search(r"(\d+)", stem)
    if match is None:
        series_id = stem.split("_")[0] if "_" in stem else stem
        return {
            "series_id": series_id,
            "frame_index": None,
            "frame_label": None,
            "source_stem": stem,
            "import_mode": "batch_in_situ_series",
        }
    frame_label = match.group(1)
    prefix = stem[: match.start()].strip("_")
    series_id = prefix.split("_")[0] if prefix else stem.split("_")[0]
    return {
        "series_id": series_id,
        "frame_index": int(frame_label),
        "frame_label": frame_label,
        "source_stem": stem,
        "import_mode": "batch_in_situ_series",
    }


def _find_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    original = [str(column) for column in columns]
    normalized = {column.strip().lower(): column for column in original}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return normalized[key]
    return None


def _infer_q_unit(column: str) -> tuple[str, list[str]]:
    lower = column.lower()
    if "nm" in lower:
        return "nm^-1", []
    if "_a_" in lower or "a_inv" in lower or "a^-1" in lower:
        return "A^-1", []
    return "A^-1", [f"Could not infer q unit from column '{column}'; defaulted to A^-1."]


def _infer_intensity_unit(column: str) -> tuple[str, list[str]]:
    lower = column.lower()
    if "cm" in lower:
        return "cm^-1", []
    return "a.u.", [f"Could not infer intensity unit from column '{column}'; defaulted to a.u."]


def infer_curve_columns(columns: Iterable[str]) -> ColumnInference:
    column_list = [str(column) for column in columns]
    q_column = _find_column(column_list, Q_CANDIDATES)
    intensity_column = _find_column(column_list, I_CANDIDATES)
    error_column = _find_column(column_list, ERROR_CANDIDATES)
    missing = []
    if q_column is None:
        missing.append("q")
    if intensity_column is None:
        missing.append("intensity")
    if missing:
        raise ValueError(f"Could not infer required columns: {', '.join(missing)}. Available columns: {column_list}")
    q_unit, q_warnings = _infer_q_unit(q_column)
    intensity_unit, intensity_warnings = _infer_intensity_unit(intensity_column)
    return ColumnInference(
        q_column=q_column,
        intensity_column=intensity_column,
        error_column=error_column,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        warnings=[*q_warnings, *intensity_warnings],
    )


def import_in_situ_series(paths: Iterable[str | Path]) -> BatchImportResult:
    file_paths = sorted([Path(path) for path in paths], key=natural_sort_key)
    result = BatchImportResult()
    first_columns: ColumnInference | None = None
    series_id: str | None = None

    for sequence_order, file_path in enumerate(file_paths):
        try:
            df = read_table(file_path)
            columns = infer_curve_columns(df.columns)
            if first_columns is None:
                first_columns = columns
            metadata = parse_sequence_metadata(file_path)
            if metadata["frame_index"] is None:
                result.warnings.append(f"{file_path.name}: sequence number could not be parsed from file name.")
            metadata["sequence_order"] = sequence_order
            if series_id is None:
                series_id = metadata.get("series_id")
            curve = load_curve(
                file_path,
                q_column=columns.q_column,
                intensity_column=columns.intensity_column,
                error_column=columns.error_column,
                name=file_path.stem,
                q_unit=columns.q_unit,
                intensity_unit=columns.intensity_unit,
                metadata=metadata,
            )
            result.imported_curves.append(curve)
            result.warnings.extend(columns.warnings)
        except Exception as exc:
            result.failed_files.append({"file": file_path.name, "error": str(exc)})

    result.import_summary = {
        "total_files": len(file_paths),
        "imported_count": len(result.imported_curves),
        "failed_count": len(result.failed_files),
        "q_column": None if first_columns is None else first_columns.q_column,
        "intensity_column": None if first_columns is None else first_columns.intensity_column,
        "error_column": None if first_columns is None else first_columns.error_column,
        "q_unit": None if first_columns is None else first_columns.q_unit,
        "intensity_unit": None if first_columns is None else first_columns.intensity_unit,
        "series_id": series_id,
    }
    return result


def create_in_situ_group(project: ProjectState, result: BatchImportResult) -> tuple[CurveGroup, HistoryRecord]:
    for curve in result.imported_curves:
        project.add_curve(curve)

    series_id = result.import_summary.get("series_id") or "series"
    group = CurveGroup.create(
        name=f"{series_id}_in_situ_series",
        curve_ids=[curve.curve_id for curve in result.imported_curves],
        metadata={
            "group_type": "in_situ_series",
            "series_id": series_id,
            "n_frames": len(result.imported_curves),
            "sort_key": "frame_index",
            "source": "batch_import",
        },
    )
    project.add_group(group)

    record = HistoryRecord.create(
        "batch_import_in_situ_series",
        input_ids=[curve.metadata.get("source_stem", curve.name) for curve in result.imported_curves],
        output_ids=[curve.curve_id for curve in result.imported_curves],
        parameters={**result.import_summary, "sort_mode": "natural_sort/frame_index", "group_id": group.group_id},
        warnings=result.warnings + [f"{item['file']}: {item['error']}" for item in result.failed_files],
    )
    project.add_history_record(record)
    return group, record
