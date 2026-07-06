from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from app.core.data_model import AnalysisResult, CurveData, HistoryRecord, utc_now_iso
from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, invariant_measured, local_slope, power_law_analysis
from app.core.validation import validate_curve


@dataclass
class PipelineStep:
    step_id: str
    step_type: str
    input_ids: list[str]
    parameters: dict
    output_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "pending"

    @classmethod
    def create(cls, step_type: str, input_ids=None, parameters=None) -> "PipelineStep":
        return cls(step_id=str(uuid4()), step_type=step_type, input_ids=list(input_ids or []), parameters=dict(parameters or {}))


@dataclass
class PipelineRun:
    pipeline_id: str
    template_id: str | None
    curve_ids: list[str]
    steps: list[PipelineStep]
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    status: str = "pending"


def run_pipeline(curves: list[CurveData], steps: list[PipelineStep], *, template_id: str | None = None) -> tuple[PipelineRun, list[AnalysisResult], list[HistoryRecord]]:
    curve_map = {curve.curve_id: curve for curve in curves}
    run = PipelineRun(pipeline_id=str(uuid4()), template_id=template_id, curve_ids=list(curve_map), steps=steps, status="running")
    analyses: list[AnalysisResult] = []
    history: list[HistoryRecord] = []
    for step in steps:
        try:
            curve = curve_map[step.input_ids[0]]
            q_range = tuple(step.parameters.get("q_range", (float(curve.q.min()), float(curve.q.max()))))
            result = None
            if step.step_type == "validate":
                report = validate_curve(curve)
                step.warnings = [issue.message for issue in report.issues]
            elif step.step_type == "guinier":
                result = guinier_analysis(curve, q_range)
            elif step.step_type == "power_law":
                result = power_law_analysis(curve, q_range)
            elif step.step_type == "local_slope":
                result = local_slope(curve, q_range)
            elif step.step_type == "peak":
                result = detect_peaks(curve, q_range, prominence=step.parameters.get("prominence"))
            elif step.step_type == "invariant":
                result = invariant_measured(curve, q_range)
            else:
                raise ValueError(f"Unsupported pipeline step_type: {step.step_type}")
            if result is not None:
                analyses.append(result)
                step.output_ids = [result.analysis_id]
                step.warnings = result.warnings
            step.status = "completed"
            history.append(HistoryRecord.create("pipeline_step", input_ids=step.input_ids, output_ids=step.output_ids, parameters=step.parameters, warnings=step.warnings))
        except Exception as exc:
            step.status = "failed"
            step.warnings.append(str(exc))
            run.status = "failed"
            run.finished_at = utc_now_iso()
            return run, analyses, history
    run.status = "completed"
    run.finished_at = utc_now_iso()
    return run, analyses, history

