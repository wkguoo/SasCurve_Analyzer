from __future__ import annotations

from app.core.model_catalog import MODEL_CATALOG, format_model_catalog_summary


def test_model_catalog_contains_common_sas_plotting_entries() -> None:
    required = {
        "linear_iq",
        "semilog_iq",
        "loglog_power_law_check",
        "guinier_plot",
        "local_slope_plot",
        "kratky_plot",
        "porod_plot",
        "invariant_integrand_plot",
        "invariant_logq_contribution_plot",
        "peak_spacing_plot",
        "q_to_d_secondary_axis",
        "shoulder_visual_check",
    }

    assert required <= set(MODEL_CATALOG)


def test_model_catalog_contains_shape_empirical_and_reserved_entries() -> None:
    required = {
        "sphere_form_factor",
        "core_shell_sphere_form_factor",
        "ellipsoid_form_factor",
        "cylinder_form_factor",
        "disk_form_factor",
        "gaussian_chain_model",
        "DAB_two_phase_model",
        "mass_fractal_empirical_model",
        "surface_fractal_empirical_model",
        "lamellar_peak_stack_model",
        "pr_inversion_interface",
        "correlation_function_interface",
        "low_q_extrapolation_interface",
        "high_q_extrapolation_interface",
    }

    assert required <= set(MODEL_CATALOG)
    for method_id in required:
        entry = MODEL_CATALOG[method_id]
        assert entry.formula
        assert entry.inputs
        assert entry.outputs
        assert entry.assumptions
        assert entry.limitations
        assert entry.status in {"model_dependent", "experimental", "reserved", "descriptive"}


def test_model_catalog_uses_user_visible_math_symbols_but_stable_ids() -> None:
    summary = format_model_catalog_summary()

    assert "q\u00b2" in summary
    assert "q\u00b3" in summary
    assert "q\u2074" in summary
    assert "\u03b1(q)" in summary
    assert "2\u03c0/q" in summary
    assert all("^" not in entry.display_name for entry in MODEL_CATALOG.values())
    assert all(" " not in method_id for method_id in MODEL_CATALOG)
