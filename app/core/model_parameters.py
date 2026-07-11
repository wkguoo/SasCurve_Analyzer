"""Derived, JSON-safe shape-model parameters.

The values here are geometric or algebraic consequences of fitted parameters.
They remain conditional on the corresponding shape model and do not establish a
unique morphology.  Every unavailable value is represented as ``None`` with a
machine-readable reason instead of a NaN or infinity.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np


DerivedParameterRecords = dict[str, dict[str, Any]]
DerivedBuilder = Callable[[Mapping[str, Any], str], DerivedParameterRecords]


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if np.isfinite(numeric) else None


def _parameter_value(parameters: Mapping[str, Any], name: str) -> float | None:
    value = parameters.get(name)
    if isinstance(value, Mapping):
        value = value.get("value")
    return _finite_float(value)


def _length_unit_from_q_unit(q_unit: str) -> str:
    cleaned = str(q_unit).strip()
    if cleaned == "A^-1":
        return "A"
    if cleaned == "nm^-1":
        return "nm"
    if cleaned.endswith("^-1") and len(cleaned) > 3:
        return cleaned[:-3]
    return f"1/({cleaned or 'q'})"


def _record(value: Any, unit: str, reason: str | None = None) -> dict[str, Any]:
    finite_value = _finite_float(value)
    return {
        "value": finite_value,
        "unit": str(unit),
        "reason": None if finite_value is not None else (reason or "non_finite_derived_value"),
    }


def _calculated_record(calculation: Callable[[], Any], unit: str, reason: str = "non_finite_derived_calculation") -> dict[str, Any]:
    """Evaluate one derived expression without exporting overflow exceptions."""

    try:
        with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
            value = calculation()
    except (ArithmeticError, OverflowError, ValueError):
        return _record(None, unit, reason)
    return _record(value, unit, reason)


def _positive_parameter(parameters: Mapping[str, Any], name: str) -> tuple[float | None, str | None]:
    value = _parameter_value(parameters, name)
    if value is None:
        return None, f"missing_or_non_finite_parameter:{name}"
    if value <= 0.0:
        return None, f"non_positive_parameter:{name}"
    return value, None


def _sphere(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    radius, reason = _positive_parameter(parameters, "radius")
    length_unit = _length_unit_from_q_unit(q_unit)
    if radius is None:
        return {
            "diameter": _record(None, length_unit, reason),
            "geometric_Rg": _record(None, length_unit, reason),
            "volume": _record(None, f"{length_unit}^3", reason),
        }
    return {
        "diameter": _calculated_record(lambda: 2.0 * radius, length_unit),
        "geometric_Rg": _calculated_record(lambda: math.sqrt(3.0 / 5.0) * radius, length_unit),
        "volume": _calculated_record(lambda: 4.0 * math.pi * radius**3 / 3.0, f"{length_unit}^3"),
    }


def _core_shell_sphere(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    core_radius, core_reason = _positive_parameter(parameters, "core_radius")
    shell_thickness, shell_reason = _positive_parameter(parameters, "shell_thickness")
    length_unit = _length_unit_from_q_unit(q_unit)
    total_reason = core_reason or shell_reason
    total_radius = None if total_reason else _finite_float(core_radius + shell_thickness)
    if total_radius is None and total_reason is None:
        total_reason = "non_finite_total_radius"
    return {
        "total_radius": _record(total_radius, length_unit, total_reason),
        "core_diameter": _record(None, length_unit, core_reason)
        if core_radius is None
        else _calculated_record(lambda: 2.0 * core_radius, length_unit),
        "total_diameter": _record(None, length_unit, total_reason)
        if total_radius is None
        else _calculated_record(lambda: 2.0 * total_radius, length_unit),
    }


def _ellipsoid(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    equatorial_radius, equatorial_reason = _positive_parameter(parameters, "equatorial_radius")
    polar_radius, polar_reason = _positive_parameter(parameters, "polar_radius")
    length_unit = _length_unit_from_q_unit(q_unit)
    reason = equatorial_reason or polar_reason
    if reason:
        return {
            "axis_ratio": _record(None, "dimensionless", reason),
            "volume": _record(None, f"{length_unit}^3", reason),
        }
    return {
        "axis_ratio": _calculated_record(lambda: polar_radius / equatorial_radius, "dimensionless"),
        "volume": _calculated_record(
            lambda: 4.0 * math.pi * equatorial_radius**2 * polar_radius / 3.0,
            f"{length_unit}^3",
        ),
    }


def _cylinder(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    radius, radius_reason = _positive_parameter(parameters, "radius")
    length, length_reason = _positive_parameter(parameters, "length")
    length_unit = _length_unit_from_q_unit(q_unit)
    both_reason = radius_reason or length_reason
    return {
        "diameter": _record(None, length_unit, radius_reason)
        if radius is None
        else _calculated_record(lambda: 2.0 * radius, length_unit),
        "aspect_ratio": _record(None, "dimensionless", both_reason)
        if both_reason
        else _calculated_record(lambda: length / (2.0 * radius), "dimensionless"),
        "volume": _record(None, f"{length_unit}^3", both_reason)
        if both_reason
        else _calculated_record(lambda: math.pi * radius**2 * length, f"{length_unit}^3"),
    }


def _disk(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    radius, radius_reason = _positive_parameter(parameters, "radius")
    thickness, thickness_reason = _positive_parameter(parameters, "thickness")
    length_unit = _length_unit_from_q_unit(q_unit)
    both_reason = radius_reason or thickness_reason
    return {
        "diameter": _record(None, length_unit, radius_reason)
        if radius is None
        else _calculated_record(lambda: 2.0 * radius, length_unit),
        "aspect_ratio": _record(None, "dimensionless", both_reason)
        if both_reason
        else _calculated_record(lambda: thickness / (2.0 * radius), "dimensionless"),
        "volume": _record(None, f"{length_unit}^3", both_reason)
        if both_reason
        else _calculated_record(lambda: math.pi * radius**2 * thickness, f"{length_unit}^3"),
    }


def _surface_fractal(parameters: Mapping[str, Any], _q_unit: str) -> DerivedParameterRecords:
    surface_dimension = _parameter_value(parameters, "surface_dimension")
    reason = None
    if surface_dimension is None:
        reason = "missing_or_non_finite_parameter:surface_dimension"
    elif not 2.0 <= surface_dimension <= 3.0:
        reason = "outside_model_domain:surface_dimension"
    return {
        "Porod_exponent": _record(None if reason else 6.0 - surface_dimension, "dimensionless", reason),
    }


def _lamellar_peak_stack(parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    q0, q0_reason = _positive_parameter(parameters, "q0")
    width, width_reason = _positive_parameter(parameters, "width")
    return {
        "d0": _record(None, _length_unit_from_q_unit(q_unit), q0_reason)
        if q0 is None
        else _calculated_record(lambda: 2.0 * math.pi / q0, _length_unit_from_q_unit(q_unit)),
        "Gaussian_FWHM": _record(None, str(q_unit), width_reason)
        if width is None
        else _calculated_record(lambda: 2.0 * math.sqrt(2.0 * math.log(2.0)) * width, str(q_unit)),
    }


DERIVED_PARAMETER_BUILDERS: dict[str, DerivedBuilder] = {
    "sphere": _sphere,
    "core_shell_sphere": _core_shell_sphere,
    "ellipsoid": _ellipsoid,
    "cylinder": _cylinder,
    "disk": _disk,
    "surface_fractal": _surface_fractal,
    "lamellar_peak_stack": _lamellar_peak_stack,
}


def derived_model_parameters(model_name: str, parameters: Mapping[str, Any], q_unit: str) -> DerivedParameterRecords:
    """Return model-derived quantities as finite values or ``None`` plus reasons.

    Models without a documented mapping deliberately return an empty mapping.
    ``parameters`` may be a simple name-to-number mapping or the legacy
    name-to-parameter-record mapping produced by :mod:`model_fitting`.
    """

    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be a mapping")
    builder = DERIVED_PARAMETER_BUILDERS.get(model_name)
    if builder is None:
        return {}
    return builder(parameters, q_unit)


__all__ = ["DERIVED_PARAMETER_BUILDERS", "derived_model_parameters"]
