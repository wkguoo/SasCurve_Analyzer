from dataclasses import FrozenInstanceError

import pytest

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.metric_registry import (
    METHOD_REGISTRY,
    applicable_method_ids,
    required_method_ids,
)


EXPECTED_METHOD_IDS = [
    "data_quality",
    "derived_coordinates",
    "guinier",
    "power_law",
    "local_slope",
    "crossover",
    "peaks",
    "shoulders",
    "oscillations",
    "porod",
    "kratky",
    "compensated",
    "invariant",
    "integrals",
    "pr",
    "correlation",
    "lamellar",
    "shape_models",
]


EXPECTED_REGISTRY = {
    "data_quality": (
        None,
        (
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
        (),
        None,
    ),
    "derived_coordinates": (
        None,
        (
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
        (),
        None,
    ),
    "guinier": (
        "guinier",
        (
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
        (),
        None,
    ),
    "power_law": (
        "power_law",
        (
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
        (),
        None,
    ),
    "local_slope": (
        "power_law",
        ("alpha_q", "plateau_count"),
        (),
        None,
    ),
    "crossover": (
        "power_law",
        ("crossover_q", "crossover_d", "slope_difference", "confidence"),
        (),
        None,
    ),
    "peaks": (
        "peak",
        (
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
        (),
        None,
    ),
    "shoulders": (
        "peak",
        ("shoulder_q", "shoulder_d", "curvature", "confidence"),
        (),
        None,
    ),
    "oscillations": (
        "peak",
        ("extrema_count", "period", "decay"),
        (),
        None,
    ),
    "porod": (
        "porod",
        (
            "alpha",
            "porod_K",
            "relative_K",
            "plateau_mean",
            "plateau_std",
            "plateau_cv",
            "noise_score",
        ),
        (),
        None,
    ),
    "kratky": (
        None,
        ("q_peak", "d_peak", "q2I_peak", "FWHM", "area"),
        (),
        None,
    ),
    "compensated": (
        None,
        ("alpha", "plateau_mean", "plateau_std", "plateau_cv"),
        (),
        None,
    ),
    "invariant": (
        None,
        ("Q_measured", "Q_low", "Q_mid", "Q_high", "Q_total", "volume_fraction"),
        (),
        None,
    ),
    "integrals": (
        None,
        (
            "integral_I",
            "integral_qI",
            "integral_q2I",
            "integral_q4I",
            "q10",
            "q50",
            "q90",
        ),
        (),
        None,
    ),
    "pr": (
        None,
        (
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
    "correlation": (
        None,
        (
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
    "lamellar": (
        "peak",
        ("q0", "d0", "peak_orders"),
        ("lamellar",),
        None,
    ),
    "shape_models": (
        None,
        (
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
        (),
        "enable_shape_models",
    ),
}


def test_required_method_ids_match_the_complete_approved_order():
    assert required_method_ids() == EXPECTED_METHOD_IDS


def test_registry_matches_every_approved_method_specification_in_order():
    assert list(METHOD_REGISTRY) == EXPECTED_METHOD_IDS
    assert list(EXPECTED_REGISTRY) == EXPECTED_METHOD_IDS

    for method_id, (
        expected_region_type,
        expected_metrics,
        expected_sample_types,
        expected_config_flag,
    ) in EXPECTED_REGISTRY.items():
        spec = METHOD_REGISTRY[method_id]
        assert spec.method_id == method_id
        assert spec.region_type == expected_region_type
        assert tuple(metric.name for metric in spec.metrics) == expected_metrics
        assert spec.sample_types == expected_sample_types
        assert spec.config_flag == expected_config_flag


@pytest.mark.parametrize(
    ("config", "expected_method_ids"),
    [
        (
            AutoBatchConfig(batch_id="default"),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="particle-pr", sample_type="particle", enable_pr=True),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "pr",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="polymer-pr", sample_type="polymer", enable_pr=True),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "pr",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="unknown-pr", sample_type="unknown", enable_pr=True),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "pr",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(
                batch_id="two-phase-correlation",
                sample_type="two_phase",
                enable_correlation=True,
            ),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "correlation",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="lamellar-off", sample_type="lamellar"),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "lamellar",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(
                batch_id="lamellar-on",
                sample_type="lamellar",
                enable_correlation=True,
            ),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "correlation",
                "lamellar",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="particle-pr-off", sample_type="particle"),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(batch_id="two-phase-correlation-off", sample_type="two_phase"),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(
                batch_id="wrong-pr-profile",
                sample_type="two_phase",
                enable_pr=True,
            ),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "shape_models",
            ],
        ),
        (
            AutoBatchConfig(
                batch_id="wrong-correlation-profile",
                sample_type="particle",
                enable_correlation=True,
            ),
            [
                "data_quality",
                "derived_coordinates",
                "guinier",
                "power_law",
                "local_slope",
                "crossover",
                "peaks",
                "shoulders",
                "oscillations",
                "porod",
                "kratky",
                "compensated",
                "invariant",
                "integrals",
                "shape_models",
            ],
        ),
    ],
    ids=[
        "default",
        "particle-pr-enabled",
        "polymer-pr-enabled",
        "unknown-pr-enabled",
        "two-phase-correlation-enabled",
        "lamellar-correlation-disabled",
        "lamellar-correlation-enabled",
        "particle-pr-disabled",
        "two-phase-correlation-disabled",
        "pr-enabled-with-wrong-sample-type",
        "correlation-enabled-with-wrong-sample-type",
    ],
)
def test_applicable_method_ids_follow_the_complete_profile_truth_matrix(
    config: AutoBatchConfig,
    expected_method_ids: list[str],
):
    expected = list(expected_method_ids)
    if not config.enable_shape_models:
        expected.remove("shape_models")
    assert applicable_method_ids(config) == expected


def test_shape_models_can_be_disabled_for_model_free_batch():
    config = AutoBatchConfig(batch_id="model-free", enable_shape_models=False)

    assert "shape_models" not in applicable_method_ids(config)


def test_shape_models_require_explicit_opt_in():
    config = AutoBatchConfig(batch_id="shape-opt-in", enable_shape_models=True)

    assert "shape_models" in applicable_method_ids(config)


def test_metric_and_method_specs_are_frozen_with_tuple_metrics():
    method_spec = METHOD_REGISTRY["guinier"]
    metric_spec = method_spec.metrics[0]

    assert all(isinstance(spec.metrics, tuple) for spec in METHOD_REGISTRY.values())

    with pytest.raises(FrozenInstanceError):
        method_spec.method_id = "changed"

    with pytest.raises(FrozenInstanceError):
        metric_spec.name = "changed"

    with pytest.raises(TypeError):
        method_spec.metrics[0] = metric_spec
