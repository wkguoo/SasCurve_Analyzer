from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData, CurveGroup, HistoryRecord, utc_now_iso


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
    reference = curves[0].q
    return all(curve.q.shape == reference.shape and np.allclose(curve.q, reference) for curve in curves[1:])


def average_replicates(curves: list[CurveData], *, interpolate: bool = True, name: str = "average_curve") -> tuple[CurveData, HistoryRecord]:
    if len(curves) < 2:
        raise ValueError("At least two curves are required for replicate averaging.")

    warnings: list[str] = []
    if q_grids_match(curves):
        q_grid = curves[0].q.copy()
        intensities = np.vstack([curve.intensity for curve in curves])
        errors = [curve.error for curve in curves]
        interpolation_method = "none"
    else:
        if not interpolate:
            raise ValueError("q grids differ; set interpolate=True to average on a common q grid.")
        q_grid = _common_q_grid(curves)
        intensities = np.vstack([np.interp(q_grid, curve.q, curve.intensity) for curve in curves])
        errors = [None if curve.error is None else np.interp(q_grid, curve.q, curve.error) for curve in curves]
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

