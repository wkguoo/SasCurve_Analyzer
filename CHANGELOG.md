# CHANGELOG

## 2026-07-07 - Uncommitted review bug fixes before main merge

### Task Objective

Review the large uncommitted worktree, fix confirmed bugs, exclude generated agent artifacts from publication, and prepare the branch for merge to `main`.

### Symptom Or Reason

- Refreshing the main curve list without an explicit target row reset the current selection to the first curve.
- Finite invariant calculations integrated q values in input order, so reversed q arrays returned negative `Q_measured` for positive data.
- Deep scan candidate windowing used the input q order and could build `q_min > q_max` windows for reversed q arrays.
- Peak detection used input q order for FWHM and area, producing negative widths and peak areas on reversed q arrays.
- Correlation-function default `r_max` used raw `np.diff(q)`, so reversed q input fell back to `200.0` instead of deriving the same real-space range as sorted q.
- `.ai-bridge/` contained generated execution logs and intermediate patches that should not be committed.

### Root Cause

Several analysis paths assumed imported q arrays were already strictly increasing, while import and project models preserve input order non-destructively. The GUI selection bug came from reading `currentRow()` after clearing the list. The generated `.ai-bridge/` directory was not ignored.

### Touched Files

- `.gitignore`
- `app/core/correlation.py`
- `app/core/deep_scan.py`
- `app/core/feature_extraction.py`
- `app/core/invariant_analysis.py`
- `app/core/model_free.py`
- `app/ui/main_window.py`
- `tests/test_correlation.py`
- `tests/test_deep_scan.py`
- `tests/test_invariant.py`
- `tests/test_invariant_analysis.py`
- `tests/test_peak_analysis.py`
- `tests/test_ui_style.py`
- `docs/developer_notes.md`

### Fix Summary

- Preserve the selected curve row before rebuilding the main curve list.
- Sort local q/intensity arrays before invariant integration, deep-scan candidate windowing, peak width/area calculation, and correlation-function default `r_max` derivation.
- Added regression tests for reversed-q invariant, deep scan, peak detection, correlation-function, and curve-list refresh behavior.
- Added `.ai-bridge/` to `.gitignore` so generated execution artifacts stay local.

### Tests Run

Focused red/green tests were run for each confirmed bug:

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_ui_style.py::test_refresh_curve_list_preserves_current_selection_by_default
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_invariant.py::test_finite_q_invariant_sorts_q_before_integrating tests\test_invariant_analysis.py::test_invariant_with_extrapolation_sorts_q_before_integrating
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deep_scan.py::test_deep_scan_sorts_q_before_candidate_windowing
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_peak_analysis.py::test_peak_detection_sorts_q_before_width_and_area
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_correlation.py::test_correlation_function_sorts_q_before_default_rmax
```

Each focused test was first observed failing before the fix and passing after the fix.

Final full verification after the review fixes:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `93 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

Sorting is local to analysis calculations and does not mutate `CurveData`. Future analysis functions that use q-neighbor relationships should either reuse a shared sorted-data helper or add their own reversed-q regression tests.

## 2026-07-07 00:32:42 +08:00 - Information-budget scale contribution analysis

### Task Objective

Implement the first practical slice of the SAS upgrade roadmap: show where finite-range invariant signal is concentrated across scattering scale, without adding high-risk model fitting.

### Added Files

- `docs/superpowers/plans/2026-07-07-information-budget.md`

### Modified Files

- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/deep_analysis.py`
- `app/ui/analysis_tab.py`
- `app/ui/plotting_tab.py`
- `tests/test_invariant.py`
- `tests/test_plotting.py`
- `docs/developer_notes.md`
- `docs/method_notes.md`

### Symptom Or Reason

Finite `Q_measured = integral(q^2 I(q) dq)` and q²I plots did not directly show which log-q scale ranges dominate the invariant contribution. Reversed q ordering could also make finite invariant integration negative even when the physical curve was positive.

### Root Cause

The existing invariant metric integrated q values in input order and only exposed the linear-q integrand. It did not compute q³I for log-q contribution density, cumulative contribution, quantile positions, entropy, or low/mid/high contribution fractions.

### Fix Summary

- Added `information_budget()` in `app/core/model_free.py` with q³I contribution spectrum, cumulative Q, Q10/Q50/Q90 q locations, `d_Q50`, dominant q/d scale, normalized entropy, low/mid/high contribution fractions, and observable d range.
- Added an `invariant_contribution` plot type using `ln q` versus `q^3 I(q)`.
- Exposed `information_budget` in the analysis tab and `invariant_contribution` in the plotting tab.
- Included information-budget output in deep analysis.
- Sorted q/intensity pairs before finite invariant integration so reversed input order does not flip the sign of `Q_measured`.

### Tests

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_invariant.py tests\test_invariant_analysis.py tests\test_plotting.py tests\test_export_deep_analysis.py -v
$files = @('main.py') + (Get-ChildItem -LiteralPath 'app\core' -Filter '*.py').FullName + (Get-ChildItem -LiteralPath 'app\ui' -Filter '*.py').FullName
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile @files
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
```

Verified related result: `14 passed`.
Verified full-suite result with explicit PowerShell file expansion for `py_compile`: `93 passed`.

### Risks And Follow-Up

- Low/mid/high fractions are descriptive and default to log-q tertiles unless explicit band boundaries are supplied.
- Quantiles and entropy use positive interval contributions; strongly background-subtracted data with negative regions should be inspected before interpretation.
- This change does not yet implement window-stability maps, local curvature/crossover candidates, batch heatmaps, or structure-property linking from the roadmap.

## 2026-07-07 00:08:13 +08:00 - GUI polish, action hierarchy, and hover help

### Task Objective

Upgrade the PySide6 GUI so the application feels more polished, key actions are visually prioritized, and hover guidance is useful without covering important controls.

### Added Files

- `app/ui/style.py`
- `tests/test_ui_style.py`
- `docs/superpowers/plans/2026-07-06-gui-polish.md`

### Modified Files

- `main.py`
- `app/ui/main_window.py`
- `app/ui/import_tab.py`
- `app/ui/check_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/records_tab.py`
- `app/ui/export_tab.py`
- `app/ui/templates_tab.py`
- `app/ui/advanced_tab.py`
- `app/ui/settings_dialog.py`
- `docs/developer_notes.md`

### Symptom Or Reason

The GUI used mostly default Qt styling and flat button treatment, so important operations such as importing, plotting, analysis, exporting, saving projects, and removing formal records were not visually distinguished. Controls also lacked consistent hover guidance.

### Root Cause

UI styling and help text were scattered or absent. Buttons were created directly in each tab without a shared action-importance convention, and no global stylesheet or tooltip/status-tip policy existed.

### Fix Summary

- Added a shared `app/ui/style.py` helper for the global theme, tooltip/status-tip behavior, and action-button roles.
- Applied a restrained scientific desktop theme using Qt stylesheets, with clearer tabs, inputs, list widgets, status bar, and tooltips.
- Replaced direct `QPushButton` creation in UI tabs with role-aware `action_button()` calls.
- Added concise tooltips plus more detailed status-bar/What's This text so hover help stays short and less obstructive.
- Marked high-impact operations with `primary`, `success`, `warning`, or `danger` roles.
- Added tab-level and curve-list help in the main window.
- Preserved existing analysis, import, export, record, and project logic.

### Tests

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_ui_style.py -v
python -m py_compile main.py app\core\*.py app\ui\*.py
python -m pytest
```

Verified with the Codex bundled Python environment. Final result: `85 passed`.

The direct wildcard `py_compile` form is not expanded by this PowerShell session, so the actual syntax check expanded file paths with `Get-ChildItem`.

Additional offscreen GUI smoke check instantiated `MainWindow` after `apply_app_theme(app)`: 29 buttons found, roles present were `danger`, `primary`, `secondary`, `success`, and `warning`, and no role-managed button was missing tooltip text. A 1240 x 780 offscreen screenshot was generated at `.tmp/gui_smoke.png`; the offscreen Qt font database was empty, so font rendering in that screenshot is not a reliable proxy for normal Windows desktop rendering. The theme now sets `Microsoft YaHei UI`, `Microsoft YaHei`, `Segoe UI`, and `Arial` fallback families for real GUI sessions.

### Risks And Follow-Up

- Full visual confirmation still requires launching the desktop GUI manually because the change targets a PySide6 desktop interface.
- Tooltips are intentionally short; detailed guidance is routed to status tips and What's This text to reduce obstruction.
- The current worktree contained substantial pre-existing uncommitted changes, so this update avoided commits and did not revert unrelated files.

## 2026-07-06 23:30:00 +08:00 - Stability, traceability, batch import, and release README update

### Task Objective

Improve `sas_curve_analyzer` stability, GUI usability, traceability, method-warning integration, project storage consistency, settings behavior, public-facing documentation, and in situ series batch import.

### Added Files

- `app/core/batch_import.py`
- `app/core/settings.py`
- `tests/test_batch_import.py`
- `tests/test_project.py`
- `tests/test_settings.py`

### Modified Files

- `README.md`
- `.gitignore`
- `docs/method_notes.md`
- `docs/advanced_methods.md`
- `docs/developer_notes.md`
- `app/core/data_model.py`
- `app/core/export.py`
- `app/core/feature_extraction.py`
- `app/core/io.py`
- `app/core/method_warnings.py`
- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/project.py`
- `app/core/report.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/export_tab.py`
- `app/ui/import_tab.py`
- `app/ui/main_window.py`
- `app/ui/plotting_tab.py`
- `app/ui/records_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_io.py`
- `tests/test_method_warnings.py`
- `tests/test_plotting.py`

### Specific Changes

- Added safe Guinier plotting filters for `I(q) <= 0` and `q <= 0`.
- Treated blank GUI/core error-column input as missing error data.
- Changed internal project curve data files from `.csv` to `.json` while preserving load compatibility through stored `data_file` paths.
- Added `AnalysisResult.structured_warnings` and bridge helpers for `MethodWarning`.
- Added settings load/save logic and applied settings to GUI defaults.
- Added natural-sorted in situ batch import with column/unit inference, frame metadata, group creation, partial-failure handling, and history records.
- Improved batch GUI selection for grouping, averaging, and A/B comparison.
- Added project-level history records for import, q conversion, analysis, group creation, comparison, export, project save, and formal-record actions.
- Added `.tmp/` to `.gitignore` for sandbox-local pytest temporary files.
- Extended formal records beyond current curves to analysis and comparison results, with unmark support.
- Rewrote README as public software documentation without internal development-stage language.

### Tests

```powershell
python -m pytest
```

Verified result in the Codex bundled Python environment with project-local temp directory: `70 passed`.

### Risks

- GUI behavior was integrated through code paths and core tests; full interactive GUI testing remains manual.
- P(r), correlation-function, and extrapolation interfaces remain experimental or reserved and should not be used for formal conclusions.
- Batch import currently infers common column names and units; unusual naming schemes may require manual extension.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 2026-07-06 22:20:50 +08:00 - Initial four-phase implementation and GitHub publication

### Task Objective

Publish `sas_curve_analyzer` to `https://github.com/wkguoo/SasCurve_Analyzer.git` after completing the four-phase development plan.

### Added Files

- Full phase-four `sas_curve_analyzer` application source tree.
- `app/core/` data, analysis, batch, export, pipeline, warning, plugin, and advanced interface modules.
- `app/ui/` PySide6 GUI modules.
- `tests/` pytest suite.
- `docs/` method and developer documentation.
- `examples/example_absolute_sas_curve.csv`.
- `.gitignore`.
- `README.md`.
- `requirements.txt`.
- `main.py`.

### Modified Files

- None for this standalone publication entry.

### Deleted Files

- None.

### Specific Changes

- Implemented four planned phases: import/check/plotting, model-free analysis, batch records/export, and advanced extensibility.
- Added non-destructive data handling and warning-rich analysis outputs.
- Added publication ignore rules for caches, virtual environments, build outputs, and generated result folders.

### Reason

The application is ready to be versioned as a standalone GitHub project.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No research output files are generated by this changelog entry.

### How To Check Success

```powershell
python -m pytest
```

Expected verified result before publication: all tests pass.

### Notes And Risks

- `compute_pr` is an experimental placeholder, not a validated P(r) algorithm.
- Correlation function analysis is a reserved interface.
- No packaging is performed during publication.
