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
    # Orthogonal audit dimensions. ``status`` remains the backwards-compatible
    # execution/result status used by existing callers; these fields explain
    # why a range was or was not used without conflating detection, consensus,
    # execution, and reliability.
    execution_status: str | None = None
    candidate_status: str = "not_evaluated"
    consensus_status: str = "not_required"
    detection_status: str = "not_evaluated"
    reliability_status: str = "not_evaluated"
    range_source: str = "unspecified"
    range_reason_codes: list[str] = field(default_factory=list)
    detection_reason_codes: list[str] = field(default_factory=list)
    reporting_status: str = "not_evaluated"
    reporting_reason_codes: list[str] = field(default_factory=list)
    related_analysis_ids: list[str] = field(default_factory=list)
    feature_relation: str | None = None
    q_selection_basis: str = "not_recorded"
    q_selection_evidence: str = ""
    # q-range track used by the registered fit.  ``adaptive`` is selected per
    # curve, ``common`` is the batch-comparable interval, and ``effective`` is
    # the configured hard boundary used by descriptive methods.
    range_track: str = "effective"
    common_range_supported: bool | None = None
    robustness_status: str = "not_evaluated"
    uncertainty_interpretation: str = "not_evaluated"

    def __post_init__(self) -> None:
        if self.execution_status is None:
            self.execution_status = (
                self.status.value if isinstance(self.status, AnalysisStatus) else str(self.status)
            )


@dataclass
class ProgressEvent:
    completed_units: int
    total_units: int
    curve_name: str | None
    operation: str
    message: str = ""


DEFAULT_EFFECTIVE_Q_RANGE: tuple[float, float] = (0.01, 0.5)


@dataclass
class AutoBatchConfig:
    batch_id: str
    sample_type: str = "unknown"
    allowed_models: list[str] = field(default_factory=list)
    enable_shape_models: bool = False
    effective_q_range: tuple[float, float] = DEFAULT_EFFECTIVE_Q_RANGE
    q_unit_override: str | None = None
    intensity_unit_override: str | None = None
    consensus_min_coverage: float = 0.70
    allow_per_frame_range_fallback: bool = False
    reporting_min_log_q_span_decades: float = 0.10
    range_mode: str = "dual"
    common_min_log_q_span_decades: float = 0.10
    power_law_formal_min_log_q_span_decades: float = 0.30
    porod_formal_min_log_q_span_decades: float = 0.20
    guinier_formal_qmin_rg_max: float = 0.65
    guinier_formal_qmax_rg_max: float = 1.00
    guinier_exploratory_qmax_rg_max: float = 1.30
    porod_min_log_q_position_fraction: float = 0.65
    feature_confirmed_noise_score: float = 3.0
    oscillation_candidate_min_cycles: int = 2
    oscillation_min_cycles: int = 3
    oscillation_period_cv_max: float = 0.25
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
    bootstrap_mode: str = "moving_block_residual"
    bootstrap_block_length: int = 0
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
    reference_filename_pattern: str = "-rt_"
    create_archives: bool = False

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
        if self.range_mode not in {"dual", "adaptive", "common", "legacy"}:
            raise ValueError("range_mode must be dual, adaptive, common, or legacy")
        if not isfinite(self.reporting_min_log_q_span_decades) or self.reporting_min_log_q_span_decades <= 0.0:
            raise ValueError("reporting_min_log_q_span_decades must be positive and finite")
        for name in (
            "common_min_log_q_span_decades",
            "power_law_formal_min_log_q_span_decades",
            "porod_formal_min_log_q_span_decades",
            "guinier_formal_qmin_rg_max",
            "guinier_formal_qmax_rg_max",
            "guinier_exploratory_qmax_rg_max",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if self.guinier_formal_qmax_rg_max > self.guinier_exploratory_qmax_rg_max:
            raise ValueError("guinier formal qmaxRg must not exceed exploratory qmaxRg")
        if not 0.0 <= self.porod_min_log_q_position_fraction <= 1.0:
            raise ValueError("porod_min_log_q_position_fraction must be in [0, 1]")
        if not isfinite(self.feature_confirmed_noise_score) or self.feature_confirmed_noise_score <= 0.0:
            raise ValueError("feature_confirmed_noise_score must be positive and finite")
        if self.oscillation_candidate_min_cycles < 2:
            raise ValueError("oscillation_candidate_min_cycles must be at least 2")
        if self.oscillation_min_cycles < self.oscillation_candidate_min_cycles:
            raise ValueError("oscillation_min_cycles must be >= oscillation_candidate_min_cycles")
        if not isfinite(self.oscillation_period_cv_max) or self.oscillation_period_cv_max <= 0.0:
            raise ValueError("oscillation_period_cv_max must be positive and finite")
        if self.bootstrap_samples < 1:
            raise ValueError("bootstrap_samples must be positive")
        if self.bootstrap_mode not in {"moving_block_residual", "point"}:
            raise ValueError("bootstrap_mode must be moving_block_residual or point")
        if self.bootstrap_block_length < 0:
            raise ValueError("bootstrap_block_length must be zero (automatic) or positive")
        if not 0.0 < self.sensitivity_boundary_fraction < 0.5:
            raise ValueError("sensitivity_boundary_fraction must be in (0, 0.5)")
        if self.reference_mode not in {"first", "previous", "selected"}:
            raise ValueError("reference_mode must be first, previous, or selected")
        if self.pca_components < 1 or self.cluster_count < 2:
            raise ValueError("pca_components and cluster_count are invalid")
        if not isinstance(self.reference_filename_pattern, str):
            raise ValueError("reference_filename_pattern must be a string")


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
    # Validated method-family consensus details retained for review. The
    # executable q tuples remain in ``consensus_regions`` for compatibility.
    consensus_region_details: dict[str, dict[str, Any]] = field(default_factory=dict)
    # One row per scheduled curve-method job, including jobs that used the
    # effective boundary or were unable to obtain a method-specific window.
    range_audit: list[dict[str, Any]] = field(default_factory=list)
    candidate_windows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def model_rankings(self) -> list[dict[str, Any]]:
        """Compatibility-friendly descriptive alias for batch model rankings."""

        return self.rankings

    @property
    def model_transition_flags(self) -> list[dict[str, Any]]:
        """Compatibility-friendly descriptive alias for transition review flags."""

        return self.transition_flags
