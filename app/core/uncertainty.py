from __future__ import annotations

import numpy as np


def input_uncertainty_kind(column, columns=()) -> str:
    """Classify a column's declared meaning, without treating any third column as sigma."""
    if column is None:
        return "missing"
    name = str(column).strip().lower()
    names = {str(value).strip().lower() for value in columns}
    if name == "std_intensity" or (
        "std" in name and ("mean_intensity" in names or "n_frames" in names)
    ):
        return "series_std"
    if name in {"error", "sigma", "sigma_i", "err", "uncertainty", "di", "dy", "d_i", "intensity_error"}:
        return "measurement"
    return "unknown"


def prepare_input_uncertainty(error, column, columns, metadata):
    """Keep nonmeasurement columns as source data, outside the fitting sigma array."""
    inferred = input_uncertainty_kind(column, columns)
    kind = metadata.get("uncertainty_kind", inferred) if error is not None else "missing"
    if kind not in {"missing", "measurement", "series_std", "unknown", "assumed"}:
        raise ValueError(f"Unsupported uncertainty_kind: {kind!r}")
    metadata["uncertainty_kind"] = kind
    metadata["uncertainty_column"] = None if column is None else str(column)
    if error is not None and kind != "measurement":
        metadata["non_measurement_error"] = {
            "column": str(column), "kind": kind,
            "values": np.asarray(error, dtype=float).tolist(),
        }
        return None
    return error


def log_intensity_sigma(intensity, error, *, base: float = np.e):
    """Propagate intensity uncertainty to a logarithm with the given base."""

    intensity_array = np.asarray(intensity, dtype=float)
    error_array = np.asarray(error, dtype=float)
    log_base = float(np.log(base))
    if not np.isfinite(log_base) or log_base == 0.0:
        raise ValueError("Logarithm base must be finite, positive, and different from 1.")
    sigma = error_array / (intensity_array * log_base)
    sigma[~np.isfinite(sigma)] = np.nan
    return sigma
