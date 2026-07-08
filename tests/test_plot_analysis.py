from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.plot_analysis import PLOT_ANALYSIS_FORMULAS, analyze_curve_plot

_trapezoid = getattr(np, "trapezoid", np.trapz)


def test_loglog_plot_analysis_recovers_power_law_alpha() -> None:
    q = np.linspace(0.01, 0.2, 80)
    alpha = 3.2
    amplitude = 5.5
    curve = CurveData.create(name="power", q=q, intensity=amplitude * q ** (-alpha))

    result = analyze_curve_plot(curve, "loglog", (float(q.min()), float(q.max())))

    assert result.results["plot_type"] == "loglog"
    np.testing.assert_allclose(result.results["alpha"], alpha, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(result.results["A"], amplitude, rtol=1e-10, atol=1e-12)
    assert result.results["fit_point_count"] == q.size
    assert result.results["export_tables"]["residuals"]


def test_guinier_plot_analysis_recovers_rg_and_i0() -> None:
    q = np.linspace(0.005, 0.06, 60)
    rg = 18.0
    i0 = 120.0
    curve = CurveData.create(name="guinier", q=q, intensity=i0 * np.exp(-(q**2) * rg**2 / 3.0))

    result = analyze_curve_plot(curve, "guinier", (float(q.min()), float(q.max())))

    np.testing.assert_allclose(result.results["Rg"], rg, rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(result.results["I0"], i0, rtol=1e-10, atol=1e-12)
    assert result.results["R2"] > 0.999999


def test_kratky_and_invariant_integrals_use_trapezoid() -> None:
    q = np.linspace(0.1, 1.0, 30)
    intensity = 2.0 + q
    curve = CurveData.create(name="integral", q=q, intensity=intensity)
    expected = _trapezoid(q**2 * intensity, q)

    kratky = analyze_curve_plot(curve, "kratky", (0.1, 1.0))
    invariant = analyze_curve_plot(curve, "invariant", (0.1, 1.0))

    np.testing.assert_allclose(kratky.results["Kratky_curve_area_in_selected_q_range"], expected)
    np.testing.assert_allclose(invariant.results["Q_measured"], expected)
    assert invariant.results["fraction_warning"] == "finite_range_only_no_extrapolation"


def test_porod_plateau_statistics_and_stability_score() -> None:
    q = np.linspace(1.0, 2.0, 20)
    constant = 7.0
    curve = CurveData.create(name="porod", q=q, intensity=constant / q**4)

    result = analyze_curve_plot(curve, "porod", (1.0, 2.0))

    np.testing.assert_allclose(result.results["q4I_plateau_mean"], constant, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(result.results["q4I_plateau_cv"], 0.0, atol=1e-12)
    np.testing.assert_allclose(result.results["plateau_stability_score"], 1.0, atol=1e-12)
    np.testing.assert_allclose(result.results["Porod_alpha_from_loglog"], 4.0, rtol=1e-10, atol=1e-12)


def test_local_slope_plot_analysis_reports_positive_alpha() -> None:
    q = np.linspace(0.01, 1.0, 100)
    alpha = 2.4
    curve = CurveData.create(name="slope", q=q, intensity=3.0 * q ** (-alpha))

    result = analyze_curve_plot(curve, "local_slope", (0.02, 0.9))

    np.testing.assert_allclose(result.results["average_alpha_in_selected_range"], alpha, rtol=1e-10, atol=1e-12)
    assert result.results["slope_plateau_regions"] == "not_implemented"
    assert any("not implemented" in warning for warning in result.warnings)


def test_log_domain_filters_nonpositive_values_without_offsets() -> None:
    curve = CurveData.create(name="invalid", q=[0.0, 0.1, 0.2], intensity=[1.0, -1.0, 4.0])

    result = analyze_curve_plot(curve, "loglog", (0.0, 0.2))

    assert result.results["fit_point_count"] < 3
    assert result.results["filtered_point_count"] > 0
    assert any("no constant was added" in warning for warning in result.warnings)


def test_plot_analysis_suppresses_unrelated_optional_derived_warnings() -> None:
    curve = CurveData.create(name="plain", q=[0.1, 0.2, 0.3], intensity=[1.0, 2.0, 3.0])

    result = analyze_curve_plot(curve, "linear", (0.1, 0.3))
    joined = "\n".join(result.warnings)

    assert "q_alpha_I is NaN" not in joined
    assert "qRg is NaN" not in joined
    assert "qD is NaN" not in joined
    assert "qR is NaN" not in joined
    assert "no reference curve was provided" not in joined


def test_linear_and_semilog_do_not_show_unrelated_local_slope_warning() -> None:
    curve = CurveData.create(name="two-points", q=[0.1, 0.2], intensity=[1.0, 2.0])

    linear = analyze_curve_plot(curve, "linear", (0.1, 0.2))
    semilog = analyze_curve_plot(curve, "semilog", (0.1, 0.2))

    assert "local_slope_dlnI_dlnq" not in "\n".join(linear.warnings)
    assert "local_slope_dlnI_dlnq" not in "\n".join(semilog.warnings)


def test_local_slope_keeps_its_own_derived_warning() -> None:
    curve = CurveData.create(name="two-points", q=[0.1, 0.2], intensity=[1.0, 2.0])

    result = analyze_curve_plot(curve, "local_slope", (0.1, 0.2))

    assert any("local_slope_dlnI_dlnq" in warning for warning in result.warnings)
    assert any("fewer than 3 rows" in warning for warning in result.warnings)


def test_semilog_keeps_nonpositive_intensity_domain_warning() -> None:
    curve = CurveData.create(name="nonpositive", q=[0.1, 0.2, 0.3], intensity=[1.0, 0.0, 3.0])

    result = analyze_curve_plot(curve, "semilog", (0.1, 0.3))

    assert any("no constant was added" in warning for warning in result.warnings)
    assert result.results["filtered_nonpositive_I_count"] == 1


def test_linear_counts_inf_as_filtered_nonfinite_fact() -> None:
    curve = CurveData.create(name="inf-linear", q=[0.1, 0.2, 0.3], intensity=[1.0, np.inf, 3.0])

    result = analyze_curve_plot(curve, "linear", (0.1, 0.3))

    assert result.results["nan_or_inf_count"] == 1
    assert result.results["filtered_point_count"] == 1
    assert any("non-finite" in warning for warning in result.warnings)


def test_plot_analysis_formulas_use_standard_user_visible_symbols() -> None:
    joined = "\n".join(PLOT_ANALYSIS_FORMULAS.values())

    assert "q^2" not in joined
    assert "q^4" not in joined
    assert "alpha(q)" not in joined
    assert "2*pi" not in joined
    assert "q²" in joined
    assert "q⁴" in joined
    assert "α(q)" in joined


def test_porod_plot_analysis_excludes_inf_from_plateau_statistics() -> None:
    curve = CurveData.create(name="finite-filter", q=[1.0, 2.0, 3.0], intensity=[2.0, np.inf, 2.0 / 81.0])

    result = analyze_curve_plot(curve, "porod", (1.0, 3.0))

    np.testing.assert_allclose(result.results["q4I_plateau_mean"], 2.0)
    assert result.results["fit_point_count"] == 2
    residuals = result.results["export_tables"]["residuals"]
    assert all(np.isfinite(row["ln_q"]) and np.isfinite(row["ln_I"]) for row in residuals)
