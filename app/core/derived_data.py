from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.data_model import CurveData


DERIVED_VALUE_COLUMNS = [
    "q2",
    "ln_q",
    "log10_q",
    "inv_q",
    "d_2pi_over_q",
    "qRg",
    "qD",
    "qR",
    "ln_I",
    "log10_I",
    "qI",
    "q2I",
    "q3I",
    "q4I",
    "q_alpha_I",
    "alpha_local",
    "local_slope_dlnI_dlnq",
    "I_over_ref",
    "I_minus_ref",
]

DERIVED_VALID_COLUMNS = [
    "valid_q",
    "valid_I",
    "valid_ln_q",
    "valid_log10_q",
    "valid_ln_I",
    "valid_log10_I",
    "valid_d_2pi_over_q",
    "valid_qRg",
    "valid_qD",
    "valid_qR",
    "valid_q_alpha_I",
    "valid_local_slope",
    "valid_I_over_ref",
    "valid_I_minus_ref",
]


@dataclass(frozen=True)
class DerivedDataOptions:
    alpha: float | None = None
    rg: float | None = None
    diameter: float | None = None
    radius: float | None = None
    reference_curve_id: str | None = None
    include_natural_logs: bool = True
    include_log10: bool = True
    include_valid_flags: bool = True
    include_optional_parameter_warnings: bool = True


@dataclass(frozen=True)
class DerivedDataResult:
    table: pd.DataFrame
    units: dict[str, str]
    formulas: dict[str, str]
    warnings: list[str]
    metadata: dict[str, Any]


def _nan_array(length: int) -> np.ndarray:
    return np.full(length, np.nan, dtype=np.float64)


def _source_stem(curve: CurveData) -> str | None:
    if curve.metadata.get("source_stem"):
        return str(curve.metadata["source_stem"])
    if curve.source_file:
        return Path(curve.source_file).stem
    return None


def _validate_curve_arrays(curve: CurveData) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    q = np.asarray(curve.q, dtype=np.float64)
    intensity = np.asarray(curve.intensity, dtype=np.float64)
    if q.shape != intensity.shape:
        raise ValueError(f"q and intensity length mismatch: q={q.shape}, intensity={intensity.shape}.")
    error = None
    if curve.error is not None:
        error = np.asarray(curve.error, dtype=np.float64)
        if error.shape != q.shape:
            raise ValueError(f"error length mismatch: error={error.shape}, q={q.shape}.")
    return q, intensity, error


def _safe_where(mask: np.ndarray, values: np.ndarray) -> np.ndarray:
    output = _nan_array(mask.size)
    output[mask] = values[mask]
    return output


def _parameter_column(q: np.ndarray, parameter: float | None) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(q) & (parameter is not None)
    values = _nan_array(q.size)
    if parameter is not None:
        values[valid] = q[valid] * float(parameter)
    return values, valid


def _local_slope(q: np.ndarray, intensity: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[str]]:
    values = _nan_array(q.size)
    warnings: list[str] = []
    valid = np.isfinite(q) & np.isfinite(intensity) & (q > 0) & (intensity > 0)
    valid_indices = np.flatnonzero(valid)
    if valid_indices.size < 3:
        warnings.append("local_slope_dlnI_dlnq is NaN because fewer than 3 rows have q > 0 and I > 0.")
        return values, np.isfinite(values), warnings

    q_valid = q[valid_indices]
    if np.unique(q_valid).size != q_valid.size:
        warnings.append("local_slope_dlnI_dlnq is NaN because valid q values contain duplicates.")
        return values, np.isfinite(values), warnings

    order = np.argsort(q_valid)
    sorted_indices = valid_indices[order]
    with np.errstate(divide="ignore", invalid="ignore"):
        sorted_values = np.gradient(np.log(intensity[sorted_indices]), np.log(q[sorted_indices]))
    values[sorted_indices] = sorted_values
    return values, np.isfinite(values), warnings


def _reference_columns(
    curve: CurveData,
    reference_curve: CurveData | None,
    q: np.ndarray,
    intensity: np.ndarray,
    *,
    warn_missing_reference: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    ratio = _nan_array(q.size)
    difference = _nan_array(q.size)
    valid_ratio = np.zeros(q.size, dtype=bool)
    valid_difference = np.zeros(q.size, dtype=bool)
    warnings: list[str] = []
    if reference_curve is None:
        if warn_missing_reference:
            warnings.append("I_over_ref and I_minus_ref are NaN because no reference curve was provided.")
        return ratio, difference, valid_ratio, valid_difference, warnings

    ref_q, ref_i, _ref_error = _validate_curve_arrays(reference_curve)
    if q.shape != ref_q.shape or not np.array_equal(q, ref_q):
        warnings.append("I_over_ref and I_minus_ref are NaN because reference curve q grid differs; no interpolation was performed.")
        return ratio, difference, valid_ratio, valid_difference, warnings

    valid_difference = np.isfinite(intensity) & np.isfinite(ref_i)
    difference[valid_difference] = intensity[valid_difference] - ref_i[valid_difference]
    valid_ratio = valid_difference & (ref_i != 0)
    ratio[valid_ratio] = intensity[valid_ratio] / ref_i[valid_ratio]
    if np.any(valid_difference & (ref_i == 0)):
        warnings.append("I_over_ref contains NaN for rows where reference intensity is zero.")
    if reference_curve.curve_id == curve.curve_id:
        warnings.append("Reference curve is the same as the source curve; ratio is 1 where valid and difference is 0.")
    return ratio, difference, valid_ratio, valid_difference, warnings


def derived_column_units(curve: CurveData, *, alpha: float | None = None) -> dict[str, str]:
    q_unit = curve.q_unit
    i_unit = curve.intensity_unit
    length_unit = f"1/({q_unit})"
    q_alpha_unit = f"({q_unit})^{alpha} {i_unit}" if alpha is not None else f"({q_unit})^alpha {i_unit}"
    return {
        "q": q_unit,
        "I": i_unit,
        "error": i_unit,
        "q2": f"({q_unit})^2",
        "ln_q": "dimensionless transform of q numeric value",
        "log10_q": "dimensionless transform of q numeric value",
        "inv_q": length_unit,
        "d_2pi_over_q": length_unit,
        "qRg": "dimensionless",
        "qD": "dimensionless",
        "qR": "dimensionless",
        "ln_I": "dimensionless transform of I numeric value",
        "log10_I": "dimensionless transform of I numeric value",
        "qI": f"{q_unit} {i_unit}",
        "q2I": f"({q_unit})^2 {i_unit}",
        "q3I": f"({q_unit})^3 {i_unit}",
        "q4I": f"({q_unit})^4 {i_unit}",
        "q_alpha_I": q_alpha_unit,
        "alpha_local": "dimensionless",
        "local_slope_dlnI_dlnq": "dimensionless",
        "I_over_ref": "dimensionless",
        "I_minus_ref": i_unit,
    }


def derived_column_formulas(*, alpha: float | None = None) -> dict[str, str]:
    alpha_text = "alpha" if alpha is None else str(alpha)
    return {
        "q": "original q",
        "I": "original I(q)",
        "error": "original error/sigma if provided",
        "q2": "q**2",
        "ln_q": "ln(q), valid where q > 0",
        "log10_q": "log10(q), valid where q > 0",
        "inv_q": "1/q, valid where q != 0",
        "d_2pi_over_q": "2π/q, valid where q > 0",
        "qRg": "q*Rg, valid when Rg is provided and q is finite",
        "qD": "q*D, valid when D is provided and q is finite",
        "qR": "q*R, valid when R is provided and q is finite",
        "ln_I": "ln(I), valid where I > 0",
        "log10_I": "log10(I), valid where I > 0",
        "qI": "q*I",
        "q2I": "q**2*I",
        "q3I": "q**3*I",
        "q4I": "q**4*I",
        "q_alpha_I": f"q**{alpha_text}*I, valid when alpha is provided and the result is finite",
        "alpha_local": "α(q) = -local_slope_dlnI_dlnq = -d ln(I)/d ln(q)",
        "local_slope_dlnI_dlnq": "np.gradient(np.log(I), np.log(q)) on q-sorted rows with q > 0 and I > 0",
        "I_over_ref": "I/I_ref, valid only when a reference curve has the same q grid and I_ref != 0",
        "I_minus_ref": "I-I_ref, valid only when a reference curve has the same q grid",
    }


def build_curve_derived_table(
    curve: CurveData,
    *,
    options: DerivedDataOptions | None = None,
    reference_curve: CurveData | None = None,
    preserve_input_order: bool = True,
) -> DerivedDataResult:
    options = options or DerivedDataOptions()
    q, intensity, error = _validate_curve_arrays(curve)
    row_count = q.size
    warnings: list[str] = []

    order = np.arange(row_count) if preserve_input_order else np.argsort(q, kind="mergesort")
    sort_rank = np.empty(row_count, dtype=int)
    sort_rank[np.argsort(q, kind="mergesort")] = np.arange(row_count)

    valid_q = np.isfinite(q)
    valid_i = np.isfinite(intensity)
    valid_qi = valid_q & valid_i
    positive_q = valid_q & (q > 0)
    positive_i = valid_i & (intensity > 0)
    nonzero_q = valid_q & (q != 0)

    q2 = np.square(q)
    ln_q = _nan_array(row_count)
    log10_q = _nan_array(row_count)
    inv_q = _nan_array(row_count)
    d_2pi_over_q = _nan_array(row_count)
    ln_i = _nan_array(row_count)
    log10_i = _nan_array(row_count)
    with np.errstate(divide="ignore", invalid="ignore"):
        ln_q[positive_q] = np.log(q[positive_q])
        log10_q[positive_q] = np.log10(q[positive_q])
        inv_q[nonzero_q] = 1.0 / q[nonzero_q]
        d_2pi_over_q[positive_q] = 2.0 * np.pi / q[positive_q]
        ln_i[positive_i] = np.log(intensity[positive_i])
        log10_i[positive_i] = np.log10(intensity[positive_i])

    qrg, valid_qrg = _parameter_column(q, options.rg)
    qd, valid_qd = _parameter_column(q, options.diameter)
    qr, valid_qr = _parameter_column(q, options.radius)

    q_alpha_i = _nan_array(row_count)
    valid_q_alpha = np.zeros(row_count, dtype=bool)
    if options.alpha is None:
        if options.include_optional_parameter_warnings:
            warnings.append("q_alpha_I is NaN because alpha was not provided.")
    else:
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            q_alpha_i = np.power(q, float(options.alpha)) * intensity
        valid_q_alpha = valid_qi & np.isfinite(q_alpha_i)
        q_alpha_i = _safe_where(valid_q_alpha, q_alpha_i)

    if options.include_optional_parameter_warnings and options.rg is None:
        warnings.append("qRg is NaN because Rg was not provided.")
    if options.include_optional_parameter_warnings and options.diameter is None:
        warnings.append("qD is NaN because D was not provided.")
    if options.include_optional_parameter_warnings and options.radius is None:
        warnings.append("qR is NaN because R was not provided.")

    local_slope, valid_local_slope, slope_warnings = _local_slope(q, intensity)
    warnings.extend(slope_warnings)
    ratio, difference, valid_ratio, valid_difference, reference_warnings = _reference_columns(
        curve,
        reference_curve,
        q,
        intensity,
        warn_missing_reference=options.include_optional_parameter_warnings,
    )
    warnings.extend(reference_warnings)

    if np.any(valid_q & ~positive_q):
        warnings.append("ln_q, log10_q, and d_2pi_over_q contain NaN for rows where q <= 0.")
    if np.any(valid_i & ~positive_i):
        warnings.append("ln_I, log10_I, and local_slope_dlnI_dlnq contain NaN for rows where I <= 0.")
    if np.any(~valid_q):
        warnings.append("Derived q-based columns contain NaN for rows where q is non-finite.")
    if np.any(~valid_i):
        warnings.append("Derived intensity-based columns contain NaN for rows where I is non-finite.")

    table = pd.DataFrame(
        {
            "row_index": np.arange(row_count, dtype=int),
            "sort_index_by_q": sort_rank,
            "curve_id": curve.curve_id,
            "curve_name": curve.name,
            "source_stem": _source_stem(curve),
            "q": q,
            "I": intensity,
            "error": _nan_array(row_count) if error is None else error,
            "q_unit": curve.q_unit,
            "intensity_unit": curve.intensity_unit,
            "q2": q2,
            "ln_q": ln_q,
            "log10_q": log10_q,
            "inv_q": inv_q,
            "d_2pi_over_q": d_2pi_over_q,
            "qRg": qrg,
            "qD": qd,
            "qR": qr,
            "ln_I": ln_i,
            "log10_I": log10_i,
            "qI": q * intensity,
            "q2I": q2 * intensity,
            "q3I": np.power(q, 3) * intensity,
            "q4I": np.power(q, 4) * intensity,
            "q_alpha_I": q_alpha_i,
            "alpha_local": -local_slope,
            "local_slope_dlnI_dlnq": local_slope,
            "I_over_ref": ratio,
            "I_minus_ref": difference,
            "valid_q": valid_q,
            "valid_I": valid_i,
            "valid_ln_q": positive_q,
            "valid_log10_q": positive_q,
            "valid_ln_I": positive_i,
            "valid_log10_I": positive_i,
            "valid_d_2pi_over_q": positive_q,
            "valid_qRg": valid_qrg,
            "valid_qD": valid_qd,
            "valid_qR": valid_qr,
            "valid_q_alpha_I": valid_q_alpha,
            "valid_local_slope": valid_local_slope,
            "valid_I_over_ref": valid_ratio,
            "valid_I_minus_ref": valid_difference,
        }
    )
    table = table.iloc[order].reset_index(drop=True)
    if not options.include_valid_flags:
        table = table.drop(columns=DERIVED_VALID_COLUMNS)
    if not options.include_natural_logs:
        drop = [column for column in ["ln_q", "ln_I"] if column in table]
        table = table.drop(columns=drop)
    if not options.include_log10:
        drop = [column for column in ["log10_q", "log10_I"] if column in table]
        table = table.drop(columns=drop)

    metadata = {
        "alpha": options.alpha,
        "rg": options.rg,
        "diameter": options.diameter,
        "radius": options.radius,
        "reference_curve_id": None if reference_curve is None else reference_curve.curve_id,
        "reference_curve_name": None if reference_curve is None else reference_curve.name,
        "preserve_input_order": preserve_input_order,
        "row_count": row_count,
        "no_interpolation": True,
        "no_smoothing": True,
        "no_background_subtraction": True,
        "no_unit_conversion": True,
    }
    return DerivedDataResult(
        table=table,
        units=derived_column_units(curve, alpha=options.alpha),
        formulas=derived_column_formulas(alpha=options.alpha),
        warnings=warnings,
        metadata=metadata,
    )

