from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.core.data_model import CurveData, CurveGroup, HistoryRecord
from app.core.io import apply_q_import_range_filter, QImportRangeFilterError, read_table
from app.core.project import ProjectState
from app.core.transforms import convert_q_unit, normalize_q_unit
from app.core.uncertainty import input_uncertainty_kind, prepare_input_uncertainty


Q_CANDIDATES = ("q", "Q", "q_A_inv", "q_A^-1", "q_inv_A", "q_nm_inv", "q_nm^-1", "q_inv_nm")
I_CANDIDATES = ("I", "intensity", "Intensity", "I(q)", "intensity_cm_inv", "I_cm_inv", "I_cm^-1", "mean_intensity", "I_abs_cm_inv", "I_abs_cm^-1", "I_abs_cm-1")
ERROR_CANDIDATES = ("error", "sigma", "sigma_I", "err", "uncertainty", "dI", "d_i", "std_intensity", "std")


@dataclass
class ColumnInference:
    q_column: str
    intensity_column: str
    error_column: str | None
    q_unit: str
    intensity_unit: str
    warnings: list[str] = field(default_factory=list)
    uncertainty_kind: str = "missing"


@dataclass
class BatchImportResult:
    imported_curves: list[CurveData] = field(default_factory=list)
    failed_files: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    import_summary: dict[str, Any] = field(default_factory=dict)


def natural_sort_key(value: str | Path) -> list[Any]:
    text = Path(value).as_posix() if isinstance(value, Path) else str(value).replace("\\", "/")
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def parse_sequence_metadata(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    stem = file_path.stem
    # Numeric frame identifiers are whole underscore-delimited tokens. This
    # avoids reading alloy names such as Ti15 or unit suffixes such as cm-1 as
    # frame numbers.
    matches = list(re.finditer(r"(?<![^_])(\d+)(?=_|$)", stem))
    if len(matches) != 1:
        series_id = stem.split("_")[0] if "_" in stem else stem
        warning = None
        if len(matches) > 1:
            warning = "multiple standalone numeric tokens found; frame_index was left unset."
        return {
            "series_id": series_id,
            "frame_index": None,
            "frame_label": None,
            "source_stem": stem,
            "import_mode": "batch_in_situ_series",
            "sequence_parse_warning": warning,
        }
    match = matches[0]
    frame_label = match.group(1)
    prefix = stem[: match.start()].strip("_")
    series_id = prefix if prefix else stem[:match.start()].rstrip("_")
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
    kind = input_uncertainty_kind(error_column, column_list)
    uncertainty_warnings = []
    if kind in {"series_std", "unknown"}:
        uncertainty_warnings.append(f"Column '{error_column}' is {kind}, not measured pointwise uncertainty; retained as metadata, not fitting sigma.")
    return ColumnInference(
        q_column=q_column,
        intensity_column=intensity_column,
        error_column=error_column,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        warnings=[*q_warnings, *intensity_warnings, *uncertainty_warnings],
        uncertainty_kind=kind,
    )


def import_in_situ_series(
    paths: Iterable[str | Path],
    *,
    limit_q_range: bool = False,
    q_min: float | None = None,
    q_max: float | None = None,
    source_q_unit_override: str | None = None,
    source_intensity_unit_override: str | None = None,
    target_q_unit: str | None = None,
) -> BatchImportResult:
    file_paths = sorted([Path(path) for path in paths], key=natural_sort_key)
    result = BatchImportResult()
    first_columns: ColumnInference | None = None
    series_id: str | None = None
    raw_total_points = 0
    imported_total_points = 0
    filtered_out_total_points = 0
    created_curve_total_points = 0
    failed_q_range_would_import_total_points = 0

    def accumulate_q_filter_diagnostics(diagnostics: dict[str, Any]) -> None:
        nonlocal raw_total_points, imported_total_points, filtered_out_total_points
        raw_total_points += int(diagnostics.get("raw_point_count", 0))
        imported_total_points += int(diagnostics.get("imported_point_count", 0))
        filtered_out_total_points += int(diagnostics.get("filtered_out_point_count", 0))

    for sequence_order, file_path in enumerate(file_paths):
        try:
            df = read_table(file_path)
            columns = infer_curve_columns(df.columns)
            if first_columns is None:
                first_columns = columns
            metadata = parse_sequence_metadata(file_path)
            if metadata["frame_index"] is None:
                warning = metadata.get("sequence_parse_warning") or "no standalone numeric frame token was found."
                result.warnings.append(f"{file_path.name}: {warning}")
            metadata["sequence_order"] = sequence_order
            if series_id is None:
                series_id = metadata.get("series_id")
            source_q_unit = source_q_unit_override or columns.q_unit
            source_intensity_unit = source_intensity_unit_override or columns.intensity_unit
            canonical_source_q_unit = normalize_q_unit(source_q_unit)
            destination_q_unit = normalize_q_unit(target_q_unit or canonical_source_q_unit)
            q_column = pd.to_numeric(df[columns.q_column], errors="coerce").to_numpy(dtype=float)
            intensity = pd.to_numeric(df[columns.intensity_column], errors="coerce").to_numpy(dtype=float)
            error = (
                None
                if columns.error_column is None
                else pd.to_numeric(df[columns.error_column], errors="coerce").to_numpy(dtype=float)
            )
            if q_column.shape != intensity.shape:
                raise ValueError("q and intensity columns must have the same length.")
            if error is not None and error.shape != q_column.shape:
                raise ValueError("error column must have the same length as q.")

            source_curve = CurveData.create(
                name=file_path.stem,
                q=q_column,
                intensity=intensity,
                error=error,
                q_unit=canonical_source_q_unit,
                intensity_unit=source_intensity_unit,
                source_file=file_path,
                metadata=metadata,
                processing_history=[
                    {
                        "action": "import",
                        "source_file": str(file_path),
                        "q_column": columns.q_column,
                        "intensity_column": columns.intensity_column,
                        "error_column": columns.error_column,
                    }
                ],
            )
            converted_curve = convert_q_unit(source_curve, destination_q_unit)
            factor = 1.0 if canonical_source_q_unit == destination_q_unit else (0.1 if canonical_source_q_unit == "nm^-1" else 10.0)
            metadata.update(
                {
                    "source_q_unit": source_q_unit,
                    "source_intensity_unit": source_intensity_unit,
                    "q_unit_source": "batch_config_override" if source_q_unit_override else "default_assumption" if _infer_q_unit(columns.q_column)[1] else "column_header",
                    "intensity_unit_source": "batch_config_override" if source_intensity_unit_override else "default_assumption" if _infer_intensity_unit(columns.intensity_column)[1] else "column_header",
                    "q_unit_target": destination_q_unit,
                    "q_unit_conversion_factor": factor,
                }
            )
            q, intensity, error, q_filter_diagnostics = apply_q_import_range_filter(
                converted_curve.q,
                converted_curve.intensity,
                converted_curve.error,
                limit_q_range=limit_q_range,
                q_min=q_min,
                q_max=q_max,
            )
            if limit_q_range:
                metadata["import_q_range_filter"] = {
                    "enabled": True,
                    "q_min": q_filter_diagnostics["q_range_filter_min"],
                    "q_max": q_filter_diagnostics["q_range_filter_max"],
                    "raw_point_count": q_filter_diagnostics["raw_point_count"],
                    "finite_qi_point_count": q_filter_diagnostics["finite_qi_point_count"],
                    "imported_point_count": q_filter_diagnostics["imported_point_count"],
                    "filtered_out_point_count": q_filter_diagnostics["filtered_out_point_count"],
                    "q_min_imported": q_filter_diagnostics["q_min_imported"],
                    "q_max_imported": q_filter_diagnostics["q_max_imported"],
                }
                converted_curve.processing_history.append(
                    {
                        "action": "filter_q_range",
                        "q_unit": destination_q_unit,
                        "q_range_filter_enabled": True,
                        "q_range_filter_min": q_filter_diagnostics["q_range_filter_min"],
                        "q_range_filter_max": q_filter_diagnostics["q_range_filter_max"],
                        "raw_point_count": q_filter_diagnostics["raw_point_count"],
                        "finite_qi_point_count": q_filter_diagnostics["finite_qi_point_count"],
                        "imported_point_count": q_filter_diagnostics["imported_point_count"],
                        "filtered_out_point_count": q_filter_diagnostics["filtered_out_point_count"],
                    }
                )
            error = prepare_input_uncertainty(error, columns.error_column, df.columns, metadata)
            curve = CurveData.create(
                name=file_path.stem,
                q=q,
                intensity=intensity,
                error=error,
                q_unit=destination_q_unit,
                intensity_unit=source_intensity_unit,
                source_file=file_path,
                metadata=metadata,
                processing_history=converted_curve.processing_history,
            )
            result.imported_curves.append(curve)
            result.warnings.extend(columns.warnings)
            q_filter = curve.metadata.get("import_q_range_filter")
            if q_filter:
                accumulate_q_filter_diagnostics(q_filter)
            else:
                raw_total_points += int(curve.q.size)
                imported_total_points += int(curve.q.size)
            created_curve_total_points += int(curve.q.size)
        except QImportRangeFilterError as exc:
            diagnostics = exc.diagnostics
            accumulate_q_filter_diagnostics(diagnostics)
            failed_q_range_would_import_total_points += int(diagnostics.get("imported_point_count", 0))
            result.failed_files.append(
                {
                    "file": file_path.name,
                    "error": f"q range filter failed for file {file_path.name}: {exc}",
                    "failure_type": "q_range_filter_too_few_points",
                    "q_range_filter_enabled": str(diagnostics.get("q_range_filter_enabled")),
                    "q_range_filter_min": str(diagnostics.get("q_range_filter_min")),
                    "q_range_filter_max": str(diagnostics.get("q_range_filter_max")),
                    "raw_point_count": str(diagnostics.get("raw_point_count")),
                    "would_import_point_count": str(diagnostics.get("imported_point_count")),
                    "filtered_out_point_count": str(diagnostics.get("filtered_out_point_count")),
                }
            )
        except Exception as exc:
            result.failed_files.append({"file": file_path.name, "error": str(exc)})

    result.import_summary = {
        "total_files": len(file_paths),
        "imported_count": len(result.imported_curves),
        "failed_count": len(result.failed_files),
        "q_column": None if first_columns is None else first_columns.q_column,
        "intensity_column": None if first_columns is None else first_columns.intensity_column,
        "error_column": None if first_columns is None else first_columns.error_column,
        "q_unit": None if not result.imported_curves else result.imported_curves[0].q_unit,
        "intensity_unit": None if not result.imported_curves else result.imported_curves[0].intensity_unit,
        "source_q_unit": None if first_columns is None else (source_q_unit_override or first_columns.q_unit),
        "source_intensity_unit": None if first_columns is None else (source_intensity_unit_override or first_columns.intensity_unit),
        "series_id": series_id,
        "q_range_filter_enabled": bool(limit_q_range),
        "q_range_filter_min": q_min if limit_q_range else None,
        "q_range_filter_max": q_max if limit_q_range else None,
        "raw_total_points": raw_total_points,
        "imported_total_points": imported_total_points,
        "filtered_out_total_points": filtered_out_total_points,
        "created_curve_total_points": created_curve_total_points,
        "failed_q_range_would_import_total_points": failed_q_range_would_import_total_points,
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
