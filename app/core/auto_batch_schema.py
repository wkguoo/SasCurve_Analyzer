from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.data_model import utc_now_iso


class AnalysisStatus(str, Enum):
    SUCCESS = "success"
    ASSUMPTION_DEPENDENT = "assumption_dependent"
    NOT_APPLICABLE = "not_applicable"
    MISSING_PREREQUISITE = "missing_prerequisite"
    FIT_FAILED = "fit_failed"
    INVALID = "invalid"
    CANCELLED = "cancelled"


@dataclass
class ParameterValue:
    name: str
    value: Any
    unit: str = ""
    status: AnalysisStatus = AnalysisStatus.SUCCESS
    stderr: float | None = None
    ci95_low: float | None = None
    ci95_high: float | None = None
    initial: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    bound_hit: bool | None = None
    invalid_reason: str | None = None


@dataclass
class AnalysisEnvelope:
    curve_id: str
    curve_name: str
    analysis_id: str
    analysis_type: str
    status: AnalysisStatus
    q_range: tuple[float, float] | None
    parameters: list[ParameterValue] = field(default_factory=list)
    fit_quality: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    validity_checks: list[dict[str, Any]] = field(default_factory=list)
    reliability_label: str = "invalid"
    reliability_score: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    invalid_reason: str | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)


@dataclass
class ProgressEvent:
    completed_units: int
    total_units: int
    curve_name: str | None
    operation: str
    message: str = ""


DEFAULT_EFFECTIVE_Q_RANGE: tuple[float, float] = (0.01, 0.05)


@dataclass
class AutoBatchConfig:
    batch_id: str
    sample_type: str = "unknown"
    allowed_models: list[str] = field(default_factory=list)
    enable_shape_models: bool = True
    effective_q_range: tuple[float, float] = DEFAULT_EFFECTIVE_Q_RANGE
    q_unit_override: str | None = None
    intensity_unit_override: str | None = None
    consensus_min_coverage: float = 0.70
    allow_per_frame_range_fallback: bool = False
    metadata_path: Path | None = None
    metadata_match_column: str = "source_file"
    absolute_intensity: bool = False
    contrast: float | None = None
    volume_fraction: float | None = None
    enable_pr: bool = False
    enable_correlation: bool = False
    enable_bootstrap: bool = False
    bootstrap_samples: int = 200
    bootstrap_seed: int = 12345
    enable_range_sensitivity: bool = True
    sensitivity_boundary_fraction: float = 0.05
    enable_sequence_analysis: bool = True
    sequence_axis: str | None = None
    reference_mode: str = "first"
    reference_curve_id: str | None = None
    q_ref: float | None = None
    enable_kinetics: bool = False
    enable_exploratory_statistics: bool = False
    pca_components: int = 3
    cluster_count: int = 3
    random_seed: int = 12345

    def __post_init__(self) -> None:
        if not self.batch_id.strip():
            raise ValueError("batch_id must not be empty")
        if not isinstance(self.effective_q_range, (tuple, list)) or len(self.effective_q_range) != 2:
            raise ValueError("effective_q_range must contain two finite ascending q bounds")
        q_low, q_high = self.effective_q_range
        if isinstance(q_low, bool) or isinstance(q_high, bool):
            raise ValueError("effective_q_range must contain two finite ascending q bounds")
        try:
            q_low = float(q_low)
            q_high = float(q_high)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("effective_q_range must contain two finite ascending q bounds") from exc
        if not isfinite(q_low) or not isfinite(q_high) or q_low < 0.0 or q_low >= q_high:
            raise ValueError("effective_q_range must contain two finite ascending q bounds")
        self.effective_q_range = (q_low, q_high)
        if not 0.0 < self.consensus_min_coverage <= 1.0:
            raise ValueError("consensus_min_coverage must be in (0, 1]")
        if self.bootstrap_samples < 1:
            raise ValueError("bootstrap_samples must be positive")
        if not 0.0 < self.sensitivity_boundary_fraction < 0.5:
            raise ValueError("sensitivity_boundary_fraction must be in (0, 0.5)")
        if self.reference_mode not in {"first", "previous", "selected"}:
            raise ValueError("reference_mode must be first, previous, or selected")
        if self.pca_components < 1 or self.cluster_count < 2:
            raise ValueError("pca_components and cluster_count are invalid")


@dataclass
class AutoBatchRun:
    batch_id: str
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    status: str = "pending"
    curves: list[Any] = field(default_factory=list)
    analyses: list[AnalysisEnvelope] = field(default_factory=list)
    consensus_regions: dict[str, tuple[float, float]] = field(default_factory=dict)
    input_manifest: list[dict[str, Any]] = field(default_factory=list)
    failed_inputs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    rankings: list[dict[str, Any]] = field(default_factory=list)
    main_model: str | None = None
    transition_flags: list[dict[str, Any]] = field(default_factory=list)
    sequence_results: dict[str, Any] = field(default_factory=dict)

    @property
    def model_rankings(self) -> list[dict[str, Any]]:
        """Compatibility-friendly descriptive alias for batch model rankings."""

        return self.rankings

    @property
    def model_transition_flags(self) -> list[dict[str, Any]]:
        """Compatibility-friendly descriptive alias for transition review flags."""

        return self.transition_flags
