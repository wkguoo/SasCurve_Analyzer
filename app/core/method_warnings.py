from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict

import numpy as np


@dataclass
class MethodWarning:
    warning_code: str
    severity: str
    message: str
    suggested_action: str
    related_analysis_id: str | None = None


def warning_to_dict(warning: MethodWarning) -> dict:
    return asdict(warning)


def warning_to_text(warning: MethodWarning) -> str:
    return f"[{warning.severity}] {warning.warning_code}: {warning.message} Suggested action: {warning.suggested_action}"


def guinier_warnings(*, qrg_max=None, fit_points=None, slope=None, r_squared=None, q_range_width=None, related_analysis_id=None) -> list[MethodWarning]:
    warnings: list[MethodWarning] = []
    if qrg_max is not None and qrg_max > 1.3:
        warnings.append(MethodWarning("GUINIER_QRG_HIGH", "warning", "qRg_max > 1.3; Guinier interval may be too high.", "Choose a lower-q fitting interval.", related_analysis_id))
    if fit_points is not None and fit_points < 5:
        warnings.append(MethodWarning("GUINIER_TOO_FEW_POINTS", "warning", "Too few points for stable Guinier fitting.", "Use at least five valid points if possible.", related_analysis_id))
    if slope is not None and slope >= 0:
        warnings.append(MethodWarning("GUINIER_NON_NEGATIVE_SLOPE", "error", "Slope is non-negative, so Rg is not physically valid.", "Check q range and data quality.", related_analysis_id))
    if r_squared is not None and q_range_width is not None and r_squared > 0.99 and q_range_width > 1.0:
        warnings.append(MethodWarning("GUINIER_HIGH_R2_WIDE_RANGE", "info", "High R2 can still be misleading when q range is wide.", "Inspect residuals and qRg limits.", related_analysis_id))
    return warnings


def power_law_warnings(*, alpha=None, fit_points=None, local_slope_std=None, crosses_peak=False, related_analysis_id=None) -> list[MethodWarning]:
    warnings: list[MethodWarning] = []
    if fit_points is not None and fit_points < 5:
        warnings.append(MethodWarning("POWER_TOO_FEW_POINTS", "warning", "Too few points for power-law fitting.", "Use a wider stable log-log interval.", related_analysis_id))
    if local_slope_std is not None and local_slope_std > 0.3:
        warnings.append(MethodWarning("POWER_LOCAL_SLOPE_UNSTABLE", "warning", "Local slope fluctuates strongly in the selected interval.", "Narrow the interval or inspect local slope plot.", related_analysis_id))
    if crosses_peak:
        warnings.append(MethodWarning("POWER_CROSSES_PEAK", "warning", "Selected interval may cross a peak or shoulder.", "Avoid fitting across features.", related_analysis_id))
    if alpha is not None:
        warnings.append(MethodWarning("POWER_ALPHA_NON_UNIQUE", "info", "alpha cannot uniquely determine structure.", "Interpret with material context and q range.", related_analysis_id))
    return warnings


def invariant_warnings(related_analysis_id=None) -> list[MethodWarning]:
    return [
        MethodWarning("INVARIANT_FINITE_RANGE", "warning", "Current invariant is only a finite measured q-range integral.", "Do not treat it as a strict 0-to-infinity invariant.", related_analysis_id),
        MethodWarning("INVARIANT_NO_EXTRAPOLATION", "info", "No q->0 or q->infinity extrapolation was applied.", "Record q range when comparing samples.", related_analysis_id),
        MethodWarning("INVARIANT_NO_VOLUME_FRACTION", "warning", "Do not directly invert this value into volume fraction.", "Use contrast and full invariant assumptions before physical inversion.", related_analysis_id),
    ]


def peak_warnings(peak_width=None, related_analysis_id=None) -> list[MethodWarning]:
    warnings = [
        MethodWarning("PEAK_D_NOT_DIAMETER", "warning", "d=2*pi/q* is a characteristic length or correlation distance, not a particle diameter.", "Confirm interpretation with morphology and scattering model.", related_analysis_id)
    ]
    if peak_width is not None and peak_width > 0.2:
        warnings.append(MethodWarning("PEAK_BROAD", "info", "Broad peak or shoulder should be manually confirmed.", "Inspect the original curve and derivative views.", related_analysis_id))
    return warnings


def porod_plateau_warnings(q4i_values, related_analysis_id=None) -> list[MethodWarning]:
    values = np.asarray(q4i_values, dtype=float)
    warnings: list[MethodWarning] = []
    if values.size and np.nanmean(values) != 0:
        mean = float(np.nanmean(values))
        cv = float(np.nanstd(values) / abs(mean))
        if mean <= 0 or cv > 0.2:
            warnings.append(MethodWarning("POROD_NO_STABLE_PLATEAU", "warning", "q^4I(q) does not show a stable plateau.", "Choose another high-q range or inspect noise.", related_analysis_id))
    warnings.append(MethodWarning("POROD_NO_ABSOLUTE_SURFACE", "warning", "Do not calculate absolute specific surface area without contrast and phase assumptions.", "Treat plateau metrics as descriptive unless assumptions are known.", related_analysis_id))
    return warnings

