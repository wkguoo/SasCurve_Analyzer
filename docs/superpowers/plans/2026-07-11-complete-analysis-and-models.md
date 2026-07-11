# Complete Analysis and Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete method-level parameter registry, full diagnostics, uncertainty, all 10 candidate-model fits, and batch-level main-model selection for every imported curve.

**Architecture:** Keep existing scientific functions as the source algorithms, enrich their result tables where necessary, and normalize every result through one production `analysis_runner`. Centralize fit statistics and model parameter serialization so methods cannot silently omit required fields.

**Tech Stack:** Python 3.x, numpy, pandas, scipy, matplotlib, pytest; Plan 1 schemas and registry; existing SAS analysis modules.

## Global Constraints

- Prerequisite: `2026-07-11-auto-batch-foundation.md` is complete and green.
- Every registered field must exist even when its value is null; null values require an explicit status/reason.
- Every fit must retain q range, input/fit/excluded counts, weighted state, all parameter uncertainty/bounds, diagnostics, validity and residual tables.
- Fit all models listed in `AutoBatchConfig.allowed_models` for every curve; do not keep only the winning model.
- Sequential initial values may improve optimization but must never replace a current-frame fit result.
- Do not add automated material-mechanism conclusions.
- Do not modify raw curve arrays or source files.
- Do not run Git commit/push or package without explicit user authorization.

---

## File Structure

- Create `app/core/fit_diagnostics.py`: common fit statistics, parameter records, covariance/correlation and residual tables.
- Create `app/core/extended_features.py`: crossover, shoulders, oscillations, extra integrals and normalized-shape metrics.
- Create `app/core/uncertainty_analysis.py`: bootstrap and q-range sensitivity.
- Create `app/core/analysis_runner.py`: registry-driven production adapter returning `AnalysisEnvelope`.
- Create `app/core/model_selection.py`: per-frame ranking, batch main-model selection and transition flags.
- Modify `app/core/model_free.py`, `feature_extraction.py`, `model_fitting.py`, `porod_analysis.py`, `invariant_analysis.py`, `pr_analysis.py`, `correlation.py`, `lamellar_analysis.py`, and `auto_batch.py`.
- Create focused tests `test_fit_diagnostics.py`, `test_extended_features.py`, `test_complete_model_fitting.py`, `test_uncertainty_analysis.py`, `test_analysis_runner.py`, and `test_model_selection.py`.
- Extend existing method tests instead of replacing them.

### Task 1: Common Fit Diagnostics Contract

**Files:**
- Create: `app/core/fit_diagnostics.py`
- Test: `tests/test_fit_diagnostics.py`

**Interfaces:**
- Produces: `FitDiagnostics`, `parameter_records()`, `fit_diagnostics()`, `covariance_to_correlation()`, `build_residual_rows()`.
- Consumed by: all fitting functions and `analysis_runner.py`.

- [ ] **Step 1: Write failing diagnostic tests**

```python
import numpy as np

from app.core.fit_diagnostics import build_residual_rows, covariance_to_correlation, fit_diagnostics


def test_fit_diagnostics_reports_complete_statistics():
    observed = np.array([1.0, 2.0, 4.0, 8.0])
    fitted = np.array([1.1, 1.9, 4.2, 7.8])
    sigma = np.full(4, 0.2)
    result = fit_diagnostics(observed, fitted, parameter_count=2, sigma=sigma)
    assert {"dof", "rss", "wrss", "rmse", "mae", "R2", "adjusted_R2", "chi_square", "reduced_chi_square", "AIC", "AICc", "BIC"} <= result.keys()
    assert result["dof"] == 2


def test_singular_covariance_returns_null_correlations():
    correlation = covariance_to_correlation(np.array([[1.0, np.nan], [np.nan, 1.0]]))
    assert correlation[0][1] is None


def test_residual_rows_record_inclusion_and_standardized_residual():
    rows = build_residual_rows(np.array([0.1]), np.array([2.0]), np.array([1.5]), sigma=np.array([0.25]))
    assert rows[0]["residual"] == 0.5
    assert rows[0]["standardized_residual"] == 2.0
    assert rows[0]["included"] is True
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py`.

Expected: import fails for `fit_diagnostics`.

- [ ] **Step 3: Implement complete reusable statistics**

```python
from __future__ import annotations

from typing import Any

import numpy as np


def _finite_float(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def fit_diagnostics(observed, fitted, *, parameter_count: int, sigma=None) -> dict[str, Any]:
    y = np.asarray(observed, dtype=float)
    yhat = np.asarray(fitted, dtype=float)
    residual = y - yhat
    mask = np.isfinite(y) & np.isfinite(yhat)
    y, yhat, residual = y[mask], yhat[mask], residual[mask]
    n = int(y.size)
    k = int(parameter_count)
    dof = max(0, n - k)
    rss = float(np.sum(residual**2)) if n else np.nan
    mae = float(np.mean(np.abs(residual))) if n else np.nan
    rmse = float(np.sqrt(rss / n)) if n else np.nan
    tss = float(np.sum((y - np.mean(y)) ** 2)) if n else np.nan
    r2 = np.nan if not n or tss == 0 else 1.0 - rss / tss
    adjusted = np.nan if dof <= 0 or not np.isfinite(r2) else 1.0 - (1.0 - r2) * (n - 1) / dof
    variance = max(rss / max(n, 1), 1e-300) if np.isfinite(rss) else np.nan
    aic = n * np.log(variance) + 2 * k if n else np.nan
    aicc = aic + (2 * k * (k + 1)) / (n - k - 1) if n > k + 1 else np.nan
    bic = n * np.log(variance) + k * np.log(n) if n else np.nan
    wrss = chi_square = reduced = np.nan
    if sigma is not None:
        s = np.asarray(sigma, dtype=float)[mask]
        valid = np.isfinite(s) & (s > 0)
        if np.all(valid):
            wrss = chi_square = float(np.sum((residual / s) ** 2))
            reduced = chi_square / max(dof, 1)
    return {key: _finite_float(value) for key, value in {
        "n": n, "parameter_count": k, "dof": dof, "rss": rss, "wrss": wrss,
        "rmse": rmse, "mae": mae, "R2": r2, "adjusted_R2": adjusted,
        "chi_square": chi_square, "reduced_chi_square": reduced,
        "AIC": aic, "AICc": aicc, "BIC": bic,
    }.items()}


def covariance_to_correlation(covariance) -> list[list[float | None]]:
    cov = np.asarray(covariance, dtype=float)
    scale = np.sqrt(np.diag(cov))
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = cov / np.outer(scale, scale)
    return [[_finite_float(value) for value in row] for row in corr]


def build_residual_rows(q, observed, fitted, *, sigma=None) -> list[dict[str, Any]]:
    qv = np.asarray(q, dtype=float)
    y = np.asarray(observed, dtype=float)
    yhat = np.asarray(fitted, dtype=float)
    s = None if sigma is None else np.asarray(sigma, dtype=float)
    rows = []
    for index in range(qv.size):
        residual = y[index] - yhat[index]
        standard = None if s is None or not np.isfinite(s[index]) or s[index] <= 0 else residual / s[index]
        rows.append({"q": float(qv[index]), "observed": float(y[index]), "fitted": float(yhat[index]), "residual": float(residual), "standardized_residual": _finite_float(standard) if standard is not None else None, "sigma": None if s is None else _finite_float(s[index]), "weight": None if s is None or s[index] <= 0 else float(1.0 / s[index] ** 2), "included": True, "exclusion_reason": None})
    return rows
```

- [ ] **Step 4: Implement `parameter_records()` with bounds and confidence intervals**

Add a function returning one row per parameter with `name`, `value`, `unit`, `initial`, `lower_bound`, `upper_bound`, `stderr`, `ci95_low`, `ci95_high`, and `bound_hit`. Use `None` for non-finite uncertainty; never omit a key.

- [ ] **Step 5: Run tests and existing model-fit regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_model_fitting.py`.

Expected: all tests pass.

### Task 2: Complete Guinier, Power-law and Local-Slope Outputs

**Files:**
- Modify: `app/core/model_free.py`
- Test: `tests/test_model_free_complete.py`
- Extend: `tests/test_guinier.py`, `tests/test_power_law.py`, `tests/test_local_slope.py`

**Interfaces:**
- Existing public signatures remain compatible.
- `AnalysisResult.results` gains complete parameters, `fit_quality`, `residual_rows`, `excluded_rows`, and method-specific validity fields.

- [ ] **Step 1: Add failing contract tests**

```python
def test_guinier_contains_full_confirmed_contract(guinier_curve):
    result = guinier_analysis(guinier_curve, (0.01, 0.04))
    required = {"Rg", "I0", "slope", "intercept", "q_start", "q_end", "qminRg", "qmaxRg", "fit_points", "excluded_points", "weighted_fit", "fit_quality", "residual_rows"}
    assert required <= result.results.keys()
    assert {"R2", "rmse", "chi_square", "reduced_chi_square", "AICc", "BIC"} <= result.results["fit_quality"].keys()


def test_power_law_contains_alpha_prefactor_uncertainty_and_residuals(power_law_curve):
    result = power_law_analysis(power_law_curve, (0.02, 0.2))
    assert {"alpha", "prefactor", "slope", "intercept", "parameter_records", "fit_quality", "residual_rows"} <= result.results.keys()
```

- [ ] **Step 2: Run focused tests and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_model_free_complete.py`.

Expected: assertions fail for missing fields.

- [ ] **Step 3: Refactor linear fits through `fit_diagnostics()`**

Keep the existing transformations and weighted/unweighted behavior, but calculate fitted values and call:

```python
quality = fit_diagnostics(y_observed, y_fitted, parameter_count=2, sigma=transformed_sigma)
residual_rows = build_residual_rows(q_selected, y_observed, y_fitted, sigma=transformed_sigma)
```

Store q_start/end, qminRg/qmaxRg, fit/excluded counts, weighted flag, parameter records and residual rows in the result.

- [ ] **Step 4: Extend local-slope plateau rows**

Each plateau row must contain:

```python
{"plateau_id": index, "q_start": q0, "q_end": q1, "alpha_mean": mean, "alpha_std": std, "point_count": count, "stability_score": max(0.0, 1.0 - std / threshold)}
```

The point table must contain `q`, `alpha`, and `valid` for every calculable point.

- [ ] **Step 5: Run normal, invalid-domain and regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_model_free_complete.py tests\test_guinier.py tests\test_power_law.py tests\test_local_slope.py tests\test_method_warnings.py`.

Expected: all tests pass.

### Task 3: Crossover, Peak, Shoulder, Oscillation, Porod, Kratky and Integral Metrics

**Files:**
- Create: `app/core/extended_features.py`
- Modify: `app/core/feature_extraction.py`, `app/core/porod_analysis.py`, `app/core/model_free.py`
- Test: `tests/test_extended_features.py`
- Extend: `tests/test_peak_analysis.py`, `tests/test_porod_analysis.py`, `tests/test_invariant_analysis.py`

**Interfaces:**
- Produces: `detect_crossovers()`, `detect_shoulders()`, `analyze_oscillations()`, `extended_integrals()`, `normalized_shape_distance()`.

- [ ] **Step 1: Write failing synthetic-feature tests**

```python
import numpy as np

from app.core.extended_features import detect_crossovers, extended_integrals


def test_crossover_detects_known_slope_transition():
    q = np.geomspace(0.01, 1.0, 300)
    intensity = np.where(q < 0.1, q ** -2.0, 0.01 * q ** -4.0)
    rows = detect_crossovers(q, intensity, min_segment_points=20)
    assert rows
    assert abs(np.log10(rows[0]["crossover_q"] / 0.1)) < 0.15


def test_extended_integrals_report_all_required_weights():
    q = np.linspace(0.01, 0.1, 100)
    intensity = np.ones_like(q)
    result = extended_integrals(q, intensity, bands=(0.04, 0.07))
    assert {"integral_I", "integral_qI", "integral_q2I", "integral_q4I", "Q_low", "Q_mid", "Q_high", "q10", "q50", "q90"} <= result.keys()
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_extended_features.py`.

- [ ] **Step 3: Implement deterministic extended features**

Use finite positive q/I masks for log-based calculations, `np.gradient` for local-slope/curvature candidates, `scipy.signal.find_peaks` for extrema, and trapezoidal integration for all weighted integrals. Return empty lists plus objective warnings when point counts are insufficient.

Required crossover row:

```python
{"crossover_q": q_value, "crossover_d": 2.0 * np.pi / q_value, "left_alpha": left_mean, "right_alpha": right_mean, "slope_difference": abs(right_mean-left_mean), "confidence": confidence}
```

- [ ] **Step 4: Enrich existing peak/Porod/Kratky results**

Peak rows must add baseline, net height, area, FWHM, HWHM, asymmetry, prominence, SNR, correlation length, edge truncation and validity. Porod must add full plateau range/statistics and noise score. Kratky must add FWHM, area and peak-completeness status.

- [ ] **Step 5: Run focused regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_extended_features.py tests\test_peak_analysis.py tests\test_porod_analysis.py tests\test_invariant_analysis.py tests\test_plot_analysis.py`.

Expected: all tests pass.

### Task 4: Complete Conditional Advanced Analyses

**Files:**
- Modify: `app/core/invariant_analysis.py`, `app/core/pr_analysis.py`, `app/core/correlation.py`, `app/core/lamellar_analysis.py`
- Test: `tests/test_advanced_contracts.py`

**Interfaces:**
- Public functions retain signatures.
- Each result provides all registered scalars, a full point table, prerequisites, assumption-dependent status and back-fit/extrapolation diagnostics.

- [ ] **Step 1: Write failing advanced-contract tests**

```python
def test_pr_contract_contains_backfit_and_stability(pr_curve):
    result = compute_pr(pr_curve, (0.01, 0.3), dmax=100.0, regularization=1e-2)
    assert {"Dmax", "Rg_pr", "peak_r", "peak_height", "peak_count", "tail_score", "negative_fraction", "smoothness", "backfit_rmse", "backfit_chi_square"} <= result.results.keys()
    assert "pr_distribution" in result.results["export_tables"]


def test_conditional_absolute_quantities_are_null_with_reason_without_contrast(curve):
    result = invariant_with_extrapolation(curve, (0.01, 0.2), absolute_intensity=False, contrast=None)
    assert result.results["volume_fraction"] is None
    assert result.results["volume_fraction_status"] == "missing_prerequisite"
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_advanced_contracts.py`.

- [ ] **Step 3: Add explicit conditional fields and point tables**

For every unavailable absolute quantity add `<metric>_status` and `<metric>_invalid_reason`. P(r) adds r/P(r), back-calculated I(q), Dmax/regularization inputs and stability metrics. Correlation adds r/correlation point tables and long-period/thickness parameters. Lamellar adds q0/d0, order index and deviation from integer order.

- [ ] **Step 4: Preserve assumption-dependent reliability**

Ensure these methods never return `high` solely from numerical convergence when structural prerequisites are assumptions. Add validity tests for sample type, absolute intensity, contrast, q extrapolation and plateau validity.

- [ ] **Step 5: Run advanced regression tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_advanced_contracts.py tests\test_pr_analysis.py tests\test_correlation.py tests\test_lamellar_analysis.py tests\test_invariant_analysis.py tests\test_method_warnings.py`.

Expected: all tests pass.

### Task 5: Complete 10-Model Fits, Multi-Start Retries and Derived Parameters

**Files:**
- Modify: `app/core/model_fitting.py`
- Create: `app/core/model_parameters.py`
- Test: `tests/test_complete_model_fitting.py`
- Extend: `tests/test_shape_models.py`, `tests/test_model_fitting.py`

**Interfaces:**
- Produces: `fit_shape_model_complete(...)`, `fit_all_allowed_models(...)`, `derived_model_parameters(model_name, parameters, q_unit)`.
- Existing `fit_shape_model()` remains compatible and delegates to the complete implementation.

- [ ] **Step 1: Write failing complete-model tests**

```python
import numpy as np

from app.core.shape_models import MODEL_SPECS


def test_every_model_exports_all_parameter_metadata(model_curve_factory):
    for model_name, spec in MODEL_SPECS.items():
        curve = model_curve_factory(model_name)
        result = fit_shape_model(curve, (curve.q.min(), curve.q.max()), model_name)
        records = {row["name"]: row for row in result.results["parameter_records"]}
        assert set(spec.parameter_names) == set(records)
        for row in records.values():
            assert {"value", "unit", "initial", "lower_bound", "upper_bound", "stderr", "ci95_low", "ci95_high", "bound_hit"} <= row.keys()
        assert {"fit_quality", "covariance", "parameter_correlation", "covariance_condition_number", "max_abs_parameter_correlation", "identifiability_status", "residual_rows", "derived_parameters", "attempts"} <= result.results.keys()


def test_noiseless_synthetic_models_reproduce_forward_curve(model_curve_factory):
    for model_name in MODEL_SPECS:
        curve = model_curve_factory(model_name)
        result = fit_shape_model(curve, (curve.q.min(), curve.q.max()), model_name)
        assert result.results["converged"] is True
        assert result.results["fit_quality"]["rmse"] <= 1e-4 * max(1.0, float(np.max(np.abs(curve.intensity))))


def test_high_parameter_correlation_is_not_reported_as_unique(core_shell_degenerate_curve):
    result = fit_shape_model(core_shell_degenerate_curve, (core_shell_degenerate_curve.q.min(), core_shell_degenerate_curve.q.max()), "core_shell_sphere")
    assert result.results["identifiability_status"] in {"weak", "non_identifiable"}
    assert result.results["max_abs_parameter_correlation"] >= 0.95
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_complete_model_fitting.py`.

- [ ] **Step 3: Centralize model-derived parameters**

Implement exact mappings:

```python
DERIVED_PARAMETER_BUILDERS = {
    "sphere": lambda p: {"diameter": 2*p["radius"], "geometric_Rg": (3/5) ** 0.5 * p["radius"], "volume": 4*np.pi*p["radius"]**3/3},
    "core_shell_sphere": lambda p: {"total_radius": p["core_radius"]+p["shell_thickness"], "core_diameter": 2*p["core_radius"], "total_diameter": 2*(p["core_radius"]+p["shell_thickness"])},
    "ellipsoid": lambda p: {"axis_ratio": p["polar_radius"]/p["equatorial_radius"], "volume": 4*np.pi*p["equatorial_radius"]**2*p["polar_radius"]/3},
    "cylinder": lambda p: {"diameter": 2*p["radius"], "aspect_ratio": p["length"]/(2*p["radius"]), "volume": np.pi*p["radius"]**2*p["length"]},
    "disk": lambda p: {"diameter": 2*p["radius"], "aspect_ratio": p["thickness"]/(2*p["radius"]), "volume": np.pi*p["radius"]**2*p["thickness"]},
    "surface_fractal": lambda p: {"Porod_exponent": 6-p["surface_dimension"]},
    "lamellar_peak_stack": lambda p: {"d0": 2*np.pi/p["q0"], "Gaussian_FWHM": 2*np.sqrt(2*np.log(2))*p["width"]},
}
```

Guard every division/domain and return null plus reason when invalid.

- [ ] **Step 4: Add complete diagnostics and retry attempts**

Use `fit_diagnostics`, `parameter_records`, covariance/correlation and residual rows. Calculate the finite covariance condition number and the maximum absolute off-diagonal parameter correlation. Set `identifiability_status` to `strong`, `weak`, or `non_identifiable` using documented thresholds; a numerically converged but non-identifiable fit cannot receive high reliability. Store every attempted initial vector with status/error. Retry order is warm-start, batch-median, defaults, then deterministic jittered multi-starts. The selected attempt is the valid result with minimum AICc.

- [ ] **Step 5: Fit all allowed models without early exit**

```python
def fit_all_allowed_models(curve, q_range, model_names, *, warm_starts=None, median_starts=None):
    results = []
    for name in model_names:
        results.append(fit_shape_model_complete(curve, q_range, name, warm_start=(warm_starts or {}).get(name), median_start=(median_starts or {}).get(name)))
    return results
```

Catch model-specific failures and return a failed `AnalysisResult`; never abort other models.

- [ ] **Step 6: Run all model tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_complete_model_fitting.py tests\test_model_fitting.py tests\test_shape_models.py`.

Expected: all tests pass for all 10 models.

### Task 6: Bootstrap and q-Range Sensitivity

**Files:**
- Create: `app/core/uncertainty_analysis.py`
- Test: `tests/test_uncertainty_analysis.py`

**Interfaces:**
- Produces: `bootstrap_fit()`, `range_sensitivity()`, `UncertaintySummary`.

- [ ] **Step 1: Write deterministic failing tests**

```python
def test_bootstrap_is_reproducible(simple_fit_callback):
    first = bootstrap_fit(simple_fit_callback, sample_count=50, seed=123)
    second = bootstrap_fit(simple_fit_callback, sample_count=50, seed=123)
    assert first.parameter_quantiles == second.parameter_quantiles


def test_range_sensitivity_reports_boundary_variants(simple_range_callback):
    result = range_sensitivity(simple_range_callback, (0.01, 0.1), boundary_fraction=0.05)
    assert result.variant_count == 9
    assert result.sensitivity_score is not None
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_uncertainty_analysis.py`.

- [ ] **Step 3: Implement seeded bootstrap and nine range variants**

Bootstrap resamples included point indices with replacement. Range sensitivity evaluates all combinations of lower/upper boundary shifts `(-5%, 0, +5%)`, rejecting invalid ranges. Return success/failure counts, parameter quantiles, coefficient of variation and a bounded sensitivity score.

- [ ] **Step 4: Integrate uncertainty as optional registered tables**

Run bootstrap/range sensitivity only when enabled in config and minimum valid fits are met. Store computation seed and sample count. Failures must not invalidate the primary fit.

- [ ] **Step 5: Run deterministic and method integration tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_uncertainty_analysis.py tests\test_guinier.py tests\test_power_law.py tests\test_model_fitting.py`.

Expected: all tests pass.

### Task 7: Registry-Driven Production Runner and Batch Model Selection

**Files:**
- Create: `app/core/analysis_runner.py`
- Create: `app/core/model_selection.py`
- Modify: `app/core/auto_batch.py`
- Test: `tests/test_analysis_runner.py`, `tests/test_model_selection.py`

**Interfaces:**
- Produces: `run_registered_analysis(curve, method_id, q_range, config) -> list[AnalysisEnvelope]`.
- Produces: `rank_models()`, `select_batch_main_model()`, `flag_possible_model_transitions()`.

- [ ] **Step 1: Write failing registry-completeness and ranking tests**

```python
def test_runner_returns_one_model_envelope_per_allowed_model(curve, config_all_models):
    results = run_registered_analysis(curve, "shape_models", (0.01, 0.3), config_all_models)
    assert {item.fit_quality["model_name"] for item in results} == set(config_all_models.allowed_models)


def test_batch_selector_uses_coverage_before_median_aicc(model_fit_rows):
    selected = select_batch_main_model(model_fit_rows, min_valid_coverage=0.70)
    assert selected.model_name == "sphere"


def test_transition_requires_three_consecutive_frames(sequence_rank_rows):
    flags = flag_possible_model_transitions(sequence_rank_rows, main_model="sphere", consecutive_frames=3)
    assert [row["frame_index"] for row in flags] == [4, 5, 6]
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_analysis_runner.py tests\test_model_selection.py`.

- [ ] **Step 3: Implement explicit dispatch without silent omission**

Build a dispatch dictionary from method ID to adapter. Validate every `applicable_method_ids(config)` entry has a handler at startup; raise a batch-level configuration error if a registry method has no handler. Convert `AnalysisResult` objects into `AnalysisEnvelope` objects with all registered null fields inserted.

- [ ] **Step 4: Implement ranking and fixed main model**

Rank valid fits by coverage, median AICc rank, median BIC rank, residual pass rate, bound-hit rate and uncertainty. Models below 70% valid coverage are ineligible for main-model selection but remain in detailed output.

- [ ] **Step 5: Integrate runner and selection into `run_auto_batch()`**

Replace the Plan 1 placeholder runner with `run_registered_analysis` by default. After curve-level work, add batch model rankings, main model and transition flags to `AutoBatchRun` without changing the main model per frame.

- [ ] **Step 6: Run Plan 2 focused and Plan 1 regression suites**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_model_free_complete.py tests\test_extended_features.py tests\test_advanced_contracts.py tests\test_complete_model_fitting.py tests\test_uncertainty_analysis.py tests\test_analysis_runner.py tests\test_model_selection.py tests\test_auto_batch.py
```

Expected: all focused tests pass.

### Task 8: Complete-Analysis Documentation and Full Verification

**Files:**
- Modify: `docs/method_notes.md`, `docs/developer_notes.md`, `docs/advanced_methods.md`, `CHANGELOG.md`

- [ ] **Step 1: Document every method contract and limitation**

List the exact scalar/table outputs, units, prerequisites and interpretation limits for all registered methods and models. State that complete numerical output is not proof of model uniqueness.

- [ ] **Step 2: Append the mandatory CHANGELOG entry**

Include every touched file, numerical behavior, tests, generated artifacts, success checks, raw-data safety and limitations.

- [ ] **Step 3: Run compile, focused and full suites**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m compileall -q main.py app\core app\ui
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_analysis_runner.py tests\test_model_selection.py tests\test_complete_model_fitting.py
python -B -m pytest -q -p no:cacheprovider
git diff --check
```

Expected: compile and all tests pass; diff check has no whitespace errors.

- [ ] **Step 4: Review without committing or packaging**

Run `git status --short`, inspect only intended files, and report results. Do not commit, push or package.
