"""Read-only sequence summaries for one-material in-situ SAS batches."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

import numpy as np

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig
from app.core.data_model import CurveData
from app.core.transforms import normalize_q_unit


_LOCAL_FEATURE_METHODS = {"peaks", "shoulders", "oscillations", "crossover", "lamellar", "local_slope"}


def _finite_number(value: object) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def _axis_values(curves: Sequence[CurveData], axis_name: str) -> tuple[list[float] | None, str | None]:
    values = [_finite_number(curve.metadata.get(axis_name)) for curve in curves]
    if any(value is None for value in values):
        return None, f"Sequence axis '{axis_name}' is missing or nonfinite for one or more curves."
    finite_values = [float(value) for value in values if value is not None]
    if len(set(finite_values)) != len(finite_values):
        return None, f"Sequence axis '{axis_name}' contains duplicate values."
    return finite_values, None


def _ordered_curves(
    curves: Sequence[CurveData], axis_name: str | None
) -> tuple[list[CurveData], list[float | None], str, bool, list[str]]:
    if not curves:
        return [], [], axis_name or "sequence_order", True, []

    warnings: list[str] = []
    if axis_name is not None:
        values, problem = _axis_values(curves, axis_name)
        if problem is not None:
            warnings.append(problem + " Numeric trends and change flags were skipped.")
            warnings.append("Curves retain source order; no alternate axis was substituted.")
            return list(curves), [None] * len(curves), axis_name, False, warnings
        indexed = sorted(zip(values or [], range(len(curves)), curves), key=lambda row: (row[0], row[1]))
        return [row[2] for row in indexed], [row[0] for row in indexed], axis_name, True, warnings

    for candidate in ("frame_index", "sequence_order"):
        values, problem = _axis_values(curves, candidate)
        if problem is None and values is not None:
            indexed = sorted(zip(values, range(len(curves)), curves), key=lambda row: (row[0], row[1]))
            return [row[2] for row in indexed], [row[0] for row in indexed], candidate, True, warnings
        if candidate == "frame_index" and problem:
            warnings.append(problem + " Falling back to ordinal sequence_order; it is not a physical time axis.")

    warnings.append("No unique finite frame_index or sequence_order was available; source order was used.")
    return list(curves), [float(index) for index in range(len(curves))], "sequence_order", True, warnings


def _native_value(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _analysis_audit(analyses: Sequence[AnalysisEnvelope]) -> list[dict[str, Any]]:
    return [
        {
            "curve_id": envelope.curve_id,
            "curve_name": envelope.curve_name,
            "analysis_id": envelope.analysis_id,
            "analysis_type": envelope.analysis_type,
            "status": envelope.status.value if isinstance(envelope.status, AnalysisStatus) else str(envelope.status),
            "execution_status": envelope.execution_status,
            "reliability_label": envelope.reliability_label,
            "reliability_score": _finite_number(envelope.reliability_score),
            "reliability_status": envelope.reliability_status,
            "reporting_status": envelope.reporting_status,
            "reporting_reason_codes": list(envelope.reporting_reason_codes),
            "detection_status": envelope.detection_status,
            "detection_reason_codes": list(envelope.detection_reason_codes),
            "candidate_status": envelope.candidate_status,
            "consensus_status": envelope.consensus_status,
            "parameter_count": len(envelope.parameters),
            "warnings": list(envelope.warnings),
            "invalid_reason": envelope.invalid_reason,
        }
        for envelope in analyses
    ]


def _parameter_rows(
    curves: Sequence[CurveData], axes: Sequence[float | None], analyses: Sequence[AnalysisEnvelope]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    locations = {curve.curve_id: (index, axes[index], curve.name) for index, curve in enumerate(curves)}
    audit_rows: list[dict[str, Any]] = []
    trajectories: list[dict[str, Any]] = []
    for envelope in analyses:
        if envelope.curve_id not in locations:
            continue
        frame, axis, curve_name = locations[envelope.curve_id]
        model_name = next((str(p.value) for p in envelope.parameters if p.name == "model_name" and p.value), None)
        envelope_status = envelope.status.value if isinstance(envelope.status, AnalysisStatus) else str(envelope.status)
        for parameter in envelope.parameters:
            numeric_value = _finite_number(parameter.value)
            parameter_status = (
                parameter.status.value
                if isinstance(parameter.status, AnalysisStatus)
                else str(parameter.status)
            )
            row = {
                "frame": frame,
                "axis_value": axis,
                "curve_id": envelope.curve_id,
                "curve_name": curve_name,
                "analysis_type": envelope.analysis_type,
                "analysis_id": envelope.analysis_id,
                "model_name": model_name,
                "parameter": parameter.name,
                "value": numeric_value,
                "value_raw": _native_value(parameter.value),
                "unit": parameter.unit,
                "status": envelope_status,
                "parameter_status": parameter_status,
                "parameter_invalid_reason": parameter.invalid_reason,
                "stderr": _finite_number(parameter.stderr),
                "ci95_low": _finite_number(parameter.ci95_low),
                "ci95_high": _finite_number(parameter.ci95_high),
                "bound_hit": parameter.bound_hit,
                "reliability_label": envelope.reliability_label,
                "reliability_score": _finite_number(envelope.reliability_score),
                "reliability_status": envelope.reliability_status,
                "reporting_status": envelope.reporting_status,
                "reporting_reason_codes": list(envelope.reporting_reason_codes),
                "detection_status": envelope.detection_status,
                "detection_reason_codes": list(envelope.detection_reason_codes),
            }
            audit_rows.append(row)
            if numeric_value is not None:
                trajectories.append(row)
    return trajectories, audit_rows


def _qualified_trajectories(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["value"] is not None
        and row["axis_value"] is not None
        and row["status"] == AnalysisStatus.SUCCESS.value
        and row["parameter_status"] == AnalysisStatus.SUCCESS.value
        and row["reliability_status"] == "reliable"
        and row["reporting_status"] == "reportable"
        and row["analysis_type"] not in _LOCAL_FEATURE_METHODS
    ]


def _unique_frame_groups(rows: Sequence[dict[str, Any]]) -> dict[tuple[str, str | None, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str | None, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["analysis_type"], row["model_name"], row["parameter"], row["unit"] or "")
        grouped[key].append(row)
    return {
        key: series
        for key, series in grouped.items()
        if len({row["frame"] for row in series}) == len(series)
    }


def _change_flags(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for key, series in _unique_frame_groups(rows).items():
        series.sort(key=lambda row: row["frame"])
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
                    "model_name": key[1],
                    "parameter": key[2],
                    "unit": key[3],
                    "delta": float(differences[index]),
                    "robust_z": float(robust_z[index]),
                    "interpretation": "review_candidate_not_phase_transition_proof",
                }
            )
    return flags


def _intensity_unit_key(unit: str) -> str:
    normalized = "".join(str(unit).casefold().split()).replace("⁻¹", "^-1")
    if normalized in {"1/cm", "cm-1", "cm^-1"}:
        return "cm^-1"
    if normalized in {"au", "a.u.", "a.u", "arb.u.", "arbitraryunits"}:
        return "a.u."
    return normalized


def _unit_factors(curves: Sequence[CurveData]) -> tuple[dict[str, float] | None, str | None, str | None]:
    factors: dict[str, float] = {}
    intensity_units: dict[str, str] = {}
    for curve in curves:
        try:
            q_unit = normalize_q_unit(curve.q_unit)
        except ValueError:
            return None, None, f"Sequence comparisons were skipped because q unit '{curve.q_unit}' is unsupported."
        factors[curve.curve_id] = 0.1 if q_unit == "nm^-1" else 1.0
        intensity_units[curve.curve_id] = _intensity_unit_key(curve.intensity_unit)
    unique_intensity_units = set(intensity_units.values())
    if len(unique_intensity_units) > 1:
        displayed = sorted({str(curve.intensity_unit) for curve in curves})
        return None, None, f"Sequence comparisons were skipped because intensity units differ across curves: {displayed}."
    canonical_intensity = next(iter(unique_intensity_units), "")
    return factors, canonical_intensity, None


def _reference_rows(
    curves: Sequence[CurveData],
    axes: Sequence[float | None],
    config: AutoBatchConfig,
    q_factors: dict[str, float],
) -> tuple[list[dict[str, Any]], list[str]]:
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
        q = np.asarray(curve.q, dtype=float) * q_factors[curve.curve_id]
        intensity = np.asarray(curve.intensity, dtype=float)
        rq = np.asarray(reference.q, dtype=float) * q_factors[reference.curve_id]
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
                "q_unit": "A^-1",
                "intensity_unit": curve.intensity_unit,
                "point_count": int(np.count_nonzero(finite)),
                "rmse": float(np.sqrt(np.mean(delta**2))),
                "mae": float(np.mean(np.abs(delta))),
                "relative_absolute_area": None if denominator <= 0 else float(np.trapezoid(np.abs(delta), q_use[finite]) / denominator),
            }
        )
    return rows, []


def _linear_trends(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for key, series in _unique_frame_groups(rows).items():
        series.sort(key=lambda row: row["frame"])
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
                "model_name": key[1],
                "parameter": key[2],
                "unit": key[3],
                "slope": float(slope),
                "intercept": float(intercept),
                "R2": r2,
                "point_count": len(series),
                "interpretation": "descriptive_linear_trend_not_kinetic_mechanism",
            }
        )
    return output


def _exploratory_statistics(
    curves: Sequence[CurveData],
    axes: Sequence[float | None],
    config: AutoBatchConfig,
    q_factors: dict[str, float],
    intensity_unit: str,
) -> dict[str, Any]:
    if len(curves) < 2:
        return {"status": "not_applicable", "reason": "at_least_two_curves_required"}
    effective_low, effective_high = config.effective_q_range
    prepared: list[tuple[np.ndarray, np.ndarray]] = []
    for curve in curves:
        q = np.asarray(curve.q, dtype=float) * q_factors[curve.curve_id]
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
    for iteration in range(50):
        new_labels = np.argmin(np.linalg.norm(scores[:, None, :] - centers[None, :, :], axis=2), axis=1)
        if np.array_equal(new_labels, labels) and iteration:
            break
        labels = new_labels
        for label in range(cluster_count):
            members = scores[labels == label]
            if len(members):
                centers[label] = np.mean(members, axis=0)
    return {
        "status": "success",
        "q_grid": grid.tolist(),
        "q_unit": "A^-1",
        "intensity_unit": intensity_unit,
        "explained_variance_ratio": explained.tolist(),
        "scores": [
            {
                "frame": i,
                "axis_value": axes[i],
                "curve_id": curve.curve_id,
                "components": scores[i].tolist(),
                "cluster": int(labels[i]),
            }
            for i, curve in enumerate(curves)
        ],
        "interpretation": "exploratory_pattern_not_phase_or_mechanism_proof",
    }


def analyze_sequence(
    curves: Sequence[CurveData], analyses: Sequence[AnalysisEnvelope], config: AutoBatchConfig
) -> dict[str, Any]:
    """Create JSON-safe sequence summaries without mutating curves or analyses."""

    ordered, axes, axis_name, axis_valid, axis_warnings = _ordered_curves(curves, config.sequence_axis)
    trajectories, parameter_audit = _parameter_rows(ordered, axes, analyses)
    qualified = _qualified_trajectories(trajectories) if axis_valid else []
    q_factors, intensity_unit, unit_warning = _unit_factors(ordered)
    warnings = list(axis_warnings)
    if unit_warning is not None:
        warnings.append(unit_warning)
    if q_factors is None or intensity_unit is None:
        references = []
        reference_warnings: list[str] = []
        exploratory = (
            {"status": "not_applicable", "reason": "incompatible_sequence_units"}
            if config.enable_exploratory_statistics
            else {"status": "not_enabled"}
        )
    else:
        references, reference_warnings = _reference_rows(ordered, axes, config, q_factors)
        exploratory = (
            _exploratory_statistics(ordered, axes, config, q_factors, intensity_unit)
            if config.enable_exploratory_statistics
            else {"status": "not_enabled"}
        )
    warnings.extend(reference_warnings)
    return {
        "status": "not_applicable" if not ordered else ("success" if axis_valid else "limited"),
        "sequence_axis": axis_name,
        "sequence_axis_valid": axis_valid,
        "effective_q_range": list(config.effective_q_range),
        "frame_table": [
            {"frame": i, "axis_value": axes[i], "curve_id": curve.curve_id, "curve_name": curve.name}
            for i, curve in enumerate(ordered)
        ],
        "analysis_audit": _analysis_audit(analyses),
        "parameter_trajectories": trajectories,
        "parameter_audit": parameter_audit,
        "reference_comparisons": references,
        "change_flags": _change_flags(qualified) if axis_valid else [],
        "linear_trends": _linear_trends(qualified) if config.enable_kinetics and axis_valid else [],
        "exploratory_statistics": exploratory,
        "warnings": warnings,
        "interpretation": "sequence_association_not_causality_or_phase_transition_proof",
    }


__all__ = ["analyze_sequence"]
