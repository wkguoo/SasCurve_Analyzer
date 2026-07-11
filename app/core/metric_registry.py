"""Authoritative method and metric definitions for automated batch analysis."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.auto_batch_schema import AutoBatchConfig


@dataclass(frozen=True)
class MetricSpec:
    """One named output metric produced by an analysis method."""

    name: str
    unit_role: str = "dimensionless"
    nullable: bool = True


@dataclass(frozen=True)
class MethodSpec:
    """The metrics and applicability conditions for one analysis method."""

    method_id: str
    region_type: str | None
    metrics: tuple[MetricSpec, ...]
    sample_types: tuple[str, ...] = ()
    config_flag: str | None = None


def _metrics(*names: str) -> tuple[MetricSpec, ...]:
    return tuple(MetricSpec(name) for name in names)


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
        ),
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
        ),
    ),
    "local_slope": MethodSpec(
        "local_slope",
        "power_law",
        _metrics("alpha_q", "plateau_count"),
    ),
    "crossover": MethodSpec(
        "crossover",
        "power_law",
        _metrics("crossover_q", "crossover_d", "slope_difference", "confidence"),
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
        ),
    ),
    "shoulders": MethodSpec(
        "shoulders",
        "peak",
        _metrics("shoulder_q", "shoulder_d", "curvature", "confidence"),
    ),
    "oscillations": MethodSpec(
        "oscillations",
        "peak",
        _metrics("extrema_count", "period", "decay"),
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
        ),
    ),
    "kratky": MethodSpec(
        "kratky",
        None,
        _metrics("q_peak", "d_peak", "q2I_peak", "FWHM", "area"),
    ),
    "compensated": MethodSpec(
        "compensated",
        None,
        _metrics("alpha", "plateau_mean", "plateau_std", "plateau_cv"),
    ),
    "invariant": MethodSpec(
        "invariant",
        None,
        _metrics("Q_measured", "Q_low", "Q_mid", "Q_high", "Q_total", "volume_fraction"),
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
        ),
        ("two_phase", "lamellar"),
        "enable_correlation",
    ),
    "lamellar": MethodSpec(
        "lamellar",
        "peak",
        _metrics("q0", "d0", "peak_orders"),
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
        ),
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
