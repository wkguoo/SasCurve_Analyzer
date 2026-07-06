from __future__ import annotations

import math

import numpy as np
from scipy.signal import find_peaks, peak_widths

from app.core.data_model import AnalysisResult, CurveData


def detect_peaks(curve: CurveData, q_range: tuple[float, float], *, prominence: float | None = None) -> AnalysisResult:
    q_min, q_max = q_range
    mask = np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q >= q_min) & (curve.q <= q_max)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    warnings = ["d = 2*pi/q* is a characteristic length or correlation distance, not a particle diameter."]
    peaks, properties = find_peaks(intensity, prominence=prominence)
    peak_results: list[dict] = []

    if peaks.size:
        widths = peak_widths(intensity, peaks, rel_height=0.5)
        for i, peak_index in enumerate(peaks):
            peak_q = float(q[peak_index])
            width_points = float(widths[0][i])
            dq = float(np.mean(np.diff(q))) if q.size > 1 else float("nan")
            fwhm = width_points * dq if np.isfinite(dq) else None
            left = max(0, int(math.floor(widths[2][i])))
            right = min(q.size - 1, int(math.ceil(widths[3][i])))
            area = float(np.trapezoid(intensity[left : right + 1], q[left : right + 1])) if right > left else None
            peak_results.append(
                {
                    "peak_q": peak_q,
                    "peak_I": float(intensity[peak_index]),
                    "peak_index": int(peak_index),
                    "FWHM": fwhm,
                    "peak_area": area,
                    "d": float(2.0 * math.pi / peak_q) if peak_q > 0 else None,
                }
            )
    else:
        warnings.append("No peak was detected in the selected q range.")

    return AnalysisResult.create(
        curve=curve,
        analysis_type="peak_detection",
        q_range=q_range,
        parameters={"signal": "I(q)", "prominence": prominence},
        results={"peaks": peak_results, "peak_count": len(peak_results)},
        warnings=warnings,
    )

