from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CurveData:
    curve_id: str
    name: str
    q: np.ndarray
    intensity: np.ndarray
    error: np.ndarray | None = None
    q_unit: str = "A^-1"
    intensity_unit: str = "a.u."
    source_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    parent_id: str | None = None
    processing_history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        q: Any,
        intensity: Any,
        error: Any | None = None,
        q_unit: str = "A^-1",
        intensity_unit: str = "a.u.",
        source_file: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        parent_id: str | None = None,
        processing_history: list[dict[str, Any]] | None = None,
    ) -> "CurveData":
        q_array = np.asarray(q, dtype=float).copy()
        intensity_array = np.asarray(intensity, dtype=float).copy()
        error_array = None if error is None else np.asarray(error, dtype=float).copy()
        return cls(
            curve_id=str(uuid4()),
            name=name,
            q=q_array,
            intensity=intensity_array,
            error=error_array,
            q_unit=q_unit,
            intensity_unit=intensity_unit,
            source_file=None if source_file is None else str(Path(source_file)),
            metadata=dict(metadata or {}),
            parent_id=parent_id,
            processing_history=list(processing_history or []),
        )

    def copy_with(
        self,
        *,
        name: str | None = None,
        q: Any | None = None,
        intensity: Any | None = None,
        error: Any | None = None,
        q_unit: str | None = None,
        intensity_unit: str | None = None,
        parent_id: str | None = None,
        history_entry: dict[str, Any] | None = None,
    ) -> "CurveData":
        history = list(self.processing_history)
        if history_entry is not None:
            history.append(history_entry)
        return CurveData.create(
            name=name or self.name,
            q=self.q if q is None else q,
            intensity=self.intensity if intensity is None else intensity,
            error=self.error if error is None else error,
            q_unit=q_unit or self.q_unit,
            intensity_unit=intensity_unit or self.intensity_unit,
            source_file=self.source_file,
            metadata=dict(self.metadata),
            parent_id=parent_id or self.curve_id,
            processing_history=history,
        )


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    count: int = 0


@dataclass
class ValidationReport:
    curve_id: str
    summary: dict[str, Any]
    issues: list[ValidationIssue] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def has_warnings(self) -> bool:
        return bool(self.issues)


@dataclass
class AnalysisResult:
    analysis_id: str
    curve_id: str
    analysis_type: str
    q_range: tuple[float, float]
    parameters: dict[str, Any]
    results: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    structured_warnings: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    software_version: str = "0.1.0"
    input_curve_version: str | None = None

    @classmethod
    def create(
        cls,
        *,
        curve: CurveData,
        analysis_type: str,
        q_range: tuple[float, float],
        parameters: dict[str, Any] | None = None,
        results: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        structured_warnings: list[dict[str, Any]] | None = None,
    ) -> "AnalysisResult":
        return cls(
            analysis_id=str(uuid4()),
            curve_id=curve.curve_id,
            analysis_type=analysis_type,
            q_range=q_range,
            parameters=dict(parameters or {}),
            results=dict(results or {}),
            warnings=list(warnings or []),
            structured_warnings=list(structured_warnings or []),
            input_curve_version=curve.curve_id,
        )


@dataclass
class CurveGroup:
    group_id: str
    name: str
    curve_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(cls, name: str, curve_ids: list[str] | None = None, metadata: dict[str, Any] | None = None) -> "CurveGroup":
        return cls(group_id=str(uuid4()), name=name, curve_ids=list(curve_ids or []), metadata=dict(metadata or {}))


@dataclass
class ComparisonResult:
    comparison_id: str
    curve_a_id: str
    curve_b_id: str
    comparison_type: str
    q: np.ndarray
    values: np.ndarray
    q_range: tuple[float, float]
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class HistoryRecord:
    record_id: str
    action_type: str
    input_ids: list[str]
    output_ids: list[str]
    parameters: dict[str, Any]
    timestamp: str = field(default_factory=utc_now_iso)
    software_version: str = "0.1.0"
    user_note: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        action_type: str,
        input_ids: list[str] | None = None,
        output_ids: list[str] | None = None,
        parameters: dict[str, Any] | None = None,
        user_note: str = "",
        warnings: list[str] | None = None,
    ) -> "HistoryRecord":
        return cls(
            record_id=str(uuid4()),
            action_type=action_type,
            input_ids=list(input_ids or []),
            output_ids=list(output_ids or []),
            parameters=dict(parameters or {}),
            user_note=user_note,
            warnings=list(warnings or []),
        )


@dataclass
class FormalRecord:
    formal_id: str
    source_type: str
    source_id: str
    title: str
    description: str = ""
    selected_at: str = field(default_factory=utc_now_iso)
    q_range: tuple[float, float] | None = None
    key_results: dict[str, Any] = field(default_factory=dict)
    figure_paths: list[str] = field(default_factory=list)
    data_paths: list[str] = field(default_factory=list)
    user_note: str = ""

    @classmethod
    def create(
        cls,
        *,
        source_type: str,
        source_id: str,
        title: str,
        description: str = "",
        q_range: tuple[float, float] | None = None,
        key_results: dict[str, Any] | None = None,
        figure_paths: list[str] | None = None,
        data_paths: list[str] | None = None,
        user_note: str = "",
    ) -> "FormalRecord":
        return cls(
            formal_id=str(uuid4()),
            source_type=source_type,
            source_id=source_id,
            title=title,
            description=description,
            q_range=q_range,
            key_results=dict(key_results or {}),
            figure_paths=list(figure_paths or []),
            data_paths=list(data_paths or []),
            user_note=user_note,
        )
