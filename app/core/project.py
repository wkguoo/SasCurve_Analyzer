from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
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
    revision: int = field(default=0, init=False, repr=False, compare=False)

    def _touch(self) -> None:
        self.revision += 1

    def add_curve(self, curve: CurveData) -> None:
        self.curves.append(curve)
        self._touch()

    def get_curve(self, curve_id: str) -> CurveData | None:
        for curve in self.curves:
            if curve.curve_id == curve_id:
                return curve
        return None

    def add_analysis_result(self, result: AnalysisResult) -> None:
        self.analysis_results.append(result)
        self._touch()

    def get_results_for_curve(self, curve_id: str) -> list[AnalysisResult]:
        return [result for result in self.analysis_results if result.curve_id == curve_id]

    def add_group(self, group: CurveGroup) -> None:
        self.groups.append(group)
        self._touch()

    def add_comparison_result(self, result: ComparisonResult) -> None:
        self.comparison_results.append(result)
        self._touch()

    def add_history_record(self, record: HistoryRecord) -> None:
        self.history_records.append(record)
        self._touch()

    def add_formal_record(self, record: FormalRecord) -> None:
        self.formal_records.append(record)
        self._touch()


def _json_default(value: Any):
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def _dataclass_kwargs(cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields declared on a dataclass; ignore unknown keys."""

    allowed = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in allowed}


def _as_float_pair(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"Expected a length-2 q_range, got {value!r}.")
    return float(value[0]), float(value[1])


def _resolve_project_data_file(project_root: Path, data_file: object) -> Path:
    """Resolve a curve data path that must stay inside the project folder."""

    if not isinstance(data_file, str) or not data_file.strip():
        raise ValueError("Project curve entry is missing a valid data_file path.")
    candidate = Path(data_file)
    if candidate.is_absolute():
        raise ValueError("Project data_file must be a relative path inside the project folder.")
    root = project_root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Project data_file escapes the project folder.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Project curve data file was not found: {data_file}")
    return resolved


def save_project(project: ProjectState, folder: str | Path) -> Path:
    target_folder = Path(folder)
    target_folder.mkdir(parents=True, exist_ok=True)
    curves_folder = target_folder / "curves"
    curves_folder.mkdir(exist_ok=True)

    curve_payloads = []
    for curve in project.curves:
        curve_file = curves_folder / f"{curve.curve_id}.json"
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
        if not isinstance(curve_payload, dict):
            raise ValueError("Project curve entries must be JSON objects.")
        data_path = _resolve_project_data_file(target_folder, curve_payload.pop("data_file", None))
        data = json.loads(data_path.read_text(encoding="utf-8"))
        curve_fields = _dataclass_kwargs(CurveData, curve_payload)
        curve_fields.pop("q", None)
        curve_fields.pop("intensity", None)
        curve_fields.pop("error", None)
        curve = CurveData(
            q=np.asarray(data["q"], dtype=float),
            intensity=np.asarray(data["I"], dtype=float),
            error=None if data.get("error") is None else np.asarray(data["error"], dtype=float),
            **curve_fields,
        )
        project.add_curve(curve)

    project.groups = [CurveGroup(**_dataclass_kwargs(CurveGroup, group)) for group in payload.get("groups", [])]

    analysis_results: list[AnalysisResult] = []
    for result in payload.get("analysis_results", []):
        fields_payload = _dataclass_kwargs(AnalysisResult, result)
        if "q_range" in fields_payload:
            pair = _as_float_pair(fields_payload["q_range"])
            if pair is None:
                raise ValueError("AnalysisResult.q_range cannot be null.")
            fields_payload["q_range"] = pair
        analysis_results.append(AnalysisResult(**fields_payload))
    project.analysis_results = analysis_results

    comparison_results: list[ComparisonResult] = []
    for result in payload.get("comparison_results", []):
        if not isinstance(result, dict):
            raise ValueError("Project comparison entries must be JSON objects.")
        result_copy = dict(result)
        q = np.asarray(result_copy.pop("q"), dtype=float)
        values = np.asarray(result_copy.pop("values"), dtype=float)
        fields_payload = _dataclass_kwargs(ComparisonResult, result_copy)
        fields_payload.pop("q", None)
        fields_payload.pop("values", None)
        if "q_range" in fields_payload:
            pair = _as_float_pair(fields_payload["q_range"])
            if pair is None:
                raise ValueError("ComparisonResult.q_range cannot be null.")
            fields_payload["q_range"] = pair
        comparison_results.append(ComparisonResult(q=q, values=values, **fields_payload))
    project.comparison_results = comparison_results

    project.history_records = [
        HistoryRecord(**_dataclass_kwargs(HistoryRecord, record)) for record in payload.get("history_records", [])
    ]
    formal_records: list[FormalRecord] = []
    for record in payload.get("formal_records", []):
        fields_payload = _dataclass_kwargs(FormalRecord, record)
        if "q_range" in fields_payload and fields_payload["q_range"] is not None:
            fields_payload["q_range"] = _as_float_pair(fields_payload["q_range"])
        formal_records.append(FormalRecord(**fields_payload))
    project.formal_records = formal_records
    project.revision = 0
    return project
