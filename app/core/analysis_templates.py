from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from app.core.data_model import CurveData
from app.core.pipeline import PipelineStep, run_pipeline


@dataclass
class AnalysisTemplate:
    template_id: str
    name: str
    curve_type: str = "1D SAS"
    q_range: tuple[float, float] | None = None
    plot_types: list[str] = field(default_factory=lambda: ["linear", "loglog"])
    guinier_settings: dict = field(default_factory=dict)
    power_law_settings: dict = field(default_factory=dict)
    porod_settings: dict = field(default_factory=dict)
    invariant_settings: dict = field(default_factory=dict)
    peak_settings: dict = field(default_factory=dict)
    export_settings: dict = field(default_factory=dict)

    @classmethod
    def create(cls, name: str, **kwargs) -> "AnalysisTemplate":
        return cls(template_id=str(uuid4()), name=name, **kwargs)


def save_template(template: AnalysisTemplate, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(template), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_template(path: str | Path) -> AnalysisTemplate:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("q_range") is not None:
        payload["q_range"] = tuple(payload["q_range"])
    return AnalysisTemplate(**payload)


def apply_template(template: AnalysisTemplate, curves: list[CurveData]):
    steps: list[PipelineStep] = []
    for curve in curves:
        q_range = template.q_range or (float(curve.q.min()), float(curve.q.max()))
        steps.append(PipelineStep.create("validate", [curve.curve_id], {"q_range": q_range}))
        if template.guinier_settings.get("enabled", True):
            steps.append(PipelineStep.create("guinier", [curve.curve_id], {"q_range": q_range, **template.guinier_settings}))
        if template.power_law_settings.get("enabled", True):
            steps.append(PipelineStep.create("power_law", [curve.curve_id], {"q_range": q_range, **template.power_law_settings}))
        if template.invariant_settings.get("enabled", True):
            steps.append(PipelineStep.create("invariant", [curve.curve_id], {"q_range": q_range, **template.invariant_settings}))
    return run_pipeline(curves, steps, template_id=template.template_id)

