from __future__ import annotations

import numpy as np
import pytest

import app.core.analysis_runner as analysis_runner
from app.core.analysis_runner import BatchConfigurationError, run_registered_analysis, validate_registered_handlers
from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig
from app.core.data_model import AnalysisResult, CurveData
from app.core.metric_registry import METHOD_REGISTRY, applicable_method_ids


def _curve() -> CurveData:
    q = np.linspace(0.01, 0.2, 24)
    return CurveData.create(name="runner", q=q, intensity=np.exp(-q))


def _shape_result(
    curve: CurveData,
    model_name: str,
    *,
    converged: bool,
    aicc: float | None,
) -> AnalysisResult:
    return AnalysisResult.create(
        curve=curve,
        analysis_type=f"shape_fit:{model_name}",
        q_range=(0.01, 0.2),
        results={
            "model_name": model_name,
            "converged": converged,
            "AICc": aicc,
            "BIC": None if aicc is None else aicc + 1.0,
            "fit_quality": {"R2": 0.98 if converged else None},
            "parameter_records": [
                {
                    "name": "radius",
                    "value": 10.0 if converged else None,
                    "unit": "A",
                    "stderr": 0.2 if converged else None,
                    "bound_hit": False,
                    "invalid_reason": None if converged else "synthetic failure",
                }
            ],
            "validity_checks": [
                {"name": "fit_quality_r2", "passed": converged, "severity": "warning"}
            ],
            "reliability_label": "medium" if converged else "invalid",
            "reliability_score": 0.8 if converged else 0.0,
            "export_tables": {"fit_curves": []},
        },
        warnings=[] if converged else ["synthetic failure"],
    )


def test_registered_handlers_cover_every_registry_method() -> None:
    config = AutoBatchConfig(batch_id="runner-registry")

    assert set(analysis_runner.ANALYSIS_HANDLERS) == set(METHOD_REGISTRY)
    validate_registered_handlers(config)


def test_missing_applicable_handler_is_a_batch_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(analysis_runner.ANALYSIS_HANDLERS, "guinier")

    with pytest.raises(BatchConfigurationError, match="guinier"):
        run_registered_analysis(_curve(), "data_quality", (0.01, 0.2), AutoBatchConfig(batch_id="missing-handler"))


def test_every_applicable_registry_method_returns_registry_complete_envelopes() -> None:
    curve = CurveData.create(name="short-runner", q=[0.01, 0.02, 0.03, 0.04], intensity=[4.0, 3.0, 2.0, 1.0])
    config = AutoBatchConfig(batch_id="all-methods")

    for method_id in applicable_method_ids(config):
        envelopes = run_registered_analysis(curve, method_id, (0.01, 0.04), config)

        assert envelopes
        assert all(item.analysis_type == method_id for item in envelopes)
        assert all(
            [parameter.name for parameter in item.parameters]
            == [metric.name for metric in METHOD_REGISTRY[method_id].metrics]
            for item in envelopes
        )


@pytest.mark.parametrize(
    ("config", "method_ids"),
    [
        (AutoBatchConfig(batch_id="pr", sample_type="particle", enable_pr=True), ("pr",)),
        (AutoBatchConfig(batch_id="corr", sample_type="two_phase", enable_correlation=True), ("correlation",)),
        (AutoBatchConfig(batch_id="lam", sample_type="lamellar", enable_correlation=True), ("correlation", "lamellar")),
    ],
    ids=["pr", "correlation", "lamellar-with-correlation"],
)
def test_profile_gated_handlers_return_registry_complete_envelopes(
    config: AutoBatchConfig,
    method_ids: tuple[str, ...],
) -> None:
    curve = CurveData.create(name="short-profile", q=[0.01, 0.02, 0.03, 0.04], intensity=[4.0, 3.0, 2.0, 1.0])

    for method_id in method_ids:
        envelope = run_registered_analysis(curve, method_id, (0.01, 0.04), config)[0]
        assert envelope.analysis_type == method_id
        assert [parameter.name for parameter in envelope.parameters] == [
            metric.name for metric in METHOD_REGISTRY[method_id].metrics
        ]


def test_result_envelope_fills_every_registered_metric_with_explicit_nulls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = _curve()
    partial = AnalysisResult.create(
        curve=curve,
        analysis_type="guinier",
        q_range=(0.01, 0.2),
        results={
            "Rg": 12.0,
            "Rg_status": "available",
            "reliability_label": "medium",
            "reliability_score": 0.7,
        },
    )
    monkeypatch.setitem(analysis_runner.ANALYSIS_HANDLERS, "guinier", lambda *_args: [partial])

    envelope = run_registered_analysis(
        curve,
        "guinier",
        (0.01, 0.2),
        AutoBatchConfig(batch_id="null-fill"),
    )[0]

    values = {item.name: item for item in envelope.parameters}
    assert list(values) == [metric.name for metric in METHOD_REGISTRY["guinier"].metrics]
    assert values["Rg"].value == 12.0
    assert values["I0"].value is None
    assert values["I0"].status == AnalysisStatus.MISSING_PREREQUISITE
    assert values["I0"].invalid_reason


def test_shape_models_return_every_allowed_model_and_isolate_a_failed_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = _curve()

    def fake_fit_all(*_args, **_kwargs):
        return {
            "sphere": _shape_result(curve, "sphere", converged=True, aicc=11.0),
            "cylinder": _shape_result(curve, "cylinder", converged=False, aicc=None),
        }

    monkeypatch.setattr(analysis_runner, "fit_all_allowed_models", fake_fit_all)
    config = AutoBatchConfig(batch_id="shape-models", allowed_models=["sphere", "cylinder"])

    envelopes = run_registered_analysis(curve, "shape_models", (0.01, 0.2), config)

    assert [item.analysis_id.rsplit(":", 1)[-1] for item in envelopes] == ["sphere", "cylinder"]
    assert [item.status for item in envelopes] == [AnalysisStatus.SUCCESS, AnalysisStatus.FIT_FAILED]
    assert all(
        [parameter.name for parameter in item.parameters]
        == [metric.name for metric in METHOD_REGISTRY["shape_models"].metrics]
        for item in envelopes
    )


def test_envelope_status_is_invalid_when_reliability_label_is_invalid() -> None:
    curve = _curve()
    result = AnalysisResult.create(
        curve=curve,
        analysis_type="shape_fit:sphere",
        q_range=(0.01, 0.2),
        results={
            "model_name": "sphere",
            "converged": True,
            "AICc": 20.0,
            "reliability_label": "invalid",
            "reliability_score": 0.12,
            "parameter_records": [{"name": "radius", "value": 5.0, "unit": "A"}],
            "export_tables": {"fit_curves": []},
        },
    )

    envelope = analysis_runner._envelope_from_result(curve, "shape_models", result)

    assert envelope.status is AnalysisStatus.INVALID
    assert envelope.reliability_label == "invalid"
    assert envelope.invalid_reason
    assert "invalid" in envelope.invalid_reason
