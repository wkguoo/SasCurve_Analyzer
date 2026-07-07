from __future__ import annotations

import math

import numpy as np
from scipy.signal import find_peaks, peak_widths

from app.core.data_model import AnalysisResult, CurveData
from app.core.method_warnings import peak_warnings, warning_to_dict, warning_to_text


def detect_peaks(curve: CurveData, q_range: tuple[float, float], *, prominence: float | None = None) -> AnalysisResult:
    q_min, q_max = q_range
    mask = np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q >= q_min) & (curve.q <= q_max)
    q = curve.q[mask]
    intensity = curve.intensity[mask]
    if q.size > 1:
        order = np.argsort(q)
        q = q[order]
        intensity = intensity[order]
    warnings: list[str] = []
    peaks, properties = find_peaks(intensity, prominence=prominence)
    peak_results: list[dict] = []

    if peaks.size:
        widths = peak_widths(intensity, peaks, rel_height=0.5)
        sample_positions = np.arange(q.size, dtype=float)
        for i, peak_index in enumerate(peaks):
            peak_q = float(q[peak_index])
            left_ip = float(widths[2][i])
            right_ip = float(widths[3][i])
            left_q = float(np.interp(left_ip, sample_positions, q))
            right_q = float(np.interp(right_ip, sample_positions, q))
            fwhm = right_q - left_q if right_q >= left_q else None
            left = max(0, int(math.floor(left_ip)))
            right = min(q.size - 1, int(math.ceil(right_ip)))
            area = None
            if fwhm is not None and right > left:
                left_i = float(np.interp(left_ip, sample_positions, intensity))
                right_i = float(np.interp(right_ip, sample_positions, intensity))
                inside = (q > left_q) & (q < right_q)
                area_q = np.concatenate(([left_q], q[inside], [right_q]))
                area_i = np.concatenate(([left_i], intensity[inside], [right_i]))
                area = float(np.trapezoid(area_i, area_q))
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

    method_warnings = peak_warnings()

    return AnalysisResult.create(
        curve=curve,
        analysis_type="peak_detection",
        q_range=q_range,
        parameters={"signal": "I(q)", "prominence": prominence},
        results={"peaks": peak_results, "peak_count": len(peak_results)},
        warnings=[*warnings, *(warning_to_text(warning) for warning in method_warnings)],
        structured_warnings=[warning_to_dict(warning) for warning in method_warnings],
    )

