# In-Situ Sequence Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add continuous in-situ comparison, parameter trends, change/outlier detection, optional kinetics, PCA/clustering and heatmap outputs while preserving sequence order and scientific interpretation limits.

**Architecture:** Convert completed per-curve analyses into a stable feature matrix keyed by curve/frame. Keep curve-grid alignment, scalar-trend analysis, kinetics, multivariate exploration and figure generation in separate focused modules, then attach their outputs to `AutoBatchRun`.

**Tech Stack:** Python 3.x, numpy, pandas, scipy, matplotlib, pytest; Plan 1 and Plan 2 core interfaces.

## Global Constraints

- Prerequisites: Plans 1 and 2 are complete and all tests pass.
- Preserve natural `sequence_order`; metadata variables supplement but never silently reorder without recording the sort key.
- Calculate differences/ratios only on identical or explicitly interpolated common q grids; record interpolation method and range.
- No smoothing of raw curves. Any rolling statistic applies to scalar trend copies only and is labelled.
- Kinetics, PCA and clustering are `exploratory`; they do not prove mechanism or phase identity.
- Failed or invalid per-curve metrics remain missing; do not forward-fill them.
- Do not run Git commit/push or package without explicit user authorization.

---

## File Structure

- Create `app/core/sequence_alignment.py`: stable order, reference selection, common-q alignment, differences, ratios and normalized shape distance.
- Create `app/core/sequence_features.py`: authoritative frame-feature matrix and metric status matrix.
- Create `app/core/sequence_trends.py`: changes, slopes, change points, outliers and characteristic positions.
- Create `app/core/sequence_kinetics.py`: optional empirical/Avrami fits with full diagnostics.
- Create `app/core/sequence_statistics.py`: PCA and clustering using numpy/scipy only.
- Create `app/core/sequence_figures.py`: q-sequence heatmaps and parameter-trend figures.
- Modify `app/core/auto_batch_schema.py` and `app/core/auto_batch.py` to store sequence tables/figures.
- Add tests for each module plus `tests/test_sequence_integration.py`.

### Task 1: Stable Sequence Alignment and Curve Comparisons

**Files:**
- Create: `app/core/sequence_alignment.py`
- Test: `tests/test_sequence_alignment.py`

**Interfaces:**
- Produces: `ordered_curves()`, `align_sequence()`, `sequence_comparisons()`, `normalized_shape_distance()`.

- [ ] **Step 1: Write failing ordering and alignment tests**

```python
import numpy as np

from app.core.data_model import CurveData
from app.core.sequence_alignment import ordered_curves, sequence_comparisons


def _curve(name, q, intensity, order):
    return CurveData.create(name, q, intensity, metadata={"sequence_order": order})


def test_order_is_numeric_sequence_order_not_name_order():
    curves = [_curve("f10", [1, 2], [1, 1], 10), _curve("f2", [1, 2], [1, 1], 2)]
    assert [curve.name for curve in ordered_curves(curves)] == ["f2", "f10"]


def test_comparison_records_interpolation_and_reference():
    a = _curve("a", [0.01, 0.02, 0.03], [10, 5, 2], 0)
    b = _curve("b", [0.015, 0.025, 0.035], [12, 6, 3], 1)
    rows = sequence_comparisons([a, b], reference="first", interpolate=True)
    assert rows[0]["reference_curve_id"] == a.curve_id
    assert rows[0]["interpolated"] is True
    assert rows[0]["q_min"] == 0.015
    assert rows[0]["q_max"] == 0.03
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_alignment.py`.

- [ ] **Step 3: Implement stable ordering and common-grid alignment**

```python
def ordered_curves(curves):
    return sorted(curves, key=lambda curve: (
        curve.metadata.get("sequence_order") is None,
        curve.metadata.get("sequence_order", float("inf")),
        curve.metadata.get("frame_index", float("inf")),
        curve.name,
    ))
```

For mismatched grids, use the reference curve points inside the overlap range and `np.interp` the target curve. Return q, reference I, target I, interpolation flag, overlap range and warning. Reject ratios where the reference is zero/non-finite.

- [ ] **Step 4: Implement every approved comparison**

For first-frame, previous-frame and user-selected references, output pointwise difference, ratio and relative difference. Calculate normalized shape distances after max, q_ref, area, invariant, low/mid/high-band-mean normalization. Each distance row includes method, q range, valid point count and status.

- [ ] **Step 5: Run sequence and existing comparison tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_alignment.py tests\test_comparison.py tests\test_batch.py`.

Expected: all tests pass.

### Task 2: Frame Feature Matrix and Trend Metrics

**Files:**
- Create: `app/core/sequence_features.py`, `app/core/sequence_trends.py`
- Test: `tests/test_sequence_features.py`, `tests/test_sequence_trends.py`

**Interfaces:**
- Produces: `build_feature_matrix(run) -> pandas.DataFrame`, `build_status_matrix(run)`, `analyze_scalar_trend()`.

- [ ] **Step 1: Write failing feature/status tests**

```python
def test_feature_matrix_keeps_invalid_as_nan(auto_batch_run_fixture):
    table = build_feature_matrix(auto_batch_run_fixture)
    status = build_status_matrix(auto_batch_run_fixture)
    invalid_curve = auto_batch_run_fixture.curves[1]
    assert np.isnan(table.loc[invalid_curve.curve_id, "guinier.Rg"])
    assert status.loc[invalid_curve.curve_id, "guinier.Rg"] == "invalid"


def test_trend_reports_absolute_relative_and_outlier_fields():
    result = analyze_scalar_trend(np.arange(6), np.array([1, 2, 3, 4, 5, 50], dtype=float))
    assert {"absolute_change", "relative_change", "trend_slope", "outlier_indices", "change_points", "start_x", "peak_x", "half_x", "saturation_value"} <= result.keys()
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_features.py tests\test_sequence_trends.py`.

- [ ] **Step 3: Implement authoritative long-to-wide feature conversion**

Use only scalar `ParameterValue` records with status `success` or `assumption_dependent`. Column names are `<analysis_type>.<model_name?>.<parameter_name>`. Preserve `curve_id`, curve name, frame index, sequence order and all scalar metadata columns.

- [ ] **Step 4: Implement robust trends without filling gaps**

Fit slope only on finite pairs. Use median absolute deviation for outliers. Use piecewise mean-shift cost for change-point candidates with a minimum of three finite points per side. Start/peak/half/saturation are returned only when the finite trend has enough dynamic range; otherwise status is `invalid` with reason.

- [ ] **Step 5: Run focused tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_features.py tests\test_sequence_trends.py`.

Expected: all tests pass.

### Task 3: Optional Empirical and Avrami Kinetics

**Files:**
- Create: `app/core/sequence_kinetics.py`
- Test: `tests/test_sequence_kinetics.py`

**Interfaces:**
- Produces: `fit_empirical_saturation()`, `fit_avrami()`, each returning parameters, fit diagnostics, point rows, assumptions and status.

- [ ] **Step 1: Write failing synthetic kinetics tests**

```python
def test_avrami_recovers_seeded_synthetic_parameters():
    x = np.linspace(0, 10, 80)
    y = 2.0 + 5.0 * (1.0 - np.exp(-0.03 * x**2.0))
    result = fit_avrami(x, y)
    assert result["status"] == "success"
    assert abs(result["parameters"]["n"]["value"] - 2.0) < 0.2
    assert {"AICc", "BIC", "rmse", "R2"} <= result["fit_quality"].keys()


def test_kinetics_rejects_non_monotonic_short_series():
    result = fit_avrami(np.arange(4), np.array([1, 4, 2, 3]))
    assert result["status"] == "invalid"
    assert result["invalid_reason"]
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_kinetics.py`.

- [ ] **Step 3: Implement bounded kinetic functions**

Use `curve_fit` with:

```python
def avrami(x, baseline, amplitude, k, n, x0):
    shifted = np.maximum(np.asarray(x) - x0, 0.0)
    return baseline + amplitude * (1.0 - np.exp(-k * shifted**n))
```

Bounds require amplitude and k non-negative, `0.1 <= n <= 6`, and x0 within the observed x range. Use Plan 2 fit diagnostics and residual rows.

- [ ] **Step 4: Add applicability checks**

Require at least 8 finite points, a numeric monotonic metadata axis, nontrivial dynamic range and no dominant missing block. Mark output `exploratory`/`assumption_dependent` even when fit quality is high.

- [ ] **Step 5: Run tests**

Run the Step 2 command. Expected: all tests pass.

### Task 4: PCA and Clustering Without New Dependencies

**Files:**
- Create: `app/core/sequence_statistics.py`
- Test: `tests/test_sequence_statistics.py`

**Interfaces:**
- Produces: `prepare_exploratory_matrix()`, `pca_svd()`, `cluster_features()`.

- [ ] **Step 1: Write failing deterministic statistics tests**

```python
def test_pca_outputs_scores_loadings_and_explained_variance():
    matrix = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1]})
    result = pca_svd(matrix, component_count=2)
    assert result["scores"].shape == (4, 2)
    assert result["loadings"].shape == (3, 2)
    assert 0.999 <= sum(result["explained_variance_ratio"]) <= 1.001


def test_clustering_is_deterministic_with_seed():
    matrix = np.array([[0, 0], [0.1, 0], [10, 10], [10.1, 10]])
    first = cluster_features(matrix, cluster_count=2, seed=42)
    second = cluster_features(matrix, cluster_count=2, seed=42)
    assert first["labels"] == second["labels"]
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_statistics.py`.

- [ ] **Step 3: Implement standardized SVD PCA**

Drop columns with fewer than 70% finite values or zero variance. Median-impute remaining missing values only inside the exploratory copy, recording imputed cells. Standardize columns, run `np.linalg.svd`, and return scores/loadings/explained variance with original labels.

- [ ] **Step 4: Implement seeded scipy clustering**

Use `scipy.cluster.vq.kmeans2` with deterministic initialization from a seeded generator. Return labels, centers, point-to-center distances, retained feature names and preprocessing report. Mark all outputs exploratory.

- [ ] **Step 5: Run tests**

Run the Step 2 command. Expected: all tests pass.

### Task 5: Heatmaps and Parameter-Trend Figures

**Files:**
- Create: `app/core/sequence_figures.py`
- Test: `tests/test_sequence_figures.py`

**Interfaces:**
- Produces: `build_sequence_grid()`, `plot_sequence_heatmap()`, `plot_parameter_trends()`.

- [ ] **Step 1: Write failing figure-data tests**

```python
def test_sequence_grid_uses_common_overlap_and_reports_interpolation(curves):
    grid = build_sequence_grid(curves, point_count=200)
    assert grid.intensity.shape == (len(curves), 200)
    assert grid.interpolated is True
    assert grid.q[0] >= max(curve.q.min() for curve in curves)


def test_heatmap_export_is_nonempty(tmp_path, sequence_grid):
    target = tmp_path / "heatmap.png"
    plot_sequence_heatmap(sequence_grid, target, color_scale="log10")
    assert target.stat().st_size > 1000
```

- [ ] **Step 2: Run and verify RED**

Run with `$env:MPLBACKEND='Agg'; python -B -m pytest -q -p no:cacheprovider tests\test_sequence_figures.py`.

- [ ] **Step 3: Implement common-grid construction**

Use the intersection of valid positive q ranges and a log-spaced grid. Interpolate intensity only for visualization/sequence comparison, never mutate curves, and attach q range, grid count and warnings.

- [ ] **Step 4: Implement publication-ready figures**

Heatmap axes must be q with unit and metadata variable/frame with unit; colorbar must state I unit or log10 I. Trend figures show valid points, invalid gaps, transition/outlier markers, clear legends and 300 dpi PNG plus optional SVG.

- [ ] **Step 5: Run figure tests**

Run the Step 2 command. Expected: all tests pass.

### Task 6: Sequence Integration Into AutoBatchRun

**Files:**
- Modify: `app/core/auto_batch_schema.py`, `app/core/auto_batch.py`
- Test: `tests/test_sequence_integration.py`

**Interfaces:**
- `AutoBatchRun` gains `sequence_tables`, `sequence_figures`, `main_model`, `model_transition_flags`.
- `run_sequence_analysis(run, config)` enriches a completed run without mutating curve data.

- [ ] **Step 1: Write failing integration test**

```python
def test_completed_auto_batch_contains_sequence_outputs(in_situ_input_dir, enabled_sequence_config):
    run = run_auto_batch(in_situ_input_dir, enabled_sequence_config)
    assert {"feature_matrix", "status_matrix", "comparisons", "trends"} <= run.sequence_tables.keys()
    assert run.sequence_figures == {}  # paths are created by Plan 4 exporter
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_sequence_integration.py`.

- [ ] **Step 3: Add typed sequence fields and orchestration stage**

After per-curve/model analysis and main-model selection, call sequence alignment, feature extraction, trends, optional kinetics and optional statistics. Catch stage-level errors and retain core results with `partial_success`.

- [ ] **Step 4: Verify raw arrays remain unchanged**

Add assertions comparing every curve's q/I/error bytes before and after sequence analysis. Ensure visualization interpolation exists only in returned tables.

- [ ] **Step 5: Run Plan 3 focused suite and prior-plan regressions**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_sequence_alignment.py tests\test_sequence_features.py tests\test_sequence_trends.py tests\test_sequence_kinetics.py tests\test_sequence_statistics.py tests\test_sequence_figures.py tests\test_sequence_integration.py tests\test_auto_batch.py tests\test_analysis_runner.py tests\test_model_selection.py
```

Expected: all tests pass.

### Task 7: Sequence Documentation and Full Verification

**Files:**
- Modify: `docs/method_notes.md`, `docs/developer_notes.md`, `docs/user_manual_zh.md`, `CHANGELOG.md`

- [ ] **Step 1: Document sequence outputs and interpretation limits**

Document ordering, metadata merge, reference selection, interpolation, normalization distances, trend metrics, heatmap axes, kinetics prerequisites, missing-value handling and exploratory PCA/clustering.

- [ ] **Step 2: Append a complete CHANGELOG record**

Include files, behavior, commands, outputs, checks, no raw-data changes, and no packaging/commit/push.

- [ ] **Step 3: Run compile, focused and full suites**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m compileall -q main.py app\core app\ui
python -B -m pytest -q -p no:cacheprovider tests\test_sequence_integration.py tests\test_sequence_figures.py
python -B -m pytest -q -p no:cacheprovider
git diff --check
```

Expected: compile and all tests pass; diff check is clean.

- [ ] **Step 4: Review without committing or packaging**

Inspect `git status --short` and the diff. Do not commit, push or package.
