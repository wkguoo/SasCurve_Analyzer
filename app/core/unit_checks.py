from __future__ import annotations

from collections.abc import Sequence

from app.core.data_model import CurveData
from app.core.transforms import normalize_q_unit


def _canonical_q_unit(unit: str) -> str:
    try:
        return normalize_q_unit(unit)
    except ValueError:
        return unit.strip()


def _canonical_intensity_unit(unit: str) -> str:
    return " ".join(unit.strip().lower().split())


def validate_compatible_curve_units(curves: Sequence[CurveData], *, operation: str) -> None:
    if not curves:
        return
    reference_q_unit = _canonical_q_unit(curves[0].q_unit)
    reference_intensity_unit = _canonical_intensity_unit(curves[0].intensity_unit)
    q_units = [_canonical_q_unit(curve.q_unit) for curve in curves]
    intensity_units = [_canonical_intensity_unit(curve.intensity_unit) for curve in curves]

    if any(unit != reference_q_unit for unit in q_units):
        display_units = ", ".join(curve.q_unit for curve in curves)
        raise ValueError(
            f"q units differ for {operation}: {display_units}. "
            "Convert all curves to the same q unit before averaging or comparison."
        )
    if any(unit != reference_intensity_unit for unit in intensity_units):
        display_units = ", ".join(curve.intensity_unit for curve in curves)
        raise ValueError(
            f"intensity units differ for {operation}: {display_units}. "
            "Use curves with the same intensity unit before averaging or comparison."
        )
