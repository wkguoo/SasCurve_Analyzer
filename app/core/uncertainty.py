from __future__ import annotations

import numpy as np


def log_intensity_sigma(intensity, error):
    intensity_array = np.asarray(intensity, dtype=float)
    error_array = np.asarray(error, dtype=float)
    sigma = error_array / intensity_array
    sigma[~np.isfinite(sigma)] = np.nan
    return sigma

