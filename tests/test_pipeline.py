from __future__ import annotations

from app.core.data_model import CurveData
from app.core.pipeline import PipelineStep, run_pipeline


def test_pipeline_step_create() -> None:
    step = PipelineStep.create("validate", ["curve-1"], {"q_range": (0, 1)})
    assert step.status == "pending"
    assert step.step_id


def test_pipeline_run_success_and_history() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03, 0.04, 0.05], intensity=[100, 90, 80, 70, 60])
    steps = [PipelineStep.create("validate", [curve.curve_id]), PipelineStep.create("invariant", [curve.curve_id])]
    run, analyses, history = run_pipeline([curve], steps)
    assert run.status == "completed"
    assert len(analyses) == 1
    assert len(history) == 2


def test_pipeline_failure_records_failed_step() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02], intensity=[100, 90])
    steps = [PipelineStep.create("unknown", [curve.curve_id])]
    run, _analyses, _history = run_pipeline([curve], steps)
    assert run.status == "failed"
    assert steps[0].status == "failed"
    assert steps[0].warnings

