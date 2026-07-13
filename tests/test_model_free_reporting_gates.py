from __future__ import annotations

import numpy as np
import pytest

from app.core.analysis_runner import run_registered_analysis
from app.core.auto_batch_schema import AutoBatchConfig
from app.core.data_model import CurveData


def _config() -> AutoBatchConfig:
    return AutoBatchConfig(
        batch_id="formal-gates",
        effective_q_range=(0.01, 0.5),
        enable_bootstrap=False,
        enable_range_sensitivity=True,
    )


def test_known_guinier_curve_passes_formal_qrg_and_residual_gate() -> None:
    q = np.linspace(0.01, 0.03, 80)
    rg = 20.0
    intensity = 5.0 * np.exp(-(rg**2) * q**2 / 3.0)
    curve = CurveData.create(name="guinier", q=q, intensity=intensity)

    envelope = run_registered_analysis(curve, "guinier", (0.01, 0.03), _config())[0]

    assert envelope.reporting_status == "reportable"
    assert envelope.reporting_reason_codes == ["guinier_formal_gate_passed"]
    assert envelope.uncertainty_interpretation.endswith("not_instrument_measurement_confidence_interval")


def test_guinier_curve_above_exploratory_qrg_limit_is_rejected() -> None:
    q = np.linspace(0.02, 0.08, 100)
    rg = 25.0
    intensity = 4.0 * np.exp(-(rg**2) * q**2 / 3.0)
    curve = CurveData.create(name="guinier-high-q", q=q, intensity=intensity)

    envelope = run_registered_analysis(curve, "guinier", (0.02, 0.08), _config())[0]

    assert envelope.reporting_status == "not_reportable"
    assert "guinier_qmaxrg_above_exploratory_limit" in envelope.reporting_reason_codes


def test_invalid_guinier_slope_marks_envelope_invalid_not_success() -> None:
    from app.core.auto_batch_schema import AnalysisStatus

    q = np.linspace(0.01, 0.03, 40)
    # Rising intensity produces a non-negative Guinier slope → invalid Rg.
    curve = CurveData.create(name="rising", q=q, intensity=1.0 + 50.0 * q**2)

    envelope = run_registered_analysis(curve, "guinier", (0.01, 0.03), _config())[0]
    values = {parameter.name: parameter.value for parameter in envelope.parameters}

    assert envelope.status is AnalysisStatus.INVALID
    assert values.get("Rg") is None
    assert envelope.reporting_status == "not_reportable"


def test_guinier_exports_fit_quality_metrics_on_envelope_parameters() -> None:
    q = np.linspace(0.01, 0.03, 80)
    rg = 20.0
    intensity = 5.0 * np.exp(-(rg**2) * q**2 / 3.0)
    curve = CurveData.create(name="guinier-metrics", q=q, intensity=intensity)

    envelope = run_registered_analysis(curve, "guinier", (0.01, 0.03), _config())[0]
    values = {parameter.name: parameter.value for parameter in envelope.parameters}

    # Unweighted OLS still surfaces rmse from fit_quality; chi_square stays null without sigma.
    assert values.get("rmse") is not None
    assert values.get("R2") == pytest.approx(1.0)
    assert "rmse" in envelope.fit_quality


def test_power_law_requires_formal_span_and_accepts_stable_known_exponent() -> None:
    q = np.geomspace(0.01, 0.08, 120)
    curve = CurveData.create(name="power", q=q, intensity=3.0 * q**-3.0)

    formal = run_registered_analysis(curve, "power_law", (0.01, 0.08), _config())[0]
    short = run_registered_analysis(curve, "power_law", (0.01, 0.015), _config())[0]

    assert formal.reporting_status == "reportable"
    assert formal.reporting_reason_codes == ["power_law_formal_gate_passed"]
    assert short.reporting_status == "exploratory"
    assert "power_law_span_below_formal_threshold" in short.reporting_reason_codes


def test_porod_gate_uses_alpha_plateau_span_and_high_q_position_not_r2_alone() -> None:
    q = np.geomspace(0.10, 0.50, 140)
    porod_curve = CurveData.create(name="porod", q=q, intensity=2.0 * q**-4.0)
    flat_curve = CurveData.create(name="flat-background", q=q, intensity=np.full_like(q, 2.0))

    accepted = run_registered_analysis(porod_curve, "porod", (0.10, 0.50), _config())[0]
    rejected = run_registered_analysis(flat_curve, "porod", (0.10, 0.50), _config())[0]

    assert accepted.reporting_status == "reportable"
    assert accepted.reporting_reason_codes == ["porod_formal_gate_passed"]
    assert rejected.reporting_status == "exploratory"
    assert "porod_alpha_outside_4_plus_or_minus_0_4" in rejected.reporting_reason_codes


def test_invariant_reports_finite_interval_only_without_volume_fraction() -> None:
    q = np.linspace(0.01, 0.5, 200)
    curve = CurveData.create(name="finite-invariant", q=q, intensity=np.exp(-q))

    envelope = run_registered_analysis(curve, "invariant", (0.01, 0.5), _config())[0]
    values = {parameter.name: parameter for parameter in envelope.parameters}

    assert envelope.reporting_status == "reportable"
    assert values["Q_measured"].value is not None
    assert values["Q_total"].value is None
    assert values["volume_fraction"].value is None


def test_invariant_with_negative_intensity_is_not_formally_reportable() -> None:
    q = np.linspace(0.01, 0.5, 120)
    intensity = np.exp(-q)
    intensity[20:40] = -0.5  # substantial negative contamination
    curve = CurveData.create(name="negative-invariant", q=q, intensity=intensity)

    envelope = run_registered_analysis(curve, "invariant", (0.01, 0.5), _config())[0]

    assert envelope.reporting_status in {"exploratory", "not_reportable"}
    assert "invariant_negative_intensity" in " ".join(envelope.reporting_reason_codes)

