from __future__ import annotations

from dataclasses import dataclass, field
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from app.core.data_model import AnalysisResult, ComparisonResult, CurveData, CurveGroup, FormalRecord, HistoryRecord


@dataclass
class ProjectState:
    curves: list[CurveData] = field(default_factory=list)
    analysis_results: list[AnalysisResult] = field(default_factory=list)
    groups: list[CurveGroup] = field(default_factory=list)
    comparison_results: list[ComparisonResult] = field(default_factory=list)
    history_records: list[HistoryRecord] = field(default_factory=list)
    formal_records: list[FormalRecord] = field(default_factory=list)

    def add_curve(self, curve: CurveData) -> None:
        self.curves.append(curve)

    def get_curve(self, curve_id: str) -> CurveData | None:
        for curve in self.curves:
            if curve.curve_id == curve_id:
                return curve
        return None

    def add_analysis_result(self, result: AnalysisResult) -> None:
        self.analysis_results.append(result)

    def get_results_for_curve(self, curve_id: str) -> list[AnalysisResult]:
        return [result for result in self.analysis_results if result.curve_id == curve_id]

    def add_group(self, group: CurveGroup) -> None:
        self.groups.append(group)

    def add_comparison_result(self, result: ComparisonResult) -> None:
        self.comparison_results.append(result)

    def add_history_record(self, record: HistoryRecord) -> None:
        self.history_records.append(record)

    def add_formal_record(self, record: FormalRecord) -> None:
        self.formal_records.append(record)


def _json_default(value: Any):
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def save_project(project: ProjectState, folder: str | Path) -> Path:
    target_folder = Path(folder)
    target_folder.mkdir(parents=True, exist_ok=True)
    curves_folder = target_folder / "curves"
    curves_folder.mkdir(exist_ok=True)

    curve_payloads = []
    for curve in project.curves:
        curve_file = curves_folder / f"{curve.curve_id}.csv"
        data = {"q": curve.q.tolist(), "I": curve.intensity.tolist(), "error": None if curve.error is None else curve.error.tolist()}
        curve_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        payload = asdict(curve)
        payload["data_file"] = str(curve_file.relative_to(target_folder))
        payload.pop("q", None)
        payload.pop("intensity", None)
        payload.pop("error", None)
        curve_payloads.append(payload)

    payload = {
        "curves": curve_payloads,
        "groups": [asdict(group) for group in project.groups],
        "analysis_results": [asdict(result) for result in project.analysis_results],
        "comparison_results": [asdict(result) for result in project.comparison_results],
        "history_records": [asdict(record) for record in project.history_records],
        "formal_records": [asdict(record) for record in project.formal_records],
    }
    project_file = target_folder / "project.json"
    project_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return project_file


def load_project(folder: str | Path) -> ProjectState:
    target_folder = Path(folder)
    payload = json.loads((target_folder / "project.json").read_text(encoding="utf-8"))
    project = ProjectState()

    for curve_payload in payload.get("curves", []):
        data = json.loads((target_folder / curve_payload.pop("data_file")).read_text(encoding="utf-8"))
        curve = CurveData(
            q=np.asarray(data["q"], dtype=float),
            intensity=np.asarray(data["I"], dtype=float),
            error=None if data.get("error") is None else np.asarray(data["error"], dtype=float),
            **curve_payload,
        )
        project.add_curve(curve)

    project.groups = [CurveGroup(**group) for group in payload.get("groups", [])]
    project.analysis_results = [AnalysisResult(**result) for result in payload.get("analysis_results", [])]
    project.comparison_results = [
        ComparisonResult(q=np.asarray(result.pop("q"), dtype=float), values=np.asarray(result.pop("values"), dtype=float), **result)
        for result in payload.get("comparison_results", [])
    ]
    project.history_records = [HistoryRecord(**record) for record in payload.get("history_records", [])]
    project.formal_records = [FormalRecord(**record) for record in payload.get("formal_records", [])]
    return project
