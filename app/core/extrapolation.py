from __future__ import annotations

import numpy as np


def low_q_extrapolation(q, intensity, method: str = "disabled", **parameters):
    if method == "disabled":
        return np.asarray(q), np.asarray(intensity), ["Low-q extrapolation disabled."]
    warning = f"Low-q extrapolation method '{method}' is enabled; results must be treated as assumption-dependent."
    return np.asarray(q), np.asarray(intensity), [warning]


def high_q_extrapolation(q, intensity, method: str = "disabled", **parameters):
    if method == "disabled":
        return np.asarray(q), np.asarray(intensity), ["High-q extrapolation disabled."]
    warning = f"High-q extrapolation method '{method}' is enabled; results must be treated as assumption-dependent."
    return np.asarray(q), np.asarray(intensity), [warning]

