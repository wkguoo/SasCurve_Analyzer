from __future__ import annotations

import numpy as np


def linear_fit(x, y, sigma=None) -> dict:
    x_array = np.asarray(x, dtype=float)
    y_array = np.asarray(y, dtype=float)
    if x_array.size < 2:
        raise ValueError("At least two points are required for linear fitting.")

    if sigma is not None:
        sigma_array = np.asarray(sigma, dtype=float)
        valid_sigma = np.isfinite(sigma_array) & (sigma_array > 0)
        if not np.all(valid_sigma):
            raise ValueError("All sigma values must be finite and positive for weighted fitting.")
        coeffs = np.polyfit(x_array, y_array, 1, w=1.0 / sigma_array)
    else:
        coeffs = np.polyfit(x_array, y_array, 1)

    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    fitted = slope * x_array + intercept
    residuals = y_array - fitted
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y_array - np.mean(y_array)) ** 2))
    r_squared = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    n = int(x_array.size)
    adjusted_r_squared = float(1.0 - (1.0 - r_squared) * (n - 1) / (n - 2)) if n > 2 else float("nan")

    reduced_chi_square = float("nan")
    standardized_residuals = None
    if sigma is not None and n > 2:
        standardized_residuals = residuals / sigma_array
        reduced_chi_square = float(np.sum(standardized_residuals**2) / (n - 2))

    return {
        "slope": slope,
        "intercept": intercept,
        "fitted": fitted,
        "residuals": residuals,
        "r_squared": r_squared,
        "adjusted_r_squared": adjusted_r_squared,
        "reduced_chi_square": reduced_chi_square,
        "standardized_residuals": standardized_residuals,
    }

