from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.array_utils import sort_arrays_by_q
from app.core.data_model import CurveData, CurveGroup, HistoryRecord, utc_now_iso
from app.core.unit_checks import validate_compatible_curve_units


def create_curve_group(name: str, curves: list[CurveData], metadata: dict | None = None) -> CurveGroup:
    return CurveGroup.create(name=name, curve_ids=[curve.curve_id for curve in curves], metadata=metadata)


def _common_q_grid(curves: list[CurveData]) -> np.ndarray:
    q_min = max(float(np.nanmin(curve.q)) for curve in curves)
    q_max = min(float(np.nanmax(curve.q)) for curve in curves)
    if q_min >= q_max:
        raise ValueError("Curves do not share an overlapping q range.")
    point_count = min(curve.q.size for curve in curves)
    return np.linspace(q_min, q_max, point_count)


def q_grids_match(curves: list[CurveData]) -> bool:
    if not curves:
        return False
    reference = sort_arrays_by_q(curves[0].q)[0]
    return all(curve.q.shape == reference.shape and np.allclose(sort_arrays_by_q(curve.q)[0], reference) for curve in curves[1:])


def build_sequence_index(curves: list[CurveData]) -> list[dict[str, Any]]:
    reference_q = sort_arrays_by_q(curves[0].q)[0] if curves else None
    rows: list[dict[str, Any]] = []
    for project_order, curve in enumerate(curves):
        metadata = curve.metadata or {}
        q_finite = curve.q[np.isfinite(curve.q)]
        warnings: list[str] = []
        if q_finite.size == 0:
            warnings.append("no finite q")
        if reference_q is not None:
            q_sorted = sort_arrays_by_q(curve.q)[0]
            if curve.q.shape != reference_q.shape or not np.allclose(q_sorted, reference_q):
                warnings.append("q grid differs from first curve")
        if np.any(~np.isfinite(curve.intensity)):
            warnings.append("non-finite intensity")
        if np.any(np.isfinite(curve.intensity) & (curve.intensity <= 0)):
            warnings.append("non-positive intensity")

        rows.append(
            {
                "sequence_order": metadata.get("sequence_order", project_order),
                "project_order": project_order,
                "curve_id": curve.curve_id,
                "curve_name": curve.name,
                "source_file": curve.source_file,
                "source_stem": metadata.get("source_stem"),
                "series_id": metadata.get("series_id"),
                "frame_label": metadata.get("frame_label"),
                "frame_index": metadata.get("frame_index"),
                "q_unit": curve.q_unit,
                "intensity_unit": curve.intensity_unit,
                "point_count": int(curve.q.size),
                "q_min": None if q_finite.size == 0 else float(np.min(q_finite)),
                "q_max": None if q_finite.size == 0 else float(np.max(q_finite)),
                "warnings": "OK" if not warnings else " | ".join(warnings),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["sequence_order"] is None,
            row["project_order"] if row["sequence_order"] is None else row["sequence_order"],
            row["project_order"],
        ),
    )


SEQUENCE_INDEX_COLUMNS = [
    "sequence_order",
    "project_order",
    "curve_id",
    "curve_name",
    "source_file",
    "source_stem",
    "series_id",
    "frame_label",
    "frame_index",
    "q_unit",
    "intensity_unit",
    "point_count",
    "q_min",
    "q_max",
    "warnings",
]


def export_sequence_index_csv(curves: list[CurveData], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(build_sequence_index(curves), columns=SEQUENCE_INDEX_COLUMNS).to_csv(target, index=False)
    return target


def average_replicates(curves: list[CurveData], *, interpolate: bool = True, name: str = "average_curve") -> tuple[CurveData, HistoryRecord]:
    if len(curves) < 2:
        raise ValueError("At least two curves are required for replicate averaging.")
    validate_compatible_curve_units(curves, operation="replicate averaging")

    warnings: list[str] = []
    if q_grids_match(curves):
        sorted_inputs = [sort_arrays_by_q(curve.q, curve.intensity) for curve in curves]
        q_grid = sorted_inputs[0][0].copy()
        intensities = np.vstack([intensity for _q, intensity in sorted_inputs])
        errors = [curve.error for curve in curves]
        if all(error is not None for error in errors):
            errors = [sort_arrays_by_q(curve.q, curve.error)[1] for curve in curves]
        interpolation_method = "none"
    else:
        if not interpolate:
            raise ValueError("q grids differ; set interpolate=True to average on a common q grid.")
        q_grid = _common_q_grid(curves)
        sorted_inputs = [sort_arrays_by_q(curve.q, curve.intensity) for curve in curves]
        intensities = np.vstack([np.interp(q_grid, q_sorted, intensity_sorted) for q_sorted, intensity_sorted in sorted_inputs])
        errors = [
            None if curve.error is None else np.interp(q_grid, *sort_arrays_by_q(curve.q, curve.error))
            for curve in curves
        ]
        interpolation_method = "linear"
        warnings.append("q grids differed; curves were linearly interpolated to a common q grid.")

    mean_intensity = np.mean(intensities, axis=0)
    replicate_std = np.std(intensities, axis=0, ddof=1)

    measurement_error = None
    if all(error is not None for error in errors):
        error_stack = np.vstack([error for error in errors if error is not None])
        measurement_error = np.sqrt(np.sum(error_stack**2, axis=0)) / len(curves)
        combined_error = np.sqrt(measurement_error**2 + replicate_std**2)
    else:
        combined_error = replicate_std

    metadata = {
        "parent_ids": [curve.curve_id for curve in curves],
        "replicate_count": len(curves),
        "interpolation_method": interpolation_method,
        "measurement_error_available": measurement_error is not None,
    }
    history_entry = {
        "action": "average_replicates",
        "created_at": utc_now_iso(),
        "parent_ids": metadata["parent_ids"],
        "interpolation_method": interpolation_method,
        "q_min": float(q_grid.min()),
        "q_max": float(q_grid.max()),
        "points": int(q_grid.size),
        "warnings": warnings,
    }
    averaged = CurveData.create(
        name=name,
        q=q_grid,
        intensity=mean_intensity,
        error=combined_error,
        q_unit=curves[0].q_unit,
        intensity_unit=curves[0].intensity_unit,
        metadata=metadata,
        parent_id=curves[0].curve_id,
        processing_history=[history_entry],
    )
    record = HistoryRecord.create(
        "average_replicates",
        input_ids=[curve.curve_id for curve in curves],
        output_ids=[averaged.curve_id],
        parameters={"interpolate": interpolate, "interpolation_method": interpolation_method},
        warnings=warnings,
    )
    return averaged, record

