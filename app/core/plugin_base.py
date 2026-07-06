from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from app.core.data_model import AnalysisResult, CurveData


@dataclass
class PluginExecutionResult:
    result: AnalysisResult | None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class AnalysisPlugin(ABC):
    name: str = "unnamed"
    version: str = "0.1.0"
    description: str = ""
    input_requirements: dict = {}
    output_schema: dict = {}
    warnings: list[str] = []

    @abstractmethod
    def run(self, curve: CurveData, parameters: dict) -> AnalysisResult:
        raise NotImplementedError

    def safe_run(self, curve: CurveData, parameters: dict) -> PluginExecutionResult:
        try:
            return PluginExecutionResult(result=self.run(curve, parameters), warnings=list(self.warnings))
        except Exception as exc:
            return PluginExecutionResult(result=None, warnings=list(self.warnings), error=str(exc))


class FunctionAnalysisPlugin(AnalysisPlugin):
    def __init__(
        self,
        *,
        name: str,
        version: str,
        description: str,
        function: Callable,
        input_requirements: dict | None = None,
        output_schema: dict | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.description = description
        self.function = function
        self.input_requirements = input_requirements or {"curve": "CurveData", "q_range": "tuple[float, float]"}
        self.output_schema = output_schema or {"result": "AnalysisResult"}
        self.warnings = []

    def run(self, curve: CurveData, parameters: dict) -> AnalysisResult:
        q_range = parameters.get("q_range", (float(curve.q.min()), float(curve.q.max())))
        call_parameters = {key: value for key, value in parameters.items() if key != "q_range"}
        return self.function(curve, q_range, **call_parameters)


def get_builtin_plugins() -> dict[str, AnalysisPlugin]:
    from app.core.feature_extraction import detect_peaks
    from app.core.model_free import guinier_analysis, invariant_measured, power_law_analysis

    return {
        "guinier": FunctionAnalysisPlugin(name="guinier", version="0.1.0", description="Guinier linear fit adapter.", function=guinier_analysis),
        "power_law": FunctionAnalysisPlugin(name="power_law", version="0.1.0", description="Power-law log-log fit adapter.", function=power_law_analysis),
        "peak_detection": FunctionAnalysisPlugin(name="peak_detection", version="0.1.0", description="Peak detection adapter.", function=detect_peaks),
        "invariant": FunctionAnalysisPlugin(name="invariant", version="0.1.0", description="Finite q-range invariant adapter.", function=invariant_measured),
    }
