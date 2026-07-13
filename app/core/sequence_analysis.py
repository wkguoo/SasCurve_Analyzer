"""Read-only sequence summaries for one-material in-situ SAS batches."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig
from app.core.data_model import CurveData


def _finite_number(value: object) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _ordered_curves(curves: Sequence[CurveData], axis_name: str | None) -> tuple[list[CurveData], list[float], str]:
    candidates = [axis_name] if axis_name else ["frame_index", "sequence_order"]
    chosen = next(
        (name for name in candidates if name and all(_finite_number(c.metadata.get(name)) is not None for c in curves)),
        "sequence_order",
    )
    indexed = []
    for position, curve in enumerate(curves):
        value = _finite_number(curve.metadata.get(chosen))
        indexed.append((float(position) if value is None else value, position, curve))
    indexed.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in indexed], [row[0] for row in indexed], chosen


def _parameter_rows(
    curves: Sequence[CurveData], axes: Sequence[float], analyses: Sequence[AnalysisEnvelope]
) -> list[dict[str, Any]]:
    locations = {curve.curve_id: (index, axes[index], curve.name) for index, curve in enumerate(curves)}
    rows: list[dict[str, Any]] = []
    accepted = {AnalysisStatus.SUCCESS, AnalysisStatus.ASSUMPTION_DEPENDENT}
    for envelope in analyses:
        if envelope.curve_id not in locations or envelope.status not in accepted:
            continue
        frame, axis, curve_name = locations[envelope.curve_id]
        model_name = next((str(p.value) for p in envelope.parameters if p.name == "model_name" and p.value), None)
        range_track = str(getattr(envelope, "range_track", None) or "effective")
        for parameter in envelope.parameters:
            value = _finite_number(parameter.value)
            if value is None:
                continue
            rows.append(
                {
                    "frame": frame,
                    "axis_value": axis,
                    "curve_id": envelope.curve_id,
                    "curve_name": curve_name,
                    "analysis_type": envelope.analysis_type,
                    "analysis_id": envelope.analysis_id,
                    "range_track": range_track,
                    "model_name": model_name,
                    "parameter": parameter.name,
                    "value": value,
                    "unit": parameter.unit,
                    "status": envelope.status.value,
                }
            )
    return rows


def _trajectory_group_key(row: Mapping[str, Any]) -> tuple[str, str, str | None, str]:
    """Group trajectories by method, track, model, and parameter.

    Dual-track batches emit separate adaptive/common envelopes for the same
    method. Mixing tracks would double-count each frame and create false jumps.
    """

    return (
        str(row.get("analysis_type") or ""),
        str(row.get("range_track") or "effective"),
        row.get("model_name"),
        str(row.get("parameter") or ""),
    )


def _change_flags(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_trajectory_group_key(row)].append(row)
    flags: list[dict[str, Any]] = []
    for key, series in grouped.items():
        series.sort(key=lambda row: (row["frame"], str(row.get("analysis_id") or "")))
        # One value per frame within a track (keep first stable analysis_id).
        unique_frames: list[dict[str, Any]] = []
        seen_frames: set[object] = set()
        for row in series:
            frame = row["frame"]
            if frame in seen_frames:
                continue
            seen_frames.add(frame)
            unique_frames.append(row)
        series = unique_frames
        if len(series) < 4:
            continue
        differences = np.diff([row["value"] for row in series])
        median = float(np.median(differences))
        mad = float(np.median(np.abs(differences - median)))
        deviations = np.abs(differences - median)
        if mad <= np.finfo(float).eps:
            robust_z = np.where(deviations > np.finfo(float).eps * max(1.0, abs(median)), np.inf, 0.0)
        else:
            robust_z = 0.67448975 * deviations / mad
        for index in np.flatnonzero(robust_z >= 3.5):
            row = series[int(index) + 1]
            flags.append(
                {
                    "frame": row["frame"],
                    "axis_value": row["axis_value"],
                    "curve_id": row["curve_id"],
                    "analysis_type": key[0],
                    "range_track": key[1],
                    "model_name": key[2],
                    "parameter": key[3],
                    "delta": float(differences[index]),
                    "robust_z": float(robust_z[index]),
                    "interpretation": "review_candidate_not_phase_transition_proof",
                }
            )
    return flags


def _reference_rows(curves: Sequence[CurveData], axes: Sequence[float], config: AutoBatchConfig) -> tuple[list[dict[str, Any]], list[str]]:
    if not curves:
        return [], []
    by_id = {curve.curve_id: curve for curve in curves}
    selected = by_id.get(config.reference_curve_id or "")
    if config.reference_mode == "selected" and selected is None:
        return [], ["Selected reference curve was not found; reference comparison was skipped."]
    rows: list[dict[str, Any]] = []
    for index, curve in enumerate(curves):
        reference = curves[0] if config.reference_mode == "first" else curves[max(0, index - 1)]
        if config.reference_mode == "selected":
            reference = selected
        assert reference is not None
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        rq = np.asarray(reference.q, dtype=float)
        ri = np.asarray(reference.intensity, dtype=float)
        valid_curve = np.isfinite(q) & np.isfinite(intensity)
        valid_reference = np.isfinite(rq) & np.isfinite(ri)
        if np.count_nonzero(valid_curve) < 2 or np.count_nonzero(valid_reference) < 2:
            continue
        q, intensity = q[valid_curve], intensity[valid_curve]
        rq, ri = rq[valid_reference], ri[valid_reference]
        effective_low, effective_high = config.effective_q_range
        low = max(effective_low, float(np.nanmin(q)), float(np.nanmin(rq)))
        high = min(effective_high, float(np.nanmax(q)), float(np.nanmax(rq)))
        mask = np.isfinite(q) & np.isfinite(intensity) & (q >= low) & (q <= high)
        if np.count_nonzero(mask) < 2 or not low < high:
            continue
        q_use, i_use = q[mask], intensity[mask]
        curve_order = np.argsort(q_use, kind="stable")
        q_use, i_use = q_use[curve_order], i_use[curve_order]
        order = np.argsort(rq)
        ref_interp = np.interp(q_use, rq[order], ri[order])
        finite = np.isfinite(ref_interp)
        if np.count_nonzero(finite) < 2:
            continue
        delta = i_use[finite] - ref_interp[finite]
        denominator = float(np.trapezoid(np.abs(ref_interp[finite]), q_use[finite]))
        rows.append(
            {
                "frame": index,
                "axis_value": axes[index],
                "curve_id": curve.curve_id,
                "reference_curve_id": reference.curve_id,
                "overlap_q_start": low,
                "overlap_q_end": high,
                "point_count": int(np.count_nonzero(finite)),
                "rmse": float(np.sqrt(np.mean(delta**2))),
                "mae": float(np.mean(np.abs(delta))),
                "relative_absolute_area": None if denominator <= 0 else float(np.trapezoid(np.abs(delta), q_use[finite]) / denominator),
            }
        )
    return rows, []


def _linear_trends(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_trajectory_group_key(row)].append(row)
    output = []
    for key, series in grouped.items():
        series = sorted(series, key=lambda row: (row["frame"], str(row.get("analysis_id") or "")))
        unique_frames: list[dict[str, Any]] = []
        seen_frames: set[object] = set()
        for row in series:
            frame = row["frame"]
            if frame in seen_frames:
                continue
            seen_frames.add(frame)
            unique_frames.append(row)
        series = unique_frames
        if len(series) < 3:
            continue
        x = np.asarray([row["axis_value"] for row in series], dtype=float)
        y = np.asarray([row["value"] for row in series], dtype=float)
        if np.unique(x).size < 2:
            continue
        slope, intercept = np.polyfit(x, y, 1)
        fitted = slope * x + intercept
        ss_total = float(np.sum((y - np.mean(y)) ** 2))
        r2 = None if ss_total <= 0 else float(1.0 - np.sum((y - fitted) ** 2) / ss_total)
        output.append(
            {
                "analysis_type": key[0],
                "range_track": key[1],
                "model_name": key[2],
                "parameter": key[3],
                "slope": float(slope),
                "intercept": float(intercept),
                "R2": r2,
                "point_count": len(series),
                "interpretation": "descriptive_linear_trend_not_kinetic_mechanism",
            }
        )
    return output


def _exploratory_statistics(curves: Sequence[CurveData], axes: Sequence[float], config: AutoBatchConfig) -> dict[str, Any]:
    if len(curves) < 2:
        return {"status": "not_applicable", "reason": "at_least_two_curves_required"}
    effective_low, effective_high = config.effective_q_range
    prepared: list[tuple[np.ndarray, np.ndarray]] = []
    for curve in curves:
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        valid = (
            np.isfinite(q)
            & np.isfinite(intensity)
            & (intensity > 0)
            & (q >= effective_low)
            & (q <= effective_high)
        )
        if np.count_nonzero(valid) < 2:
            return {
                "status": "not_applicable",
                "reason": "at_least_two_finite_positive_points_per_curve_required",
            }
        q, intensity = q[valid], intensity[valid]
        order = np.argsort(q, kind="stable")
        prepared.append((q[order], intensity[order]))
    q_low = max(float(q[0]) for q, _ in prepared)
    q_high = min(float(q[-1]) for q, _ in prepared)
    if not q_low < q_high:
        return {"status": "not_applicable", "reason": "no_common_q_overlap"}
    grid = np.linspace(q_low, q_high, 128)
    matrix = []
    for q, intensity in prepared:
        values = np.interp(grid, q, intensity)
        matrix.append(np.log(np.maximum(values, np.finfo(float).tiny)))
    data = np.asarray(matrix)
    standardized = data - np.mean(data, axis=0)
    scale = np.std(standardized, axis=0)
    standardized[:, scale > 0] /= scale[scale > 0]
    u, singular, _ = np.linalg.svd(standardized, full_matrices=False)
    count = min(config.pca_components, len(curves), singular.size)
    scores = u[:, :count] * singular[:count]
    variance = singular**2
    explained = variance[:count] / np.sum(variance) if np.sum(variance) > 0 else np.zeros(count)
    cluster_count = min(config.cluster_count, len(curves))
    rng = np.random.default_rng(config.random_seed)
    centers = scores[rng.choice(len(curves), cluster_count, replace=False)].copy()
    labels = np.zeros(len(curves), dtype=int)
    for _ in range(50):
        new_labels = np.argmin(np.linalg.norm(scores[:, None, :] - centers[None, :, :], axis=2), axis=1)
        if np.array_equal(new_labels, labels) and _:
            break
        labels = new_labels
        for label in range(cluster_count):
            members = scores[labels == label]
            if len(members):
                centers[label] = np.mean(members, axis=0)
    return {"status": "success", "q_grid": grid.tolist(), "explained_variance_ratio": explained.tolist(), "scores": [{"frame": i, "axis_value": axes[i], "curve_id": curve.curve_id, "components": scores[i].tolist(), "cluster": int(labels[i])} for i, curve in enumerate(curves)], "interpretation": "exploratory_pattern_not_phase_or_mechanism_proof"}


def analyze_sequence(curves: Sequence[CurveData], analyses: Sequence[AnalysisEnvelope], config: AutoBatchConfig) -> dict[str, Any]:
    """Create JSON-safe sequence summaries without mutating curves or analyses."""

    ordered, axes, axis_name = _ordered_curves(curves, config.sequence_axis)
    rows = _parameter_rows(ordered, axes, analyses)
    references, warnings = _reference_rows(ordered, axes, config)
    result: dict[str, Any] = {
        "status": "success" if ordered else "not_applicable",
        "sequence_axis": axis_name,
        "effective_q_range": list(config.effective_q_range),
        "frame_table": [{"frame": i, "axis_value": axes[i], "curve_id": curve.curve_id, "curve_name": curve.name} for i, curve in enumerate(ordered)],
        "parameter_trajectories": rows,
        "reference_comparisons": references,
        "change_flags": _change_flags(rows),
        "linear_trends": _linear_trends(rows) if config.enable_kinetics else [],
        "exploratory_statistics": _exploratory_statistics(ordered, axes, config) if config.enable_exploratory_statistics else {"status": "not_enabled"},
        "warnings": warnings,
        "interpretation": "sequence_association_not_causality_or_phase_transition_proof",
    }
    return result


__all__ = ["analyze_sequence"]
