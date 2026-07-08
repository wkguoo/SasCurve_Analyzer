# Information Budget Implementation Plan

> **Archived note:** This plan predates the current eight-main-plot contract. `invariant_contribution` is historical and must not be reintroduced as a main plot type unless a future explicit plan overrides the eight-plot contract.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a model-free information-budget analysis that shows where finite-range invariant signal is concentrated across log-q scale.

**Architecture:** Extend `app.core.model_free` with one focused analysis function that reuses the existing `AnalysisResult` shape and does not mutate `CurveData`. Extend plotting with a q^3I contribution-spectrum view, then expose the analysis and plot names through existing PySide6 combo boxes. Keep advanced extrapolation, model fitting, and batch decomposition out of this first slice.

**Tech Stack:** Python, NumPy, Matplotlib, PySide6, pytest.

---

### Task 1: Information-Budget Core Tests

**Files:**
- Modify: `tests/test_invariant.py`
- Modify: `app/core/model_free.py`

- [ ] **Step 1: Write failing test for q^3I contribution, cumulative Q, quantiles, entropy, and fractions**

```python
def test_information_budget_reports_log_q_contribution_and_quantiles() -> None:
    q = np.array([1.0, 2.0, 3.0, 4.0])
    intensity = np.ones_like(q)
    curve = CurveData.create(name="budget", q=q, intensity=intensity)

    result = information_budget(curve, (1.0, 4.0), q_bands=(2.0, 3.0))

    assert result.analysis_type == "information_budget"
    assert np.allclose(result.results["q3I"], q**3)
    assert np.isclose(result.results["Q_measured"], np.trapezoid(q**2, q))
    assert result.results["q3I_peak_q"] == 4.0
    assert np.isclose(result.results["q3I_peak_d"], 2.0 * np.pi / 4.0)
    assert result.results["q_Q10"] < result.results["q_Q50"] < result.results["q_Q90"]
    assert np.isclose(result.results["d_Q50"], 2.0 * np.pi / result.results["q_Q50"])
    assert result.results["Q_entropy"] > 0.0
    fractions = result.results["Q_low_mid_high_fraction"]
    assert set(fractions) == {"low", "mid", "high"}
    assert np.isclose(sum(fractions.values()), 1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_invariant.py::test_information_budget_reports_log_q_contribution_and_quantiles -v
```

Expected: FAIL because `information_budget` is not implemented/imported.

- [ ] **Step 3: Implement minimal core analysis**

Add `information_budget(curve, q_range, *, q_bands=None)` to `app/core/model_free.py`. Filter finite `q > 0` and finite positive or negative intensities using the existing range style; compute q^3I for log-q contribution display, finite cumulative `Q = integral(q^2 I dq)`, q quantiles at 10/50/90 percent of positive cumulative contribution, entropy of positive interval contributions, dominant q/d, observable d min/max, and low/mid/high fractions.

- [ ] **Step 4: Re-run focused test**

Run:

```powershell
python -m pytest tests/test_invariant.py::test_information_budget_reports_log_q_contribution_and_quantiles -v
```

Expected: PASS.

### Task 2: Plotting And GUI Exposure

**Files:**
- Modify: `tests/test_plotting.py`
- Modify: `app/core/plotting.py`
- Modify: `app/ui/plotting_tab.py`
- Modify: `app/ui/analysis_tab.py`
- Modify: `app/core/deep_analysis.py`

- [ ] **Step 1: Write failing plot test**

```python
def test_q3_invariant_contribution_plot_uses_log_q_axis() -> None:
    curve = CurveData.create(name="test", q=[1.0, 2.0, 4.0], intensity=[1.0, 2.0, 3.0])
    figure, warnings = create_curve_figure(curve, plot_type="invariant_contribution")

    assert not warnings
    axis = figure.axes[0]
    assert axis.get_xlabel().startswith("ln q")
    assert axis.get_ylabel().startswith("q^3 I(q)")
    assert list(axis.lines[0].get_ydata()) == [1.0, 16.0, 192.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_plotting.py::test_q3_invariant_contribution_plot_uses_log_q_axis -v
```

Expected: FAIL because the plot type is unsupported.

- [ ] **Step 3: Implement plot type and GUI combo entries**

Add `invariant_contribution` to `create_curve_figure()`, filtering `q <= 0` before `np.log(q)`. Add the plot type to `PlottingTab`. Add `information_budget` to `AnalysisTab` and import it. Add it to `run_deep_analysis()` so deep analysis records the information-budget summary alongside existing invariant and Porod outputs.

- [ ] **Step 4: Re-run focused plotting test**

Run:

```powershell
python -m pytest tests/test_plotting.py::test_q3_invariant_contribution_plot_uses_log_q_axis -v
```

Expected: PASS.

### Task 3: Records And Verification

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/developer_notes.md`

- [ ] **Step 1: Add user-facing changelog entry**

Record the date, reason, root cause/opportunity, touched files, fix summary, tests run, and follow-up risk.

- [ ] **Step 2: Add developer note**

Document the information-budget analysis, q^3I/log-q interpretation, quantile/fraction outputs, and the finite-range caveat.

- [ ] **Step 3: Run focused and broad verification**

Run:

```powershell
python -m pytest tests/test_invariant.py tests/test_plotting.py tests/test_invariant_analysis.py -v
python -m py_compile main.py app\core\*.py app\ui\*.py
python -m pytest
```

Expected: all tests and syntax checks pass.
