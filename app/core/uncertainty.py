from __future__ import annotations

import numpy as np


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
