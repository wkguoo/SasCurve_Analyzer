# Auto Batch Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed, testable batch-analysis foundation that imports an in-situ series, merges optional metadata, resolves batch-consensus q regions, isolates failures, and returns an in-memory run object without changing raw files.

**Architecture:** Add focused core modules for schemas, metric registration, metadata/input collection, consensus-region resolution, and orchestration. Reuse `import_in_situ_series()` and `detect_auto_regions()`; do not put numerical analysis or GUI code into this plan.

**Tech Stack:** Python 3.x, dataclasses, pathlib, hashlib, csv/json, numpy, pandas, pytest; existing project modules under `app/core`.

## Global Constraints

- Input is calibrated one-dimensional q-I(q) data in `.csv`, `.txt`, or `.dat`; no detector integration, correction, or background subtraction.
- Raw input files are read-only. Do not delete, rename, move, overwrite, smooth, normalize, or modify them.
- Default batch-consensus minimum coverage is exactly `0.70`; per-frame automatic q-range fallback is disabled by default.
- Required statuses are `success`, `assumption_dependent`, `not_applicable`, `missing_prerequisite`, `fit_failed`, `invalid`, and `cancelled`.
- Preserve existing `high`, `medium`, `low`, `assumption_dependent`, and `invalid` reliability labels.
- Use only existing dependencies in this plan; do not install packages.
- Keep numerical and orchestration logic in `app/core`; no PySide6 imports in core files.
- Do not run `git commit`, `git push`, or package the application unless the user explicitly requests it.
- Update `CHANGELOG.md` and `docs/developer_notes.md` with every implemented behavior change.

---

## File Structure

- Create `app/core/auto_batch_schema.py`: status enum, typed configuration, progress event, result envelopes, run summary.
- Create `app/core/metric_registry.py`: authoritative method/model output registry and profile applicability.
- Create `app/core/batch_inputs.py`: file discovery, hashing, optional metadata CSV loading and matching; XLSX is added with `openpyxl` in Plan 4.
- Create `app/core/batch_consensus.py`: robust method-specific consensus q-range calculation.
- Create `app/core/auto_batch.py`: orchestration, progress, cancellation and partial-failure isolation.
- Create `tests/test_auto_batch_schema.py`.
- Create `tests/test_metric_registry.py`.
- Create `tests/test_batch_inputs.py`.
- Create `tests/test_batch_consensus.py`.
- Create `tests/test_auto_batch.py`.
- Modify `docs/developer_notes.md` and `CHANGELOG.md` after all focused tests pass.

### Task 1: Typed Batch Schema

**Files:**
- Create: `app/core/auto_batch_schema.py`
- Test: `tests/test_auto_batch_schema.py`

**Interfaces:**
- Produces: `AnalysisStatus`, `ParameterValue`, `AnalysisEnvelope`, `ProgressEvent`, `AutoBatchConfig`, `AutoBatchRun`.
- Consumed by: every later task and all later plans.

- [ ] **Step 1: Write the failing schema tests**

```python
from dataclasses import asdict

import pytest

from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig, ParameterValue


def test_auto_batch_config_rejects_invalid_consensus_coverage():
    with pytest.raises(ValueError, match="consensus_min_coverage"):
        AutoBatchConfig(batch_id="test", consensus_min_coverage=1.1)


def test_parameter_value_preserves_empty_value_with_reason():
    value = ParameterValue(
        name="Rg",
        value=None,
        unit="A",
        status=AnalysisStatus.MISSING_PREREQUISITE,
        invalid_reason="no valid Guinier interval",
    )
    payload = asdict(value)
    assert payload["value"] is None
    assert payload["status"] == AnalysisStatus.MISSING_PREREQUISITE
    assert payload["invalid_reason"] == "no valid Guinier interval"


def test_default_config_is_strict_batch_consensus():
    config = AutoBatchConfig(batch_id="series")
    assert config.consensus_min_coverage == 0.70
    assert config.allow_per_frame_range_fallback is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.core.auto_batch_schema'`.

- [ ] **Step 3: Implement the minimal schema**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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


@dataclass
class AutoBatchConfig:
    batch_id: str
    sample_type: str = "unknown"
    allowed_models: list[str] = field(default_factory=list)
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
```

- [ ] **Step 4: Run schema tests and verify GREEN**

Run the Step 2 command. Expected: `3 passed`.

- [ ] **Step 5: Review the diff without committing**

Run:

```powershell
git diff --check
git status --short
```

Expected: only the schema and its test are new at this checkpoint; no commit is made.

### Task 2: Authoritative Metric Registry

**Files:**
- Create: `app/core/metric_registry.py`
- Test: `tests/test_metric_registry.py`

**Interfaces:**
- Consumes: `AutoBatchConfig`.
- Produces: `MetricSpec`, `MethodSpec`, `METHOD_REGISTRY`, `required_method_ids()`, `applicable_method_ids(config)`.

- [ ] **Step 1: Write failing registry coverage tests**

```python
from app.core.metric_registry import METHOD_REGISTRY, applicable_method_ids, required_method_ids
from app.core.auto_batch_schema import AutoBatchConfig


def test_registry_contains_all_confirmed_methods():
    expected = {
        "data_quality", "derived_coordinates", "guinier", "power_law",
        "local_slope", "crossover", "peaks", "shoulders", "oscillations",
        "porod", "kratky", "compensated", "invariant", "integrals",
        "pr", "correlation", "lamellar", "shape_models",
    }
    assert expected <= set(required_method_ids())


def test_conditional_methods_follow_profile():
    base = AutoBatchConfig(batch_id="x")
    assert "pr" not in applicable_method_ids(base)
    enabled = AutoBatchConfig(batch_id="x", enable_pr=True, sample_type="particle")
    assert "pr" in applicable_method_ids(enabled)


def test_guinier_registry_contains_every_confirmed_output():
    names = {metric.name for metric in METHOD_REGISTRY["guinier"].metrics}
    assert {
        "Rg", "I0", "slope", "intercept", "q_start", "q_end",
        "qminRg", "qmaxRg", "R2", "chi_square", "reduced_chi_square",
        "rmse", "fit_points", "excluded_points", "weighted_fit",
    } <= names
```

- [ ] **Step 2: Run registry tests and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py`.

Expected: import fails because `metric_registry.py` does not exist.

- [ ] **Step 3: Implement registry types and explicit method entries**

```python
from __future__ import annotations

from dataclasses import dataclass

from app.core.auto_batch_schema import AutoBatchConfig


@dataclass(frozen=True)
class MetricSpec:
    name: str
    unit_role: str = "dimensionless"
    nullable: bool = True


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    region_type: str | None
    metrics: tuple[MetricSpec, ...]
    sample_types: tuple[str, ...] = ()
    config_flag: str | None = None


def _metrics(*names: str) -> tuple[MetricSpec, ...]:
    return tuple(MetricSpec(name) for name in names)


METHOD_REGISTRY = {
    "data_quality": MethodSpec("data_quality", None, _metrics("q_min", "q_max", "d_min", "d_max", "point_count", "I_min", "I_max", "dynamic_range", "nan_count", "negative_count", "zero_count", "duplicate_q_count", "log_usable_points")),
    "derived_coordinates": MethodSpec("derived_coordinates", None, _metrics("q2", "ln_q", "log10_q", "inv_q", "d_2pi_over_q", "qRg", "qD", "qR", "ln_I", "log10_I", "qI", "q2I", "q3I", "q4I", "q_alpha_I", "local_slope", "I_over_ref", "I_minus_ref")),
    "guinier": MethodSpec("guinier", "guinier", _metrics("Rg", "I0", "slope", "intercept", "q_start", "q_end", "qminRg", "qmaxRg", "R2", "chi_square", "reduced_chi_square", "rmse", "fit_points", "excluded_points", "weighted_fit")),
    "power_law": MethodSpec("power_law", "power_law", _metrics("alpha", "prefactor", "slope", "intercept", "R2", "chi_square", "reduced_chi_square", "rmse", "fit_points", "excluded_points", "weighted_fit")),
    "local_slope": MethodSpec("local_slope", "power_law", _metrics("alpha_q", "plateau_count")),
    "crossover": MethodSpec("crossover", "power_law", _metrics("crossover_q", "crossover_d", "slope_difference", "confidence")),
    "peaks": MethodSpec("peaks", "peak", _metrics("peak_count", "q_star", "d_star", "height", "area", "FWHM", "HWHM", "asymmetry", "prominence", "SNR", "correlation_length")),
    "shoulders": MethodSpec("shoulders", "peak", _metrics("shoulder_q", "shoulder_d", "curvature", "confidence")),
    "oscillations": MethodSpec("oscillations", "peak", _metrics("extrema_count", "period", "decay")),
    "porod": MethodSpec("porod", "porod", _metrics("alpha", "porod_K", "relative_K", "plateau_mean", "plateau_std", "plateau_cv", "noise_score")),
    "kratky": MethodSpec("kratky", None, _metrics("q_peak", "d_peak", "q2I_peak", "FWHM", "area")),
    "compensated": MethodSpec("compensated", None, _metrics("alpha", "plateau_mean", "plateau_std", "plateau_cv")),
    "invariant": MethodSpec("invariant", None, _metrics("Q_measured", "Q_low", "Q_mid", "Q_high", "Q_total", "volume_fraction")),
    "integrals": MethodSpec("integrals", None, _metrics("integral_I", "integral_qI", "integral_q2I", "integral_q4I", "q10", "q50", "q90")),
    "pr": MethodSpec("pr", None, _metrics("Dmax", "Rg_pr", "peak_r", "peak_height", "peak_count", "tail_score", "negative_fraction", "smoothness", "backfit_rmse", "backfit_chi_square"), ("particle", "polymer", "unknown"), "enable_pr"),
    "correlation": MethodSpec("correlation", None, _metrics("long_period", "correlation_length", "hard_phase_thickness", "soft_phase_thickness", "interface_thickness", "phase_fraction_indicator"), ("two_phase", "lamellar"), "enable_correlation"),
    "lamellar": MethodSpec("lamellar", "peak", _metrics("q0", "d0", "peak_orders"), ("lamellar",)),
    "shape_models": MethodSpec("shape_models", None, _metrics("model_name", "parameter_name", "parameter_value", "stderr", "ci95_low", "ci95_high", "bound_hit", "AICc", "BIC", "rank")),
}


def required_method_ids() -> list[str]:
    return list(METHOD_REGISTRY)


def applicable_method_ids(config: AutoBatchConfig) -> list[str]:
    output = []
    for method_id, spec in METHOD_REGISTRY.items():
        if spec.config_flag and not bool(getattr(config, spec.config_flag)):
            continue
        if spec.sample_types and config.sample_type not in spec.sample_types:
            continue
        output.append(method_id)
    return output
```

- [ ] **Step 4: Run registry tests and verify GREEN**

Run the Step 2 command. Expected: `3 passed`.

- [ ] **Step 5: Run schema and registry tests together**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py`.

Expected: `6 passed`.

### Task 3: Input Manifest and Optional Metadata Merge

**Files:**
- Create: `app/core/batch_inputs.py`
- Test: `tests/test_batch_inputs.py`

**Interfaces:**
- Consumes: `AutoBatchConfig`, `import_in_situ_series()`.
- Produces: `discover_curve_files(input_dir)`, `sha256_file(path)`, `load_metadata_table(path)`, `collect_batch_inputs(input_dir, config) -> BatchInputCollection`.

- [ ] **Step 1: Write failing input tests**

```python
from pathlib import Path

import pandas as pd

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_inputs import collect_batch_inputs, discover_curve_files


def test_discovery_uses_natural_sort_and_supported_extensions(tmp_path: Path):
    for name in ["sample_10.csv", "sample_2.dat", "sample_1.txt", "ignore.md"]:
        (tmp_path / name).write_text("q,I\n0.01,1\n0.02,2\n", encoding="utf-8")
    assert [p.name for p in discover_curve_files(tmp_path)] == ["sample_1.txt", "sample_2.dat", "sample_10.csv"]


def test_metadata_is_merged_without_modifying_source(tmp_path: Path):
    curve_path = tmp_path / "sample_0001.csv"
    original = b"q,I\n0.01,10\n0.02,5\n"
    curve_path.write_bytes(original)
    metadata_path = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": curve_path.name, "time_s": 5.0}]).to_csv(metadata_path, index=False)
    config = AutoBatchConfig(batch_id="sample", metadata_path=metadata_path)
    result = collect_batch_inputs(tmp_path, config)
    assert result.curves[0].metadata["time_s"] == 5.0
    assert result.manifest[0]["sha256"]
    assert curve_path.read_bytes() == original
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py`.

Expected: import fails for `app.core.batch_inputs`.

- [ ] **Step 3: Implement discovery, hashing and merge**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_import import import_in_situ_series, natural_sort_key
from app.core.data_model import CurveData


@dataclass
class BatchInputCollection:
    curves: list[CurveData]
    manifest: list[dict[str, Any]]
    failed_inputs: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def discover_curve_files(input_dir: str | Path) -> list[Path]:
    root = Path(input_dir)
    files = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in {".csv", ".txt", ".dat"}]
    return sorted(files, key=natural_sort_key)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata_table(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    raise ValueError(f"Unsupported metadata file before Plan 4: {source.suffix}")


def collect_batch_inputs(input_dir: str | Path, config: AutoBatchConfig) -> BatchInputCollection:
    paths = discover_curve_files(input_dir)
    imported = import_in_situ_series(paths)
    metadata = None if config.metadata_path is None else load_metadata_table(config.metadata_path)
    metadata_rows = {}
    if metadata is not None:
        if config.metadata_match_column not in metadata.columns:
            raise ValueError(f"Metadata match column not found: {config.metadata_match_column}")
        metadata_rows = {str(row[config.metadata_match_column]): row.to_dict() for _, row in metadata.iterrows()}
    for curve in imported.imported_curves:
        key = Path(curve.source_file or "").name
        if config.q_unit_override:
            curve.q_unit = config.q_unit_override
            curve.metadata["q_unit_source"] = "batch_config_override"
        if config.intensity_unit_override:
            curve.intensity_unit = config.intensity_unit_override
            curve.metadata["intensity_unit_source"] = "batch_config_override"
        if key in metadata_rows:
            curve.metadata.update(metadata_rows[key])
    manifest = [
        {
            "source_file": path.name,
            "source_path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "modified_time": path.stat().st_mtime,
            "sha256": sha256_file(path),
        }
        for path in paths
    ]
    return BatchInputCollection(imported.imported_curves, manifest, imported.failed_files, imported.warnings)
```

- [ ] **Step 4: Run input tests and verify GREEN**

Run the Step 2 command. Expected: `2 passed`.

- [ ] **Step 5: Run existing import regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py`.

Expected: all tests pass; existing import summary behavior is unchanged.

### Task 4: Batch-Consensus q Regions

**Files:**
- Create: `app/core/batch_consensus.py`
- Test: `tests/test_batch_consensus.py`

**Interfaces:**
- Consumes: `CurveData`, `detect_auto_regions()`, `AutoBatchConfig`.
- Produces: `ConsensusRegion`, `resolve_consensus_regions(curves, config) -> dict[str, ConsensusRegion]`.

- [ ] **Step 1: Write failing consensus tests**

```python
from app.core.auto_batch_schema import AutoBatchConfig
from app.core.batch_consensus import candidate_consensus


def test_consensus_prefers_high_coverage_over_single_high_score():
    candidates = [
        {"curve_id": "a", "q_start": 0.01, "q_end": 0.03, "score": 0.8, "fit_ready": True},
        {"curve_id": "b", "q_start": 0.011, "q_end": 0.031, "score": 0.9, "fit_ready": True},
        {"curve_id": "c", "q_start": 0.2, "q_end": 0.3, "score": 0.99, "fit_ready": True},
    ]
    result = candidate_consensus("guinier", candidates, curve_count=3, min_coverage=0.66)
    assert result is not None
    assert result.coverage == 2 / 3
    assert result.q_range[0] < 0.02


def test_consensus_returns_none_below_coverage():
    result = candidate_consensus(
        "porod",
        [{"curve_id": "a", "q_start": 0.2, "q_end": 0.3, "score": 0.9, "fit_ready": True}],
        curve_count=4,
        min_coverage=0.70,
    )
    assert result is None
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_batch_consensus.py`.

Expected: import fails for `batch_consensus`.

- [ ] **Step 3: Implement deterministic log-q clustering**

```python
from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from statistics import median
from typing import Any

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.auto_regions import detect_auto_regions
from app.core.data_model import CurveData


@dataclass(frozen=True)
class ConsensusRegion:
    region_type: str
    q_range: tuple[float, float]
    coverage: float
    median_score: float
    supporting_curve_ids: tuple[str, ...]


def candidate_consensus(region_type: str, candidates: list[dict[str, Any]], *, curve_count: int, min_coverage: float) -> ConsensusRegion | None:
    ready = [row for row in candidates if row.get("fit_ready") and row.get("q_start", 0) > 0 and row.get("q_end", 0) > row.get("q_start", 0)]
    best = None
    for anchor in ready:
        center = (log(float(anchor["q_start"])) + log(float(anchor["q_end"]))) / 2.0
        cluster = []
        for row in ready:
            row_center = (log(float(row["q_start"])) + log(float(row["q_end"]))) / 2.0
            if abs(row_center - center) <= 0.35:
                cluster.append(row)
        unique = {str(row["curve_id"]): row for row in sorted(cluster, key=lambda item: float(item["score"]))}
        rows = list(unique.values())
        coverage = len(rows) / max(curve_count, 1)
        if coverage < min_coverage:
            continue
        q_start = exp(median([log(float(row["q_start"])) for row in rows]))
        q_end = exp(median([log(float(row["q_end"])) for row in rows]))
        result = ConsensusRegion(region_type, (q_start, q_end), coverage, median([float(row["score"]) for row in rows]), tuple(sorted(unique)))
        if best is None or (result.coverage, result.median_score) > (best.coverage, best.median_score):
            best = result
    return best


def resolve_consensus_regions(curves: list[CurveData], config: AutoBatchConfig) -> dict[str, ConsensusRegion]:
    grouped: dict[str, list[dict[str, Any]]] = {"guinier": [], "power_law": [], "porod": [], "peak": []}
    for curve in curves:
        result = detect_auto_regions(curve)
        for candidate in result.results.get("candidates", []):
            region_type = str(candidate.get("region_type"))
            if region_type in grouped:
                grouped[region_type].append(candidate)
    output = {}
    for region_type, rows in grouped.items():
        consensus = candidate_consensus(region_type, rows, curve_count=len(curves), min_coverage=config.consensus_min_coverage)
        if consensus is not None:
            output[region_type] = consensus
    return output
```

- [ ] **Step 4: Run consensus tests and verify GREEN**

Run the Step 2 command. Expected: `2 passed`.

- [ ] **Step 5: Run existing auto-region regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_deep_scan.py tests\test_batch_consensus.py`.

Expected: all tests pass and `detect_auto_regions()` behavior remains unchanged.

### Task 5: Failure-Isolating Batch Orchestrator

**Files:**
- Create: `app/core/auto_batch.py`
- Test: `tests/test_auto_batch.py`

**Interfaces:**
- Consumes: `collect_batch_inputs()`, `resolve_consensus_regions()`, `applicable_method_ids()`.
- Produces: `run_auto_batch(input_dir, config, *, progress_callback=None, cancel_requested=None, analysis_runner=None) -> AutoBatchRun`.
- The injected `analysis_runner(curve, method_id, q_range, config)` always returns `list[AnalysisEnvelope]`; Plan 2 supplies the production runner and uses multiple envelopes for candidate models.

- [ ] **Step 1: Write failing orchestration tests**

```python
from pathlib import Path

from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig


def _write_curve(path: Path, scale: float) -> None:
    path.write_text(f"q,I\n0.01,{10*scale}\n0.02,{5*scale}\n0.03,{2*scale}\n", encoding="utf-8")


def test_one_method_failure_does_not_abort_batch(tmp_path: Path):
    _write_curve(tmp_path / "s_001.csv", 1)
    _write_curve(tmp_path / "s_002.csv", 2)

    def runner(curve, method_id, q_range, config):
        if curve.name == "s_001" and method_id == "power_law":
            raise RuntimeError("synthetic failure")
        return [AnalysisEnvelope(curve.curve_id, curve.name, f"{curve.name}:{method_id}", method_id, AnalysisStatus.SUCCESS, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)
    assert run.status == "partial_success"
    failed = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert len(failed) == 1
    assert failed[0].invalid_reason == "synthetic failure"


def test_cancellation_marks_remaining_work(tmp_path: Path):
    _write_curve(tmp_path / "s_001.csv", 1)
    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), cancel_requested=lambda: True)
    assert run.status == "cancelled"
```

- [ ] **Step 2: Run tests and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch.py`.

Expected: import fails for `auto_batch`.

- [ ] **Step 3: Implement orchestration and injectable runner**

```python
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig, AutoBatchRun, ProgressEvent
from app.core.batch_consensus import resolve_consensus_regions
from app.core.batch_inputs import collect_batch_inputs
from app.core.data_model import utc_now_iso
from app.core.metric_registry import applicable_method_ids


AnalysisRunner = Callable[[object, str, tuple[float, float] | None, AutoBatchConfig], list[AnalysisEnvelope]]


def _not_implemented_runner(curve, method_id, q_range, config):
    return [AnalysisEnvelope(
        curve.curve_id, curve.name, f"{curve.curve_id}:{method_id}", method_id,
        AnalysisStatus.NOT_APPLICABLE, q_range, invalid_reason="production runner is installed by Plan 2",
    )]


def run_auto_batch(
    input_dir: str | Path,
    config: AutoBatchConfig,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
    analysis_runner: AnalysisRunner | None = None,
) -> AutoBatchRun:
    collected = collect_batch_inputs(input_dir, config)
    run = AutoBatchRun(config.batch_id, curves=collected.curves, input_manifest=collected.manifest, failed_inputs=collected.failed_inputs, warnings=collected.warnings, config_snapshot=asdict(config))
    consensus = resolve_consensus_regions(collected.curves, config)
    run.consensus_regions = {name: value.q_range for name, value in consensus.items()}
    methods = applicable_method_ids(config)
    total = len(collected.curves) * len(methods)
    completed = 0
    runner = analysis_runner or _not_implemented_runner
    had_failure = bool(collected.failed_inputs)
    for curve in collected.curves:
        for method_id in methods:
            if cancel_requested and cancel_requested():
                run.status = "cancelled"
                run.finished_at = utc_now_iso()
                return run
            region_type = {"guinier": "guinier", "power_law": "power_law", "local_slope": "power_law", "crossover": "power_law", "porod": "porod", "peaks": "peak", "shoulders": "peak", "oscillations": "peak"}.get(method_id)
            q_range = run.consensus_regions.get(region_type) if region_type else (float(curve.q.min()), float(curve.q.max()))
            try:
                envelopes = runner(curve, method_id, q_range, config)
            except Exception as exc:
                had_failure = True
                envelopes = [AnalysisEnvelope(curve.curve_id, curve.name, f"{curve.curve_id}:{method_id}", method_id, AnalysisStatus.FIT_FAILED, q_range, invalid_reason=str(exc), warnings=[str(exc)])]
            run.analyses.extend(envelopes)
            completed += 1
            if progress_callback:
                progress_callback(ProgressEvent(completed, total, curve.name, method_id))
    run.status = "partial_success" if had_failure else "completed"
    run.finished_at = utc_now_iso()
    return run
```

- [ ] **Step 4: Run orchestration tests and verify GREEN**

Run the Step 2 command. Expected: `2 passed`.

- [ ] **Step 5: Run the complete Plan 1 focused suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py tests\test_io.py tests\test_batch_import.py tests\test_auto_regions.py
```

Expected: all focused tests pass.

### Task 6: Foundation Documentation and Verification

**Files:**
- Modify: `docs/developer_notes.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents the stable interfaces produced by Plan 1 for Plans 2–4.

- [ ] **Step 1: Add the exact core API documentation**

Add a section listing:

```text
AutoBatchConfig -> immutable run input after start
MetricRegistry -> authoritative output contract
collect_batch_inputs() -> curves + manifest + failures
resolve_consensus_regions() -> strict batch ranges
run_auto_batch() -> in-memory AutoBatchRun
```

- [ ] **Step 2: Append the required CHANGELOG entry**

Record date/time, objective, all added/modified files, behavior, reason, commands, outputs, success checks, raw-data safety, limitations, and that no packaging/commit/push occurred.

- [ ] **Step 3: Run compile and focused tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m compileall -q app\core
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py
```

Expected: compile exits 0 and every focused test passes.

- [ ] **Step 4: Run the full regression suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Expected: all existing and new tests pass.

- [ ] **Step 5: Review without committing or packaging**

Run `git diff --check` and `git status --short`. Expected: only intended Plan 1 files and pre-existing approved design changes are present. Do not commit, push, or package.
