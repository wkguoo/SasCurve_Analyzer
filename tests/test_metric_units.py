from __future__ import annotations


import numpy as np

from app.core.analysis_runner import _envelope_from_result, run_registered_analysis
from app.core.auto_batch_schema import AutoBatchConfig
from app.core.data_model import AnalysisResult, CurveData
from app.core.metric_registry import METHOD_REGISTRY, MetricSpec


def test_failed_and_cancelled_jobs_retain_physical_units() -> None:
    from app.core.auto_batch import _failure_envelope, _cancelled_envelope
    curve = CurveData.create("sample", [0.01, 0.02], [5.0, 2.0], q_unit="A^-1", intensity_unit="cm^-1")
    for envelope in (_failure_envelope(curve, "guinier", (0.01, 0.02), "injected"),
                     _cancelled_envelope(curve, "guinier", (0.01, 0.02))):
        units = {parameter.name: parameter.unit for parameter in envelope.parameters}
        assert units["Rg"] == "A"
        assert units["I0"] == "cm^-1"


def test_guinier_units_follow_curve_and_error_parameter_records() -> None:
    q = np.linspace(0.002, 0.03, 40)
    rg = 8.0
    intensity = 125.0 * np.exp(-(rg**2) * q**2 / 3.0)
    curve = CurveData.create(
        name="weighted-guinier",
        q=q,
        intensity=intensity,
        error=np.full(q.shape, 0.2),
        q_unit="A^-1",
        intensity_unit="cm^-1",
    )

    envelope = run_registered_analysis(
        curve,
        "guinier",
        (float(q.min()), float(q.max())),
        AutoBatchConfig(batch_id="metric-units-guinier"),
    )[0]
    parameters = {parameter.name: parameter for parameter in envelope.parameters}

    assert parameters["Rg"].unit == "A"
    assert parameters["I0"].unit == "cm^-1"
    assert parameters["slope"].unit == "A^2"
    assert parameters["q_start"].unit == "A^-1"
    assert parameters["qminRg"].unit == "dimensionless"
    assert parameters["intercept"].unit == "dimensionless ln(I numeric value in cm^-1)"
    assert parameters["weighted_fit"].value is True


def test_integral_invariant_and_log_metric_units_follow_nm_curve() -> None:
    curve = CurveData.create(
        name="nm-curve",
        q=[0.1, 0.2],
        intensity=[3.0, 1.0],
        q_unit="nm^-1",
        intensity_unit="mg/mL",
    )
    result = AnalysisResult.create(
        curve=curve,
        analysis_type="synthetic",
        q_range=(0.1, 0.2),
        results={
            "q2": 0.04,
            "ln_q": -2.3,
            "qI": 0.3,
            "integral_I": 0.4,
            "integral_qI": 0.05,
            "integral_q2I": 0.01,
            "integral_q4I": 0.001,
            "Q_measured": 0.01,
            "Q_total": 0.02,
        },
    )

    derived = _envelope_from_result(curve, "derived_coordinates", result)
    derived_units = {parameter.name: parameter.unit for parameter in derived.parameters}
    assert derived_units["q2"] == "(nm^-1)^2"
    assert derived_units["ln_q"] == "dimensionless ln(q numeric value in nm^-1)"
    assert derived_units["qI"] == "(nm^-1) mg/mL"

    integrals = _envelope_from_result(curve, "integrals", result)
    integral_units = {parameter.name: parameter.unit for parameter in integrals.parameters}
    assert integral_units["integral_I"] == "(nm^-1) mg/mL"
    assert integral_units["integral_qI"] == "(nm^-1)^2 mg/mL"
    assert integral_units["integral_q2I"] == "(nm^-1)^3 mg/mL"
    assert integral_units["integral_q4I"] == "(nm^-1)^5 mg/mL"

    invariant = _envelope_from_result(curve, "invariant", result)
    invariant_units = {parameter.name: parameter.unit for parameter in invariant.parameters}
    assert invariant_units["Q_measured"] == "(nm^-1)^3 mg/mL"
    assert invariant_units["Q_total"] == "(nm^-1)^3 mg/mL"
    assert invariant_units["volume_fraction"] == "dimensionless"


def test_shape_parameter_units_remain_authoritative_in_parameter_records() -> None:
    curve = CurveData.create(name="shape", q=[0.01, 0.02], intensity=[2.0, 1.0], q_unit="nm^-1")
    records = [
        {"name": "radius", "value": 4.0, "unit": "nm", "stderr": 0.2, "ci95_low": 3.6, "ci95_high": 4.4},
        {"name": "scale", "value": 1.5, "unit": "dimensionless", "stderr": 0.1},
    ]
    result = AnalysisResult.create(
        curve=curve,
        analysis_type="shape_fit:sphere",
        q_range=(0.01, 0.02),
        results={"model_name": "sphere", "converged": True, "parameter_records": records},
    )

    envelope = _envelope_from_result(curve, "shape_models", result)
    parameters = {parameter.name: parameter for parameter in envelope.parameters}
    assert parameters["parameter_value"].unit == "parameter-specific; see parameter_records table"
    assert parameters["stderr"].unit == "parameter-specific; see parameter_records table"
    assert parameters["AICc"].unit == "dimensionless"
    assert envelope.tables["parameter_records"] == records
    assert {row["name"]: row["unit"] for row in envelope.tables["parameter_records"]} == {
        "radius": "nm",
        "scale": "dimensionless",
    }


def test_unclassified_metric_role_is_not_assumed_dimensionless() -> None:
    assert MetricSpec("future_composite_metric").unit_role == "unspecified"
    assert all(
        metric.unit_role != "unspecified"
        for method in METHOD_REGISTRY.values()
        for metric in method.metrics
    )
