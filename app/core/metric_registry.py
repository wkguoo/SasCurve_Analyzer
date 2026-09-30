"""Authoritative method and metric definitions for automated batch analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.core.auto_batch_schema import AutoBatchConfig


@dataclass(frozen=True)
class MetricSpec:
    """One named output metric produced by an analysis method."""

    name: str
    unit_role: str = "unspecified"
    nullable: bool = True


@dataclass(frozen=True)
class MethodSpec:
    """The metrics and applicability conditions for one analysis method."""

    method_id: str
    region_type: str | None
    metrics: tuple[MetricSpec, ...]
    sample_types: tuple[str, ...] = ()
    config_flag: str | None = None
    # ``effective`` means that the method receives the already-confirmed input
    # boundary and performs its own local checks. ``candidate_consensus`` is
    # reserved for methods whose shared fit needs a method-specific candidate
    # interval (currently Guinier, power-law, and Porod).
    range_strategy: str = "effective"


def _metrics(*names: str, unit_roles: Mapping[str, str] | None = None) -> tuple[MetricSpec, ...]:
    roles = unit_roles or {}
    return tuple(MetricSpec(name, roles.get(name, "unspecified")) for name in names)


METHOD_REGISTRY: dict[str, MethodSpec] = {
    "data_quality": MethodSpec(
        "data_quality",
        None,
        _metrics(
            "q_min",
            "q_max",
            "d_min",
            "d_max",
            "point_count",
            "I_min",
            "I_max",
            "dynamic_range",
            "nan_count",
            "negative_count",
            "zero_count",
            "duplicate_q_count",
            "log_usable_points",
            unit_roles={
                "q_min": "q", "q_max": "q", "d_min": "length", "d_max": "length",
                "point_count": "count", "I_min": "intensity", "I_max": "intensity",
                "dynamic_range": "dimensionless", "nan_count": "count", "negative_count": "count",
                "zero_count": "count", "duplicate_q_count": "count", "log_usable_points": "count",
            },
        ),
    ),
    "derived_coordinates": MethodSpec(
        "derived_coordinates",
        None,
        _metrics(
            "q2",
            "ln_q",
            "log10_q",
            "inv_q",
            "d_2pi_over_q",
            "qRg",
            "qD",
            "qR",
            "ln_I",
            "log10_I",
            "qI",
            "q2I",
            "q3I",
            "q4I",
            "q_alpha_I",
            "local_slope",
            "I_over_ref",
            "I_minus_ref",
            unit_roles={
                "q2": "q_squared", "ln_q": "log_q_natural", "log10_q": "log_q_base10",
                "inv_q": "length", "d_2pi_over_q": "length", "qRg": "dimensionless",
                "qD": "dimensionless", "qR": "dimensionless", "ln_I": "log_intensity_natural",
                "log10_I": "log_intensity_base10", "qI": "q_intensity", "q2I": "q2_intensity",
                "q3I": "q3_intensity", "q4I": "q4_intensity", "q_alpha_I": "q_alpha_intensity",
                "local_slope": "dimensionless", "I_over_ref": "dimensionless", "I_minus_ref": "intensity",
            },
        ),
    ),
    "guinier": MethodSpec(
        "guinier",
        "guinier",
        _metrics(
            "Rg",
            "I0",
            "slope",
            "intercept",
            "q_start",
            "q_end",
            "qminRg",
            "qmaxRg",
            "R2",
            "chi_square",
            "reduced_chi_square",
            "rmse",
            "fit_points",
            "excluded_points",
            "weighted_fit",
            unit_roles={
                "Rg": "length", "I0": "intensity", "slope": "guinier_slope",
                "intercept": "log_intensity_natural", "q_start": "q", "q_end": "q",
                "qminRg": "dimensionless", "qmaxRg": "dimensionless", "R2": "dimensionless",
                "chi_square": "dimensionless", "reduced_chi_square": "dimensionless",
                "rmse": "log_residual", "fit_points": "count", "excluded_points": "count",
                "weighted_fit": "boolean",
            },
        ),
        range_strategy="candidate_consensus",
    ),
    "power_law": MethodSpec(
        "power_law",
        "power_law",
        _metrics(
            "alpha",
            "prefactor",
            "slope",
            "intercept",
            "R2",
            "chi_square",
            "reduced_chi_square",
            "rmse",
            "fit_points",
            "excluded_points",
            "weighted_fit",
            unit_roles={
                "alpha": "dimensionless", "prefactor": "q_alpha_intensity", "slope": "dimensionless",
                "intercept": "log_prefactor", "R2": "dimensionless", "chi_square": "dimensionless",
                "reduced_chi_square": "dimensionless", "rmse": "log_residual", "fit_points": "count",
                "excluded_points": "count", "weighted_fit": "boolean",
            },
        ),
        range_strategy="candidate_consensus",
    ),
    "local_slope": MethodSpec(
        "local_slope",
        "power_law",
        _metrics("alpha_q", "plateau_count", unit_roles={"alpha_q": "dimensionless", "plateau_count": "count"}),
    ),
    "crossover": MethodSpec(
        "crossover",
        "power_law",
        _metrics(
            "crossover_q", "crossover_d", "slope_difference", "confidence",
            unit_roles={"crossover_q": "q", "crossover_d": "length", "slope_difference": "dimensionless", "confidence": "dimensionless"},
        ),
    ),
    "peaks": MethodSpec(
        "peaks",
        "peak",
        _metrics(
            "peak_count",
            "q_star",
            "d_star",
            "height",
            "area",
            "FWHM",
            "HWHM",
            "asymmetry",
            "prominence",
            "SNR",
            "correlation_length",
            unit_roles={
                "peak_count": "count", "q_star": "q", "d_star": "length", "height": "intensity",
                "area": "q_intensity", "FWHM": "q", "HWHM": "q", "asymmetry": "dimensionless",
                "prominence": "intensity", "SNR": "dimensionless", "correlation_length": "length",
            },
        ),
    ),
    "shoulders": MethodSpec(
        "shoulders",
        "peak",
        _metrics(
            "shoulder_q", "shoulder_d", "curvature", "confidence",
            unit_roles={"shoulder_q": "q", "shoulder_d": "length", "curvature": "dimensionless", "confidence": "dimensionless"},
        ),
    ),
    "oscillations": MethodSpec(
        "oscillations",
        "peak",
        _metrics(
            "extrema_count", "period", "decay",
            unit_roles={"extrema_count": "count", "period": "q", "decay": "not_estimated"},
        ),
    ),
    "porod": MethodSpec(
        "porod",
        "porod",
        _metrics(
            "alpha",
            "porod_K",
            "relative_K",
            "plateau_mean",
            "plateau_std",
            "plateau_cv",
            "noise_score",
            unit_roles={
                "alpha": "dimensionless", "porod_K": "q4_intensity", "relative_K": "dimensionless",
                "plateau_mean": "q4_intensity", "plateau_std": "q4_intensity", "plateau_cv": "dimensionless",
                "noise_score": "dimensionless",
            },
        ),
        range_strategy="candidate_consensus",
    ),
    "kratky": MethodSpec(
        "kratky",
        None,
        _metrics(
            "q_peak", "d_peak", "q2I_peak", "FWHM", "area",
            unit_roles={"q_peak": "q", "d_peak": "length", "q2I_peak": "q2_intensity", "FWHM": "q", "area": "q3_intensity"},
        ),
    ),
    "compensated": MethodSpec(
        "compensated",
        None,
        _metrics(
            "alpha", "plateau_mean", "plateau_std", "plateau_cv",
            unit_roles={"alpha": "dimensionless", "plateau_mean": "q_alpha_intensity", "plateau_std": "q_alpha_intensity", "plateau_cv": "dimensionless"},
        ),
    ),
    "invariant": MethodSpec(
        "invariant",
        None,
        _metrics(
            "Q_measured", "Q_low", "Q_mid", "Q_high", "Q_total", "volume_fraction",
            unit_roles={
                "Q_measured": "q3_intensity", "Q_low": "q3_intensity", "Q_mid": "q3_intensity",
                "Q_high": "q3_intensity", "Q_total": "q3_intensity", "volume_fraction": "dimensionless",
            },
        ),
    ),
    "integrals": MethodSpec(
        "integrals",
        None,
        _metrics(
            "integral_I",
            "integral_qI",
            "integral_q2I",
            "integral_q4I",
            "q10",
            "q50",
            "q90",
            unit_roles={
                "integral_I": "q_intensity", "integral_qI": "q2_intensity", "integral_q2I": "q3_intensity",
                "integral_q4I": "q5_intensity", "q10": "q", "q50": "q", "q90": "q",
            },
        ),
    ),
    "pr": MethodSpec(
        "pr",
        None,
        _metrics(
            "Dmax",
            "Rg_pr",
            "peak_r",
            "peak_height",
            "peak_count",
            "tail_score",
            "negative_fraction",
            "smoothness",
            "backfit_rmse",
            "backfit_chi_square",
            unit_roles={
                "Dmax": "length", "Rg_pr": "length", "peak_r": "length", "peak_height": "intensity_per_length",
                "peak_count": "count", "tail_score": "dimensionless", "negative_fraction": "dimensionless",
                "smoothness": "intensity_per_length", "backfit_rmse": "intensity", "backfit_chi_square": "dimensionless",
            },
        ),
        ("particle", "polymer", "unknown"),
        "enable_pr",
    ),
    "correlation": MethodSpec(
        "correlation",
        None,
        _metrics(
            "long_period",
            "correlation_length",
            "hard_phase_thickness",
            "soft_phase_thickness",
            "interface_thickness",
            "phase_fraction_indicator",
            unit_roles={
                "long_period": "length", "correlation_length": "length", "hard_phase_thickness": "length",
                "soft_phase_thickness": "length", "interface_thickness": "length",
                "phase_fraction_indicator": "dimensionless",
            },
        ),
        ("two_phase", "lamellar"),
        "enable_correlation",
    ),
    "lamellar": MethodSpec(
        "lamellar",
        "peak",
        _metrics("q0", "d0", "peak_orders", unit_roles={"q0": "q", "d0": "length", "peak_orders": "count"}),
        ("lamellar",),
    ),
    "shape_models": MethodSpec(
        "shape_models",
        None,
        _metrics(
            "model_name",
            "parameter_name",
            "parameter_value",
            "stderr",
            "ci95_low",
            "ci95_high",
            "bound_hit",
            "AICc",
            "BIC",
            "rank",
            unit_roles={
                "model_name": "text", "parameter_name": "text", "parameter_value": "parameter_specific",
                "stderr": "parameter_specific", "ci95_low": "parameter_specific", "ci95_high": "parameter_specific",
                "bound_hit": "boolean", "AICc": "dimensionless", "BIC": "dimensionless", "rank": "rank",
            },
        ),
        (),
        "enable_shape_models",
    ),
}


def required_method_ids() -> list[str]:
    """Return every confirmed method in its authoritative output order."""

    return list(METHOD_REGISTRY)


def applicable_method_ids(config: AutoBatchConfig) -> list[str]:
    """Return methods whose profile conditions are satisfied by ``config``."""

    output: list[str] = []
    for method_id, spec in METHOD_REGISTRY.items():
        if spec.config_flag and not bool(getattr(config, spec.config_flag)):
            continue
        if spec.sample_types and config.sample_type not in spec.sample_types:
            continue
        output.append(method_id)
    return output
