# CHANGELOG

## 2026-07-07 - Windows double-click launcher bat

### Task Objective

Create double-clickable Windows bat launchers both inside the project and on the desktop so the SAS curve GUI can be started without typing commands.

### Symptom Or Reason

The project documented `python main.py`, but there was no double-click entry point for normal Windows desktop use.

### Root Cause

No Windows launcher script existed. A desktop copy also needs an explicit project path because its working directory is the desktop rather than the project root.

### Touched Files

- `Start_SasCurve_Analyzer.bat`
- `E:\desktop\Start_SasCurve_Analyzer.bat`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Fix Summary

- Added `Start_SasCurve_Analyzer.bat` in the project root.
- Made the script work from the project root or as a copied desktop launcher by resolving `E:\Desktop\SasCurve_Analyzer` when needed.
- Added Python discovery through `py -3` or `python`.
- Added clear pause-on-error messages for missing project files, missing Python, missing PySide6, and GUI startup failures.

### Tests Run

```powershell
cmd /c Start_SasCurve_Analyzer.bat --check
cmd /c E:\desktop\Start_SasCurve_Analyzer.bat --check
python -m py_compile main.py
```

Verified result: project-root launcher check passed; desktop launcher check passed; `main.py` syntax check passed.

### Follow-Up Risk

The launcher assumes this project remains at `E:\Desktop\SasCurve_Analyzer` when run from the desktop copy. If the project folder is moved, update `APP_DIR` in the desktop bat file or copy a fresh bat from the new project root.

## 2026-07-07 - Multi-agent audit fixes for UI, exports, and SAS parameter correctness

### Task Objective

Use parallel code audits to find UI layout/help issues, parameter export omissions, and calculation correctness risks, then merge the fixes into the main line with verification.

### Symptom Or Reason

The audit found several ways a researcher could be misled or get incorrect derived values: internal snake_case keys were shown as UI labels, deep-analysis-only controls were mixed with ordinary analysis controls, experimental advanced actions could write analysis results, several q-dependent calculations assumed imported q arrays were already sorted, nonuniform q peak FWHM used an average dq approximation, summary exports lacked curve units and run parameters, and Porod/invariant candidates could be emitted when required assumptions were not met.

### Root Cause

The application preserves imported data order non-destructively, but some analysis/export paths used raw q order for interpolation, gradients, plotting, matrix export, and inverse transforms. Export flatteners also treated scalar values as self-explanatory and did not join back to curve unit context. UI widgets reused core enum keys as display text and did not separate standard and deep-analysis workflows strongly enough.

### Touched Files

- `app/core/array_utils.py`
- `app/core/batch.py`
- `app/core/comparison.py`
- `app/core/export.py`
- `app/core/feature_extraction.py`
- `app/core/invariant_analysis.py`
- `app/core/method_warnings.py`
- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/porod_analysis.py`
- `app/core/pr_analysis.py`
- `app/core/report.py`
- `app/core/shape_models.py`
- `app/ui/advanced_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/export_tab.py`
- `app/ui/import_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/records_tab.py`
- `tests/`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Fix Summary

- Added `sort_arrays_by_q()` and used sorted local q/intensity copies for comparison interpolation, replicate averaging, plotting, local slope, Origin matrix export, normalization integrals, and P(r) inversion.
- Corrected peak FWHM on nonuniform q grids by interpolating SciPy fractional width positions onto q values.
- Added curve name, q unit, intensity unit, length unit, invariant unit, and `parameters_json` to analysis summaries and feature tables.
- Added `fit_parameters.csv` to complete analysis bundles and included fitted parameter values, uncertainty, confidence bounds, and units in reports.
- Added `bundle_warnings.txt` when complete bundle matrix export is skipped because q grids differ, and surfaced those warnings in export history/UI output.
- Gated invariant volume-fraction candidates behind absolute intensity, valid contrast, enough points, and physical Q; gated Porod surface candidates behind positive stable q4I plateau, Porod-like alpha, absolute intensity, and contrast.
- Replaced the mass-fractal cutoff form with a finite low-q empirical form that approaches the requested high-q fractal slope.
- Replaced internal combo-box keys with researcher-facing labels while keeping core keys in `userData`.
- Moved deep-analysis controls into a titled group, disabled experimental P(r)/correlation advanced buttons by default, improved Origin export hover help, and shortened the visible import path label to the filename while retaining the full path in help text.

### Tests Run

Focused red/green verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_comparison.py tests\test_batch.py tests\test_local_slope.py tests\test_plotting.py tests\test_peak_analysis.py tests\test_export.py tests\test_export_deep_analysis.py tests\test_invariant_analysis.py tests\test_porod_analysis.py tests\test_shape_models.py tests\test_ui_style.py -q
```

Verified result: first observed `15 failed, 34 passed`, then `51 passed`.

Additional focused verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_comparison.py tests\test_pr_analysis.py tests\test_invariant.py tests\test_correlation.py tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py -q
```

Verified result: `36 passed`.

Full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `116 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The UI was verified by offscreen widget tests rather than manual visual inspection in a live Windows session. Future q-neighbor calculations should use `sort_arrays_by_q()` or add explicit reversed-q/nonuniform-q regression tests before release.

## 2026-07-07 08:26:19 +08:00 - Origin long-table beginner guide export

### Task Objective

Export a detailed Markdown companion guide whenever the Origin long-table data export is written, so new users can understand each long-table parameter, plot the data correctly, and avoid overinterpreting SAS descriptors.

### Symptom Or Reason

`curves_long.csv` exposed raw q-I points and frame metadata, but the exported data folder did not include a self-contained explanation of what each column means or how a beginner should use the columns for plotting and analysis.

### Root Cause

`export_origin_long_csv()` only wrote the CSV table. The guide material existed only implicitly in developer knowledge and UI wording, so users receiving an exported folder could miss q/I/error/unit caveats, Origin plotting setup, and basic interpretation boundaries.

### Touched Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_export_deep_analysis.py`
- `docs/developer_notes.md`
- `README.md`
- `CHANGELOG.md`

### Fix Summary

- Added `curves_long_guide.md` generation next to every Origin long-table CSV export.
- Added a column-by-column Markdown guide covering `series_id`, `frame_index`, `sequence_order`, curve identity, source file stem, `q`, `I`, `error`, and units.
- Included beginner plotting recipes for log-log curves, Guinier checks, peak spacing, heatmaps, and error bars.
- Added analysis caveats for units, positive values, q range, missing errors, calibration, background handling, and model-dependent interpretation.
- Exposed `curves_long_guide` in complete analysis bundle outputs and added the guide path to the single long-table export UI message/history parameters.

### Tests Run

Focused red/green verification:

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py::test_origin_long_export_writes_beginner_guide_markdown tests\test_export_deep_analysis.py::test_export_analysis_bundle_writes_all_expected_files -q
```

Verified focused result: first observed `2 failed`, then `2 passed`.

Export/UI regression verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py::test_export_tab_exposes_origin_export_buttons -q
```

Verified result: `10 passed`.

Final full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `98 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The guide is static explanatory text. If future long-table columns are added, update `ORIGIN_LONG_COLUMN_GUIDE`, tests, README, and developer notes in the same change so the guide stays synchronized with the CSV schema.

## 2026-07-07 01:14:03 +08:00 - Origin-ready batch curve exports

### Task Objective

Make batch in situ curve exports directly usable in Origin by adding point-level long-table CSV output and q-grid-checked matrix CSV output.

### Symptom Or Reason

Batch import preserved in situ frame metadata, but export workflows only produced single-curve CSV files, feature summaries, and analysis tables. Origin users still needed manual reshaping before grouped curve plots, heatmaps, or contour plots.

### Root Cause

`app/core/export.py` did not expose project-level curve point tables. `feature_table.csv` is one row per curve, not one row per q-I point, and the analysis bundle did not include raw/imported curve data in an Origin-friendly long or matrix layout.

### Touched Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_export_deep_analysis.py`
- `tests/test_ui_style.py`
- `docs/developer_notes.md`
- `README.md`

### Fix Summary

- Added `curves_long.csv` export with one row per point and fixed columns for `series_id`, `frame_index`, `sequence_order`, curve identity, source stem, q, I, error, and units.
- Added `curves_matrix.csv` export with q as the first column and one intensity column per frame/curve when all q grids match.
- Matrix export now skips mismatched q grids with an explicit warning instead of silently interpolating or misaligning data.
- Added `curves_long` and compatible `curves_matrix` outputs to the complete analysis bundle.
- Added GUI buttons for `导出 Origin 长表` and `导出 Origin 矩阵表`.

### Tests Run

Focused red/green verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py::test_export_tab_exposes_origin_export_buttons -q
```

Verified focused result: `9 passed`.

Final full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `97 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The first matrix export intentionally requires matching q grids and does not interpolate. If Origin heatmap workflows need automatic interpolation later, add it as an explicit option with a history warning and tests that verify original curve data remain unchanged.

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

## 2026-07-07 11:53:52 +08:00 - Plotting controls, calibrated negative intensities, settings transparency, and SAS math labels

### Task Objective

Implement the `.ai-bridge/current-plan.md` usability and method-transparency plan for calibrated SAS curve plotting and validation.

### Added Files

- `app/core/model_catalog.py`
- `tests/test_model_catalog.py`

### Modified Files

- `app/core/advanced_transforms.py`
- `app/core/deep_scan.py`
- `app/core/export.py`
- `app/core/method_warnings.py`
- `app/core/plotting.py`
- `app/core/porod_analysis.py`
- `app/core/settings.py`
- `app/core/validation.py`
- `app/ui/advanced_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `app/ui/plotting_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_export.py`
- `tests/test_model_catalog.py`
- `tests/test_plotting.py`
- `tests/test_settings.py`
- `tests/test_ui_style.py`
- `tests/test_validation.py`
- `README.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added calibrated negative-intensity classification: slight negative values are reported separately from significant negative values and preserved for non-log displays.
- Added validation summary fields for negative intensity count/fraction, positive dynamic range, and log-valid/log-invalid point counts.
- Added plotting helpers for display-coordinate transforms and cursor readout formatting.
- Added peak/d-spacing plotting, optional `d = 2π/q` secondary axis, and standard Unicode math labels for q²/q³/q⁴/α.
- Added plotting tab controls for manual axis limits, full/low/mid/high q quick ranges, cursor coordinate readout, d-axis display, and q*/d annotation.
- Added settings load metadata and a read-only settings transparency panel with active values, settings path/load status, and model/formula assumptions.
- Added a model catalog covering common SAS plotting views, assumptions, limitations, and interpretation status.
- Updated docs and user-facing warning/export text to avoid developer-style ASCII caret/pi notation where the text is meant for users.

### Reason

Absolute-calibrated/background-corrected SAS data can contain slight negative values, and users need clearer plotting controls, coordinate readouts, settings visibility, and professional math notation for research workflows.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data or research output files were generated.
- `.ai-bridge/agent-status.md` and `.ai-bridge/implementation-diff.patch` are updated separately as CodexPro handoff records.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest
python -m compileall -q main.py app\core app\ui
```

Verified during implementation:

- Focused tests: `35 passed`.
- Full test suite: `127 passed`.
- Compile check: passed.

### Notes And Risks

- Axis range controls only change the displayed matplotlib axes; they do not modify imported curves or analysis ranges.
- The `d = 2π/q` axis and peak-derived `d = 2π/q*` values are characteristic scales or correlation distances, not automatic particle diameters.
- Logarithmic plots and log-based analyses still exclude `I(q) <= 0`.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 16:50:27 +08:00 - Add Beginner Chinese User Manual

### Task Objective

Implement the current-plan supplementary documentation deliverable by adding a detailed Chinese user manual for beginner graduate students.

### Added Files

- `docs/user_manual_zh.md`

### Modified Files

- `README.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added a self-contained Chinese user manual covering software scope, quick start, installation, data preparation, each GUI tab, plotting, q/display-x conversion, model-free analysis, batch comparison, project/output pages, templates, settings, advanced interfaces, workflow examples, FAQ, checklist, terminology, method boundaries, and appendices.
- Added README links to the Chinese manual in both English and Simplified Chinese sections.
- Updated developer notes to require keeping `docs/user_manual_zh.md` synchronized with UI labels, q-range behavior, outputs, settings, and method limitations.

### Reason

The current plan required a beginner-facing Chinese manual that lets a new materials research student follow the software workflow without reading source code or relying only on the concise README.

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Test-Path docs\user_manual_zh.md
Select-String -Path README.md -Encoding UTF8 -Pattern "docs/user_manual_zh.md","使用手册","User Manual"
Select-String -Path docs\user_manual_zh.md -Encoding UTF8 -Pattern "SAS Curve Analyzer 使用手册","q 范围与坐标变换","无模型分析详解","常见问题与排错","术语表"
```

### Notes And Risks

- This is a documentation-only change.
- The manual describes current implemented UI behavior. Future Supplement Plan features such as import preview, sequence table, figure export presets, reproducible export manifest, and layered errors are not described as completed features.
- No source code, raw experimental data, tests, packaging, Git commit, or Git push were changed or run for this entry.

## 2026-07-07 17:00:08 +08:00 - Add Project Lifecycle Menu And Dirty-State Tracking

### Task Objective

Implement the first broader reliability/reproducibility current-plan item: project lifecycle management for new, open, save, save-as, and unsaved-change handling.

### Added Files

- None.

### Modified Files

- `app/core/project.py`
- `app/ui/main_window.py`
- `app/ui/export_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/records_tab.py`
- `tests/test_project.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added in-memory `ProjectState.revision` tracking for project mutations.
- Added `项目` menu with `新建项目`, `打开项目...`, `保存项目`, and `另存为项目...`.
- Added `MainWindow.current_project_folder`, saved revision tracking, project dirty detection, save/open/new helpers, and title-bar `*` marker for unsaved changes.
- Added visible-window close confirmation when project changes are unsaved.
- Routed export-page project saving through `MainWindow.save_project_to_folder()` so menu save and export-page save use the same lifecycle logic.
- Refreshed title dirty state after analysis, batch operations, formal-record changes, and export-history mutations.
- Added tests for revision tracking, save/open lifecycle, dirty-state behavior, and GUI restoration after opening a saved project.
- Updated README, Chinese manual, and developer notes for project lifecycle behavior.

### Reason

The project previously had project serialization functions and an export-page save button, but did not provide a complete user-facing lifecycle with open/save/save-as/new controls or unsaved-change protection.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use the `项目` menu for project lifecycle operations.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.
- Manual testing of save/open will generate a chosen project folder containing `project.json` and `curves/*.json`.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_project.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- `ProjectState.revision` is in-memory only and is not serialized to project files.
- Close confirmation is skipped for unshown/offscreen windows so automated tests do not block; visible user windows still prompt when dirty.
- Direct list mutations outside `ProjectState` add methods should call `MainWindow.mark_project_dirty()` or use an add method.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:05:30 +08:00 - Add Import Preview And Diagnostics

### Task Objective

Implement the second broader reliability/reproducibility current-plan item: import-before-preview and diagnostics for single-curve files.

### Added Files

- `app/core/import_preview.py`
- `tests/test_import_preview.py`

### Modified Files

- `app/ui/import_tab.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `ImportPreview` and `preview_curve_file()` to read selected files, infer or apply current q/I/error columns, and compute non-destructive diagnostics.
- Added `format_import_preview()` for plain-text GUI display.
- Added import-page `预览/诊断当前文件` button and automatic preview after file selection.
- Preview reports file status, columns, first rows, q/I ranges, NaN counts, duplicate q count, non-positive q/intensity counts, error-column invalid counts, and importability messages.
- Updated README, Chinese manual, and developer notes for the new preview workflow and non-mutating behavior.
- Added tests for normal CSV, missing required columns, NaN/duplicate/negative/error warnings, and empty/comment-only files.

### Reason

The project previously attempted column inference after selecting a file, but did not give beginner users a visible pre-import diagnosis explaining whether the current column mapping was usable and which downstream steps might be affected.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `数据导入` → `选择数据文件`; the preview runs automatically. Use `预览/诊断当前文件` after manually editing column names.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_import_preview.py tests/test_io.py tests/test_batch_import.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Preview/diagnostics are read-only. They do not sort, delete rows, clip negative intensities, add offsets, or modify original files.
- `Warning` means the file can still be imported, but later plotting or analysis may filter points or hide error bars.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:11:50 +08:00 - Add Analysis q-Range Preflight

### Task Objective

Implement the third broader reliability/reproducibility current-plan item: model-free analysis preflight checks for the selected raw q range.

### Added Files

- `app/core/analysis_preflight.py`
- `tests/test_analysis_preflight.py`

### Modified Files

- `app/ui/analysis_tab.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `AnalysisPreflight`, `check_analysis_preflight()`, and `format_analysis_preflight()`.
- Added analysis-page `检查当前 q 范围` button.
- Automatically runs preflight before standard `运行分析`.
- Stops analysis when preflight severity is `error`.
- Shows preflight summary with analysis results when severity is `ok` or `warning`.
- Checks selected curve availability, finite raw q range, non-negative raw q, `q_min < q_max`, points in range, finite points, positive q points, positive intensity points, log-usable points, excluded points, minimum method-specific point counts, and selected method caveats.
- Updated README, Chinese manual, method notes, developer notes, CHANGELOG, and tests.

### Reason

Users needed a clear pre-analysis explanation when selected q ranges were empty, reversed, too small, or invalid for log-based analysis, especially when display x ranges such as `ln q` can differ from raw physical q ranges.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `无模型分析` → `检查当前 q 范围` before `运行分析`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_analysis_preflight.py tests/test_ui_style.py tests/test_guinier.py tests/test_power_law.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Preflight is a minimum numerical/input check. It does not select the best scientific interval and does not prove method validity.
- `warning` severity still allows analysis to run; `error` severity blocks standard analysis until the q range or data issue is corrected.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:17:52 +08:00 - Add Reproducible Export Bundle Metadata

### Task Objective

Implement the fourth broader reliability/reproducibility current-plan item: strengthen complete analysis bundles with manifest, README, settings snapshot, and stable warnings metadata.

### Added Files

- None.

### Modified Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `manifest.json` to complete analysis bundles.
- Added `README_export.md` explaining bundle purpose, file roles, manual review requirements, warnings, and data safety.
- Added `settings_snapshot.json` with export-time application settings.
- Made `bundle_warnings.txt` a stable bundle output even when no bundle-level warnings exist.
- Manifest now records software metadata, project counts, input curve metadata and source hash when available, analyses, comparisons, settings snapshot link, warnings, and output file names.
- GUI bundle export now passes comparison results and current settings into the bundle exporter.
- Added regression coverage for manifest, README_export, settings snapshot, and warnings output.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

The complete analysis bundle previously exported useful tables and reports, but did not include enough metadata for a future reader to audit inputs, settings, outputs, skipped optional files, and warning state from a single package.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `项目与输出` → `导出报告` → `导出完整分析包`.

### Generated Output Files

When the user exports a bundle, the selected output folder now includes:

- `manifest.json`
- `README_export.md`
- `settings_snapshot.json`
- `bundle_warnings.txt`

No files were generated during this code change except temporary pytest outputs.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_export.py tests/test_export_deep_analysis.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The bundle structure remains mostly flat in this pass to avoid a broad export-directory migration.
- Source file hashes are recorded only when the original source path still exists locally.
- Exporting a bundle does not modify original experimental data or imported curve arrays.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:23:43 +08:00 - Add Batch Sequence Management Table

### Task Objective

Implement the fifth broader reliability/reproducibility current-plan item: a batch sequence management table for reviewing in situ/time-series curve order and metadata.

### Added Files

- None.

### Modified Files

- `app/core/batch.py`
- `app/ui/batch_tab.py`
- `tests/test_batch.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `build_sequence_index()` and `export_sequence_index_csv()`.
- Added `SEQUENCE_INDEX_COLUMNS`.
- Added read-only sequence management table to `批量比较`.
- Added buttons: `刷新序列表`, `按序列顺序选择全部`, `从选中行建组`, and `导出序列索引 CSV`.
- Table rows show sequence/project order, curve ID/name, source file/stem, series/frame metadata, units, point count, q range, and warnings.
- Warnings report q grid mismatch relative to the first curve, non-finite intensity, non-positive intensity, or no finite q.
- Added tests for metadata rows, no-metadata rows, q-grid warning, CSV export, and UI table/buttons.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

Batch import already preserved sequence metadata, but users needed a direct table for checking which files were imported, whether order/frame metadata looked correct, and which curves had q-range or warning issues.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `批量比较` → `刷新序列表` and optionally `导出序列索引 CSV`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- Using the new export button writes a user-selected `sequence_index.csv`.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_batch.py tests/test_batch_import.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The sequence table is read-only. It does not insert, smooth, delete, re-order, or reinterpret curve data.
- q grid mismatch warnings are audit hints; they do not automatically interpolate or modify curves.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:27:57 +08:00 - Add Figure Export Presets

### Task Objective

Implement the sixth broader reliability/reproducibility current-plan item: lightweight scientific figure export presets.

### Added Files

- `app/core/figure_export.py`
- `tests/test_figure_export.py`

### Modified Files

- `app/ui/plotting_tab.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `FIGURE_EXPORT_PRESETS` for screen preview, presentation, and draft-publication output.
- Added safe figure filename generation and preset-based Matplotlib figure export.
- Added plotting-page preset selector, format selector, and `Export current figure` button.
- Export uses current plot type, current curve, axis limits, error bars, d-axis setting, and selected preset.
- Figure exports write project history records with curve ID, plot type, preset, format, path, and x-axis limits.
- Added tests for preset completeness, safe filenames, file writing, UI controls, and no-current-curve failure message.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

Users needed stable, low-friction image outputs for screen preview, group meetings, and manuscript drafts without turning the application into a full figure-design tool.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `曲线绘图` → select preset/format → `Export current figure`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- Using the new button writes a user-selected `.png`, `.svg`, or `.pdf` figure.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_figure_export.py tests/test_plotting.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Presets are intended for stable defaults, not final journal layout or graphic design.
- Applying a preset adjusts the current Matplotlib figure styling before saving.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 15:26:02 +08:00 - Negative-intensity settings and model catalog completeness

### Task Objective

Complete the appended `.ai-bridge/current-plan.md` small-fix plan by moving slight negative-intensity thresholds into settings and expanding the model/formula catalog.

### Added Files

- `app/ui/model_catalog_dialog.py`

### Modified Files

- `app/core/model_catalog.py`
- `app/core/settings.py`
- `app/core/validation.py`
- `app/ui/check_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_model_catalog.py`
- `tests/test_settings.py`
- `tests/test_ui_style.py`
- `tests/test_validation.py`
- `README.md`
- `docs/method_notes.md`
- `docs/advanced_methods.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `allow_slight_negative_intensity`, `slight_negative_abs_ratio_threshold`, and `slight_negative_fraction_threshold` to `AppSettings`.
- Extended `validate_curve()` with keyword arguments for slight-negative classification thresholds and recorded those values in `ValidationReport.summary`.
- Updated `CheckTab` so GUI validation uses the current settings values.
- Added settings controls for slight negative-intensity tolerance.
- Added a standalone `ModelCatalogDialog` opened from Settings.
- Expanded `model_catalog.py` to include shape/form-factor models, empirical/model-dependent models, P(r), correlation, and low-q/high-q extrapolation interfaces.
- Updated tests and documentation for the new settings and catalog behavior.

### Reason

The previous implementation hard-coded slight-negative thresholds and the catalog did not cover the project’s model-dependent, experimental, and reserved analysis interfaces.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data or research output files were generated.
- `.ai-bridge/agent-status.md`, `.ai-bridge/implementation-diff.patch`, and `.ai-bridge/execution-log.jsonl` are updated separately as handoff records.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_settings.py tests/test_validation.py tests/test_model_catalog.py tests/test_ui_style.py -q
python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Wider slight-negative thresholds can hide data-quality problems. The settings only change validation classification; they do not modify intensities and do not allow non-positive values into log analysis.
- Model catalog entries are transparency notes, not proof that a model applies.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 15:42:23 +08:00 - Add MIT License

### Task Objective

Add a standard MIT License to the standalone SAS Curve Analyzer project and update README license labeling.

### Added Files

- `LICENSE`

### Modified Files

- `README.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added standard MIT License text.
- Set copyright line to `Copyright (c) 2026 wkguoo`.
- Updated README license line to `License: MIT License. See LICENSE.`

### Reason

The project previously had no license file and README still showed `License: to be added.`

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Test-Path LICENSE
Select-String -Path LICENSE -Pattern "MIT License","Copyright \(c\) 2026 wkguoo","THE SOFTWARE IS PROVIDED"
Select-String -Path README.md -Pattern "MIT License","LICENSE"
```

### Notes And Risks

- This is a documentation/license-only change.
- No source code, raw experimental data, tests, packaging, Git commit, or Git push were changed or run for this entry.

## 2026-07-07 15:46:04 +08:00 - Add README Language Navigation And Badges

### Task Objective

Add simple English/Simplified Chinese navigation and lightweight README badges, including the MIT License badge.

### Added Files

- None.

### Modified Files

- `README.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added top README language navigation: `[English](#english) | [简体中文](#简体中文)`.
- Added static shields.io badges for `status active`, `python 3.x`, `platform Windows`, and `license MIT`.
- Added `## English` heading so the existing English README content has a stable anchor.
- Added a concise `## 简体中文` section with project purpose, main features, quick start, and usage cautions.

### Reason

The README top area needed to match the requested bilingual navigation and simple badge style, and the existing MIT License status needed to be visible in the badge row.

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Select-String -Path README.md -Pattern "\[English\]\(#english\)","\[简体中文\]\(#简体中文\)","status-active","python-3.x","platform-Windows","license-MIT","## English","## 简体中文"
Select-String -Path LICENSE -Pattern "MIT License"
git diff -- README.md CHANGELOG.md LICENSE
```

### Notes And Risks

- This is a README/CHANGELOG-only documentation update.
- Existing source code, raw experimental data, tests, packaging, Git commit, and Git push were not changed or run for this entry.

## 2026-07-07 16:39:20 +08:00 - Link Plotting And Model-Free Analysis Workflow

### Task Objective

Implement the current-plan workflow improvements for plotting coordinates, plot/analysis navigation, transformed x-range conversion, and top-level tab hierarchy.

### Added Files

- `app/core/method_mapping.py`
- `tests/test_method_mapping.py`

### Modified Files

- `app/core/plotting.py`
- `app/ui/plotting_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `tests/test_plotting.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Moved plotting cursor/current coordinate readout into a dedicated row separate from axis range controls.
- Added centralized `PLOT_TO_ANALYSIS` and `ANALYSIS_TO_PLOT` mappings.
- Added plotting-page action to send linked views to model-free analysis.
- Added analysis-page action to show the linked plot view.
- Added `display_x_range_to_q_range()` so transformed display x ranges such as `ln q` and Guinier `q²` can be converted back to raw q.
- Added analysis-page action to read current plotting x-limits and fill positive raw `q_min/q_max`.
- Grouped `历史与正式记录`, `导出报告`, and `分析模板` under the new `项目与输出` nested tab while preserving existing tab object attributes.
- Updated tests and documentation for linked workflow, transformed range semantics, and nested tabs.

### Reason

The previous GUI made long coordinate readouts compete with axis controls, required manual switching between related plot and analysis views, did not provide a clear path from transformed display x ranges back to physical q ranges, and kept lower-frequency project/output pages at the same top-level priority as the main workflow.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_plotting.py tests/test_method_mapping.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Raw analysis `q_min/q_max` still represent physical q and do not accept negative values.
- Negative values are accepted only as transformed display coordinates such as `ln q`; they are converted to positive raw q before analysis.
- This pass implements the first current-plan GUI workflow section. The supplementary beginner manual and broader reliability/reproducibility enhancement plan remain follow-up work unless implemented in a later pass.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 21:26:07 +08:00 - Review-Fix Import Preview, Plot Range Conversion, And Project Save Prompts

### Task Objective

Execute `.ai-bridge/current-plan.md` targeted review fixes before commit/push, without adding new SAS algorithms or modifying raw experimental data.

### Added Files

- None.

### Modified Files

- `app/core/import_preview.py`
- `app/core/plotting.py`
- `app/ui/import_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `app/ui/export_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/plotting_tab.py`
- `tests/test_import_preview.py`
- `tests/test_plotting.py`
- `tests/test_project.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `docs/method_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added explicit `q_unit` and `intensity_unit` parameters to import preview, with priority for UI-provided units, fallback to inferred units, then documented safe defaults.
- Passed current import-page unit fields into preview diagnostics.
- Added `display_x_limits_to_q_range_for_curve()` to clamp Matplotlib display x-limits to the selected curve's valid display range before converting back to positive raw q.
- Updated analysis-page plot-range conversion to preserve q inputs on failure and report original xlim, clipped display range, raw q range, plot type, and clipping status.
- Replaced dirty-project discard confirmation with a shared save / discard / cancel flow for new, open, and close operations.
- Renamed the export-page project save button to `项目另存为...` and documented it as an auxiliary project-save entry.
- Made sequence-index CSV export default to `settings.default_export_dir`.
- Refreshed the plotting tab after preset figure export so export styling does not persist in the current screen plot.
- Updated docs to keep fact-only message wording aligned with code and tests, and documented `project_save` as audit history.

### Reason

The review plan identified submission-blocking risks: import preview units could contradict UI inputs, Matplotlib autopadding could break valid q-range conversion, unsaved project prompts could only discard/cancel, and documentation needed to match the fact-only message policy.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

### Generated Output Files

- `.ai-bridge/implementation-diff.patch` will be regenerated after verification.
- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_import_preview.py tests/test_plotting.py tests/test_project.py tests/test_user_messages.py tests/test_ui_style.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- `save_project()` and `save_project_as_dialog()` now return `True` or `False`; Qt action triggers ignore the return value.
- Display x clipping uses the current selected curve and positive raw q for final analysis ranges.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 20:28:35 +08:00 - Add Fact-Only Layered User Messages

### Task Objective

Implement the current-plan layered error-message foundation while honoring the latest user requirement that messages show objective facts only and do not include action-guidance wording.

### Added Files

- `app/core/user_messages.py`
- `tests/test_user_messages.py`

### Modified Files

- `app/core/analysis_preflight.py`
- `app/core/import_preview.py`
- `app/ui/import_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/export_tab.py`
- `app/ui/main_window.py`
- `app/ui/advanced_tab.py`
- `tests/test_analysis_preflight.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `UserMessage` and `format_user_message()` for fact-only layered messages.
- Replaced common import, analysis, figure export, export, and project lifecycle failure paths with layered messages containing severity, observed result, original-data safety, objective facts, and technical details.
- Removed preflight `next_actions` output and retained severity, counts, filtering facts, and method limitation messages.
- Removed action-guidance labels from structured warning displays in analysis and advanced tabs.
- Updated README, Chinese manual, developer notes, and tests for fact-only message behavior.

### Reason

The current plan required clearer user-facing error messages, and the latest user correction required those messages to avoid instruction-style action guidance and show objective facts instead.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_user_messages.py tests/test_analysis_preflight.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The messages keep technical exception details visible.
- Message formatting is intentionally plain text for QTextEdit/status display and testability.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.
