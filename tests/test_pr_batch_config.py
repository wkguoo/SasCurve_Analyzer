from __future__ import annotations

import numpy as np
import pytest

import app.core.analysis_runner as analysis_runner
from app.core.analysis_runner import run_registered_analysis
from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig
from app.core.data_model import CurveData


def _curve() -> CurveData:
    q = np.linspace(0.01, 0.2, 40)
    return CurveData.create(name="pr-batch", q=q, intensity=np.exp(-3.0 * q))


def test_pr_controls_have_solver_safe_defaults_and_validate_bounds() -> None:
    defaults = AutoBatchConfig(batch_id="pr-defaults")
    assert defaults.pr_dmax is None
    assert defaults.pr_regularization == 0.01
    assert defaults.pr_r_points == 80

    config = AutoBatchConfig(
        batch_id="pr-bounds",
        pr_dmax=25,
        pr_regularization=0,
        pr_r_points=1000,
    )
    assert config.pr_dmax == 25.0
    assert config.pr_regularization == 0.0
    assert config.pr_r_points == 1000


@pytest.mark.parametrize(
    "options",
    [
        {"pr_dmax": 0},
        {"pr_dmax": float("inf")},
        {"pr_dmax": True},
        {"pr_regularization": -0.1},
        {"pr_regularization": float("nan")},
        {"pr_regularization": True},
        {"pr_r_points": 9},
        {"pr_r_points": 1001},
        {"pr_r_points": 10.5},
        {"pr_r_points": True},
    ],
)
def test_pr_controls_reject_invalid_values(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AutoBatchConfig(batch_id="pr-invalid", **options)


def test_pr_is_missing_prerequisite_without_user_supplied_dmax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_pr_call(*_args, **_kwargs):
        pytest.fail("P(r) handler must not run without a supplied Dmax")

    monkeypatch.setattr(analysis_runner, "compute_pr", unexpected_pr_call)
    config = AutoBatchConfig(batch_id="pr-no-dmax", sample_type="particle", enable_pr=True)

    envelope = run_registered_analysis(_curve(), "pr", (0.01, 0.2), config)[0]

    assert envelope.status is AnalysisStatus.MISSING_PREREQUISITE
    assert "user-supplied positive pr_dmax" in envelope.invalid_reason
    assert {item.name: item for item in envelope.parameters}["Dmax"].value is None


def test_pr_forwards_supplied_controls_and_keeps_assumption_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_compute_pr = analysis_runner.compute_pr
    received: dict[str, object] = {}

    def record_controls(curve, q_range, dmax, regularization=None, *, r_points=80):
        received.update(dmax=dmax, regularization=regularization, r_points=r_points)
        result = actual_compute_pr(
            curve,
            q_range,
            dmax=dmax,
            regularization=regularization,
            r_points=r_points,
        )
        received["analysis_parameters"] = result.parameters
        return result

    monkeypatch.setattr(analysis_runner, "compute_pr", record_controls)
    config = AutoBatchConfig(
        batch_id="pr-supplied",
        sample_type="particle",
        enable_pr=True,
        pr_dmax=45.5,
        pr_regularization=0.03,
        pr_r_points=24,
    )

    envelope = run_registered_analysis(_curve(), "pr", (0.01, 0.2), config)[0]

    assert {key: received[key] for key in ("dmax", "regularization", "r_points")} == {
        "dmax": 45.5,
        "regularization": 0.03,
        "r_points": 24,
    }
    assert received["analysis_parameters"] == {"dmax": 45.5, "regularization": 0.03, "r_points": 24}
    assert envelope.status is AnalysisStatus.ASSUMPTION_DEPENDENT
    assert {item.name: item for item in envelope.parameters}["Dmax"].value == 45.5
    assert "user_supplied_dmax_required" in envelope.assumptions
