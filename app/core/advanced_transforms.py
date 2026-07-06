from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.data_model import CurveData


@dataclass
class TransformResult:
    transform_name: str
    input: str
    output: np.ndarray
    unit: str
    warnings: list[str]


def transform_curve(curve: CurveData, transform_name: str) -> TransformResult:
    q = curve.q
    i = curve.intensity
    warnings: list[str] = []
    if transform_name == "q_to_size":
        valid = q > 0
        if not np.all(valid):
            warnings.append("Excluded q <= 0 for 2*pi/q transform.")
        return TransformResult(transform_name, "q", 2.0 * np.pi / q[valid], f"1/({curve.q_unit})", warnings)
    if transform_name == "q_squared":
        return TransformResult(transform_name, "q", q**2, f"({curve.q_unit})^2", warnings)
    if transform_name == "lnI":
        valid = i > 0
        if not np.all(valid):
            warnings.append("Excluded I <= 0 for lnI transform.")
        return TransformResult(transform_name, "I", np.log(i[valid]), f"ln({curve.intensity_unit})", warnings)
    if transform_name == "log10I":
        valid = i > 0
        if not np.all(valid):
            warnings.append("Excluded I <= 0 for log10I transform.")
        return TransformResult(transform_name, "I", np.log10(i[valid]), f"log10({curve.intensity_unit})", warnings)
    if transform_name == "qI":
        return TransformResult(transform_name, "q,I", q * i, f"{curve.q_unit} {curve.intensity_unit}", warnings)
    if transform_name == "q2I":
        return TransformResult(transform_name, "q,I", q**2 * i, f"({curve.q_unit})^2 {curve.intensity_unit}", warnings)
    if transform_name == "q3I":
        return TransformResult(transform_name, "q,I", q**3 * i, f"({curve.q_unit})^3 {curve.intensity_unit}", warnings)
    if transform_name == "q4I":
        return TransformResult(transform_name, "q,I", q**4 * i, f"({curve.q_unit})^4 {curve.intensity_unit}", warnings)
    if transform_name == "normalized_I":
        denom = float(np.nanmax(i))
        if denom == 0:
            warnings.append("Cannot normalize by Imax because Imax is zero.")
            output = np.full_like(i, np.nan, dtype=float)
        else:
            output = i / denom
        warnings.append("Normalized intensity is for display only unless explicitly saved as derived data.")
        return TransformResult(transform_name, "I", output, "normalized", warnings)
    raise ValueError(f"Unsupported transform_name: {transform_name}")

