# Developer Notes

## Project Structure

```text
sas_curve_analyzer/
  main.py
  app/
    core/
    ui/
  tests/
  examples/
  docs/
```

`app/core` contains data models, import, validation, transforms, plotting, model-free analysis, batch import, comparison, records, export, report generation, settings, templates, pipeline support, plugins, and advanced reserved interfaces.

`app/ui` contains the PySide6 interface. GUI classes should call `app/core` and should not contain numerical algorithms.

`docs/user_manual_zh.md` is the beginner-facing Chinese user manual. Keep it synchronized when UI tab names, button labels, q-range behavior, analysis outputs, export behavior, settings, or method limitations change. README should stay concise and link to the manual rather than duplicating detailed instructions.

## UI Theme And Help Text

Shared GUI styling and hover-help behavior live in `app/ui/style.py`.

Use `action_button()` for new buttons instead of instantiating `QPushButton` directly. The button role communicates importance:

- `primary`: main workflow actions such as import, plot, run analysis, export report, or save project.
- `secondary`: helper actions such as choose file, refresh, load template, or unit conversion.
- `success`: create, add, apply, or batch operations that produce new useful project state.
- `warning`: experimental, method-sensitive, or interpretation-sensitive operations.
- `danger`: removing or destructive actions such as unmarking a formal record.
- `quiet`: low-emphasis utility actions.

Use `apply_help()` for important inputs, checkboxes, combo boxes, lists, and buttons. Keep `tooltip` short so it does not cover nearby controls. Put longer context, method caveats, or risk guidance in `status_tip`; the helper also mirrors that text into What's This help.

Apply the app-wide theme with `apply_app_theme(app)` after constructing `QApplication` and before showing `MainWindow`.

`apply_app_theme()` sets a restrained Qt Fusion theme and prefers `Microsoft YaHei UI`, `Microsoft YaHei`, `Segoe UI`, and `Arial` font families so Chinese UI text renders correctly in normal Windows desktop sessions. Offscreen Qt smoke tests may not expose a real font database, so use them for structure and widget-state checks rather than final typography judgment.

## Core Data Models

- `CurveData`: one imported or derived curve.
- `AnalysisResult`: analysis output, including text warnings and `structured_warnings`.
- `CurveGroup`: ordered group of curve IDs.
- `ComparisonResult`: result of comparing two curves.
- `HistoryRecord`: project-level operation log.
- `FormalRecord`: user-selected record for reporting.
- `AppSettings`: user preferences loaded at startup.

## Project File Format

Project folders contain a top-level `project.json` plus internal curve data files in `curves/`.

New project saves write curve arrays to `curves/<curve_id>.json`. Loading still reads the `data_file` path stored in `project.json`, so old project entries pointing to `.csv` files with JSON content remain readable.

User-facing curve export remains CSV and is separate from internal project storage.

`ProjectState.revision` is an in-memory dirty-state counter. It increments when project objects are added through `add_curve()`, `add_analysis_result()`, `add_group()`, `add_comparison_result()`, `add_history_record()`, or `add_formal_record()`. It is not serialized. `load_project()` resets the loaded project revision to `0`.

`MainWindow` owns project lifecycle state:

- `current_project_folder`: folder used by `保存项目`;
- `_saved_revision`: revision at the last successful save/open/new baseline;
- `is_project_dirty()`: compares current revision with `_saved_revision`;
- `save_project_to_folder()`: writes project data and marks the project clean;
- `open_project_folder()`: loads a folder containing `project.json` and refreshes GUI state.

Visible main-window close events prompt before discarding unsaved project changes. Offscreen/unshown windows close without a prompt so automated tests do not block. When adding new UI actions that mutate existing project lists directly, prefer using `ProjectState` add methods or call `MainWindow.mark_project_dirty()` after the mutation so the title marker stays current.

## Settings

Settings are handled by `app/core/settings.py`.

`load_settings()` returns defaults if the settings file is missing, invalid, or incomplete. `load_settings_with_info()` returns the same settings plus `SettingsLoadInfo`, including path, file existence, load source, default fallback state, and any parsing error. `save_settings()` writes JSON. `MainWindow` loads settings and load metadata on startup and applies defaults to import, plotting, and export flows.

The settings dialog should show the active settings, settings file path, load status, and a concise model/formula transparency summary from `app/core/model_catalog.py`. Saving through the dialog writes the default `sas_curve_analyzer_settings.json` path and applies the values to the open main window immediately.

Negative-intensity tolerance settings live in `AppSettings`:

- `allow_slight_negative_intensity`
- `slight_negative_abs_ratio_threshold`
- `slight_negative_fraction_threshold`

`app/core/validation.py::validate_curve()` accepts these values as keyword arguments so the numerical validator does not need to import the settings module. GUI callers such as `CheckTab` should pass values from `MainWindow.settings`.

Do not read arbitrary sensitive paths for settings. Keep the default settings file local and explicit.

## Windows Launch Script

`Start_SasCurve_Analyzer.bat` is the double-click launcher for normal Windows desktop use.

The script resolves the project folder in two ways:

- If the bat file is in the project root, it uses its own directory.
- If the bat file is copied to the Windows desktop, it falls back to the fixed project path `E:\Desktop\SasCurve_Analyzer`.

The launcher checks that Python is available, reports missing PySide6 dependencies with the install command, and then starts the GUI with `python main.py` or `py -3 main.py`. Keep the desktop copy synchronized with the project-root copy when the launcher changes.

## Batch In Situ Import

Batch import logic belongs in `app/core/batch_import.py`.

Responsibilities:

- Natural-sort selected files.
- Infer q, intensity, and optional error columns.
- Infer q and intensity units from common column names.
- Parse sequence metadata from file names such as `ti15_00001_abs2d_cm-1.csv`.
- Import successful files even if some files fail.
- Create ordered in situ curve groups and project-level history records.

The UI should only collect file selections and display summaries.

Sequence management table support lives in `app/core/batch.py` and `app/ui/batch_tab.py`.

- `build_sequence_index()` creates row dictionaries from current project curves and existing `CurveData.metadata`.
- `export_sequence_index_csv()` writes `sequence_index.csv`.
- The table is read-only and should not insert, smooth, delete, or re-order curve data in the project.
- Warnings are descriptive, for example q grid mismatch relative to the first curve or non-positive intensity.
- Keep table fields aligned with `SEQUENCE_INDEX_COLUMNS` and tests when adding new sequence metadata.

## Import Preview And Diagnostics

Single-file import preview logic lives in `app/core/import_preview.py`.

- `preview_curve_file()` reads the table without modifying the source file, applies inferred or user-provided q/I/error columns, and returns an `ImportPreview`.
- `format_import_preview()` owns the plain-text summary shown by `ImportTab`.
- Preview status is `ok`, `warning`, or `error`; warnings remain importable but should tell the user what downstream plotting or analysis may filter.
- Diagnostics include row/column counts, q/I ranges, NaN counts, duplicate q count, non-positive q/intensity counts, error-column invalid counts, and preview rows.

Do not make preview mutate data, sort q in place, remove bad rows, clip negative intensities, or add intensity offsets. If future UI adds column selectors or preview tables, keep the diagnosis in core so tests can cover malformed files without opening Qt.

## User-Facing Messages

Fact-only layered user messages live in `app/core/user_messages.py`.

- `UserMessage` stores title, severity, what happened, objective facts, original-data safety, and optional technical detail.
- `format_user_message()` owns the plain-text format used by common import, analysis, export, figure-export, and project lifecycle failures.
- Do not include action-guidance or speculative-cause sections in these messages. Keep them factual: observed state, counts, paths, selected method, selected q range, and exception detail.
- Keep technical details visible so developer debugging is still possible.
- State original-data safety explicitly when an operation fails or only affects display/export state.

## Analysis Preflight

Standard model-free analysis preflight lives in `app/core/analysis_preflight.py`.

- `check_analysis_preflight()` accepts a `CurveData`, analysis type, raw q range, and range source label.
- `AnalysisPreflight` stores counts for total points, points in range, finite points, positive q points, positive intensity points, log-usable points, excluded points, severity, and messages.
- `format_analysis_preflight()` owns the plain-text summary shown by `AnalysisTab`.
- `AnalysisTab.run_analysis()` should stop when `preflight.can_run` is false and should include the preflight summary when analysis continues.

Preflight should remain a minimum numerical/input check. Do not make it select the "best" Guinier, Porod, peak, or power-law range, and do not let it emit structural conclusions. Add tests for new analysis types when their minimum point count, log requirements, or data filters differ from existing model-free methods.

## Origin Batch Exports

Origin-friendly batch curve exports live in `app/core/export.py`.

- `export_origin_long_csv()` writes `curves_long.csv` with one row per q-I point and fixed columns for sequence metadata, curve identity, q, intensity, optional error, and units. It also writes a sibling beginner guide named `<csv-stem>_guide.md`.
- `origin_long_guide_path()` owns the guide filename convention. Keep UI output and tests aligned with it.
- `export_origin_matrix_csv()` writes `curves_matrix.csv` only when all curves share the same sorted q grid. It returns `(None, warnings)` and does not create a file when q grids differ.
- The export report page intentionally keeps only stable, high-frequency data exports: current-curve CSV, `feature_table.csv`, Origin long table, Origin matrix table, and current-curve first-hand transformed-data CSV.
- Summary exports should include curve name, q unit, intensity unit, length unit, and invariant unit so scalar results can be interpreted outside the GUI.

Do not silently interpolate during matrix export. If interpolation is added later, expose it as an explicit user option and record it in project history.

## Derived Data Tables

Row-preserving derived data lives in `app/core/derived_data.py`.

- `DerivedDataOptions` stores optional alpha, Rg, D, R, and reference-curve settings.
- `build_curve_derived_table()` is the authoritative source for transformed plotting and analysis columns. Invalid mathematical domains must produce `NaN` and `valid_*` flags, not dropped rows.
- `derived_column_units()` and `derived_column_formulas()` describe internal derived columns for plotting/analysis metadata.

CSV column names must stay stable ASCII (`q2`, `ln_q`, `log10_q`, `q4I`, `local_slope_dlnI_dlnq`). UI and docs may show `q²`, `q⁴I(q)`, and `ln I(q)`.

Plotting should use `PLOT_DERIVED_MAPPING` in `app/core/plotting.py` and derived-table columns rather than recomputing transformed arrays independently. Add tests whenever a plot type changes so displayed data and derived CSV columns remain identical.

First-hand transformed-data export lives in `app/core/export.py`:

- `build_first_hand_transform_table()` returns a single-curve wide table with user-visible headers: `q`, `I(q)`, `q虏`, `ln q`, `log10 q`, `ln I(q)`, `log10 I(q)`, `q虏I(q)`, `q鈦碔(q)`, `qI(q)`, `q鲁I(q)`, and `d = 2蟺/q`.
- `export_first_hand_transform_csv()` writes `<curve_name>_transformed_data.csv` with UTF-8 BOM so Excel can open symbol headers more reliably.
- This export does not ask for alpha, Rg, D, R, or reference curves; it does not fit, smooth, interpolate, add constants, or remove original q/I rows.
- Removed report-page wrappers such as `export_curve_derived_csv()`, `export_curves_derived_long_csv()`, `export_curves_derived_matrix_csv()`, and `export_analysis_bundle()` must not be reintroduced unless a future plan explicitly restores those workflows.

Missing optional alpha/Rg/D/R/reference values can still be warnings inside explicit internal derived-data calculations. They should not appear in the simplified export report page, because that page no longer exposes those optional inputs.

## q-Order And Candidate-Parameter Safety

Imported `CurveData` preserves input order. Any algorithm that uses neighbor relationships, interpolation, integration, gradients, inverse transforms, peak widths, or matrix layout must work on sorted local copies and must not mutate the original curve arrays.

Use `app/core/array_utils.py::sort_arrays_by_q()` for new q-neighbor paths. Add reversed-q and, where relevant, nonuniform-q tests for new analysis or export behavior.

Parameter candidates that require physical assumptions should be gated before emission:

- Invariant volume-fraction candidates require absolute intensity, valid nonzero contrast, enough q points, positive finite Q, and a physical contrast factor.
- Porod surface candidates require absolute intensity, valid nonzero contrast, positive stable q4I plateau, and a high-q power-law alpha near 4.
- If assumptions are missing, export descriptive metrics and warnings, but leave the physical candidate value as `None`.

Shape-fit parameter values live in nested `result.results["parameters"]`; keep `fit_parameters.csv`, `analysis_summary.csv`, `feature_table.csv`, and Markdown reports synchronized when parameter schema changes.

## UI Labels And Experimental Controls

Combo boxes that drive core logic should show researcher-facing labels and store the core key in `itemData()`. Callers should read `currentData()` rather than relying on visible text.

User-visible math labels should use standard symbols such as `q²`, `q³`, `q⁴`, `α(q)`, and `2π/q`. Internal plot keys, transform keys, JSON fields, and CSV column names should remain stable ASCII identifiers.

`PlottingTab` supports display-only X/Y axis limits, quick q-range buttons, d-axis display for raw-q plots, peak/d-spacing annotations, and cursor coordinate readout. Range controls must not mutate `CurveData`; transformed views use transformed display coordinates such as q² or ln q. Cursor formatting lives in `app/core/plotting.py` so it can be tested without a full interactive mouse event.

The plot coordinate readout should stay in its own row, separate from axis range controls, so long transformed-coordinate messages do not compress X/Y inputs or q-range shortcut buttons.

Plotting/analysis navigation is centralized in `app/core/method_mapping.py`. Update `PLOT_TO_ANALYSIS`, `ANALYSIS_TO_PLOT`, UI combo-box items, the model catalog, and tests together when adding or renaming a plot type or model-free analysis type. The UI should call `MainWindow.set_plot_type()`, `MainWindow.set_analysis_type()`, `show_plotting_tab()`, and `show_analysis_tab()` rather than duplicating tab indices.

Display x-range to raw q-range conversion lives in `app/core/plotting.py::display_x_range_to_q_range()`. Use `display_x_limits_to_q_range_for_curve()` when converting Matplotlib axis limits, because automatic axis padding can extend raw-q or Guinier q² views outside the valid data range. Keep raw analysis q ranges positive; negative values are valid only for transformed display axes such as `ln q`.

Top-level tabs should prioritize the main workflow. Lower-frequency project output pages are grouped under `MainWindow.output_tabs` inside the `项目与输出` top-level tab while preserving `self.records_tab`, `self.export_tab`, and `self.templates_tab` attributes for existing callers.

Figure export presets live in `app/core/figure_export.py`.

- `FIGURE_EXPORT_PRESETS` owns the screen, presentation, and draft-publication presets.
- `safe_figure_filename()` owns filename sanitization.
- `export_figure_with_preset()` applies font, line, marker, format, and DPI settings before saving the current Matplotlib figure.
- `PlottingTab.export_current_figure()` should record figure exports in project history and refresh the current plot after export so preset styling does not persist on screen.

Keep this feature lightweight. Do not turn the plotting tab into a full graphic-design or layout editor; presets should only provide stable defaults for preview, group meeting, and draft-publication output.

Deep-analysis-only parameters should remain visually separated from standard model-free controls. Experimental actions should not write analysis results by default unless the UI explicitly enables that experimental mode and records the assumption in history.

## History And Formal Records

Use `ProjectState.history_records` for project-level actions such as import, q unit conversion, analysis, group creation, averaging, comparison, export, project save, and formal-record actions.

Every project save writes a `project_save` record. Treat this as an audit trail for reproducibility; do not remove or compress save history unless a future migration explicitly defines that behavior.

Use `CurveData.processing_history` for provenance of derived curve objects.

Formal records may reference curves, analysis results, comparison results, or reserved figure entries. Marking or unmarking a formal record should add a history record.

## Structured Method Warnings

Use `app/core/method_warnings.py` for reusable method warnings. Convert `MethodWarning` objects with:

- `warning_to_dict()`
- `warning_to_text()`

Keep `AnalysisResult.warnings` for backward-compatible text output and use `AnalysisResult.structured_warnings` for code, severity, message, and suggested action.

## Information-Budget Analysis

`information_budget()` lives in `app/core/model_free.py`. It is a finite-range, model-free companion to invariant analysis and answers where the measured invariant signal is concentrated across log-q scale.

The analysis sorts valid `q > 0` points before integration, computes `q³I(q)` for log-q contribution density, and returns cumulative Q, `q_Q10`, `q_Q50`, `q_Q90`, `d_Q50`, dominant `q3I_peak_q`/`q3I_peak_d`, normalized `Q_entropy`, low/mid/high contribution fractions, and observable d bounds from the selected q range.

`invariant_contribution` is historical implementation terminology and is no longer a main `create_curve_figure()` plot type. Keep q3I/log-q contribution values in derived exports or dedicated analysis results, but do not re-add `invariant_contribution` to the main plotting combo box unless a future plan explicitly changes the eight-plot contract.

Low/mid/high fractions default to log-q tertiles. If material-specific q bands are known, pass explicit `q_bands=(low_mid_q, mid_high_q)` to keep comparisons consistent across samples.

## Negative Calibrated Intensities

`app/core/validation.py` classifies calibrated negative intensities into slight and significant cases. Slight negatives are reported as `intensity_slight_negative` with `info` severity when both the relative magnitude and fraction are small. Significant negatives remain `intensity_negative` warnings. Summary fields include negative count/fraction, positive-only dynamic range, and log-valid/log-invalid point counts.

Do not clip negative intensities to zero or add constants for log plots. Linear, Kratky, Porod, invariant-integrand, and other non-log displays can preserve calibrated negatives. Logarithmic plots and log-based analyses must continue to exclude `I(q) <= 0` with explicit warnings.

## Model Catalog

`app/core/model_catalog.py` centralizes user-facing method names, formulas, inputs, outputs, assumptions, limitations, and status values for common plotting and model-free views. Keep this catalog synchronized with the plotting combo box, settings transparency panel, README, and method notes when adding or renaming a user-visible method.

When adding a model catalog entry, update tests so every entry has non-empty formula, inputs, outputs, assumptions, limitations, and status. Shape/model-dependent entries must state that fit quality is not unique morphology proof. Experimental or reserved entries must be clearly marked.

## 2026-07-07 Review Bugfix Notes

Uncommitted review found several order-sensitive bugs caused by assuming q arrays were already increasing. Import and project storage preserve input data non-destructively, so analysis functions that integrate, window, or estimate widths must sort local q/intensity copies before using neighbor-dependent operations.

Touched modules:

- `app/core/model_free.py`: `invariant_measured()` now sorts local q/intensity arrays before finite invariant integration.
- `app/core/invariant_analysis.py`: `_valid_range()` now returns q/intensity sorted by q before measured and extrapolated invariant calculations.
- `app/core/deep_scan.py`: `_finite_positive_curve()` now returns q/intensity sorted by q before Guinier and power-law candidate windowing.
- `app/core/feature_extraction.py`: `detect_peaks()` now sorts q/intensity before peak width and area calculations so FWHM and area stay positive for reversed input.
- `app/core/correlation.py`: `compute_correlation_function()` now sorts q/intensity before default `r_max` derivation and finite-q transforms.
- `app/ui/main_window.py`: `refresh_curve_list()` stores the previous selected row before clearing the list, then clamps and restores that row after repopulating.
- `.gitignore`: `.ai-bridge/` is ignored because it contains generated execution logs and intermediate patches, not application source.

Regression tests added:

- `tests/test_invariant.py::test_finite_q_invariant_sorts_q_before_integrating`
- `tests/test_invariant_analysis.py::test_invariant_with_extrapolation_sorts_q_before_integrating`
- `tests/test_deep_scan.py::test_deep_scan_sorts_q_before_candidate_windowing`
- `tests/test_peak_analysis.py::test_peak_detection_sorts_q_before_width_and_area`
- `tests/test_correlation.py::test_correlation_function_sorts_q_before_default_rmax`
- `tests/test_ui_style.py::test_refresh_curve_list_preserves_current_selection_by_default`

Follow-up risk: q sorting is still implemented per analysis path. If more q-neighbor analyses are added, prefer a shared helper or add explicit reversed-q tests with the new code.

## Adding A New Analysis Plugin

Implement `AnalysisPlugin`:

```python
class MyPlugin(AnalysisPlugin):
    name = "my_plugin"
    version = "0.1.0"
    description = "Short description"

    def run(self, curve, parameters):
        ...
```

Plugins should return `AnalysisResult`. Callers should prefer `safe_run()` so a single plugin failure does not crash the application.

## Adding A New Plot Type

The main plotting surface is intentionally restricted to the eight keys in `app/ui/plotting_tab.py::PLOT_TYPE_ITEMS`: `linear`, `semilog`, `loglog`, `guinier`, `kratky`, `porod`, `invariant`, and `local_slope`. Do not add another main plot type by default. If a future plan explicitly changes this contract, update `create_curve_figure()`, `PLOT_DERIVED_MAPPING`, `PLOT_TYPE_ITEMS`, method mappings, model catalog text, docs, and tests together. Logarithmic transforms must filter non-finite values and invalid log domains before calling `np.log`.

## Running Tests

From the project root:

```powershell
python -m pytest
```

When running in a restricted Windows sandbox, direct pytest temporary files to a writable project folder:

```powershell
$env:TEMP="$PWD\.tmp"
$env:TMP="$PWD\.tmp"
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
python -m pytest
```

## Packaging

This project does not currently include an automated packaging workflow. If a Windows desktop release is needed, evaluate PyInstaller or a comparable tool after confirming dependencies, icons, example data, and output-directory policy.

## 2026-07-08 Workspace Refactor Notes

The top-level GUI is organized by small container widgets:

- `app/ui/data_import_workspace_tab.py`: nests `ImportTab` and `CheckTab`.
- `app/ui/curve_workspace_tab.py`: uses a horizontal `QSplitter` to show `PlottingTab` and `AnalysisTab`.
- `app/ui/advanced_workspace_tab.py`: nests `AdvancedTab`, `DeepAnalysisTab`, and `BatchTab`.
- `app/ui/deep_analysis_tab.py`: owns `DeepAnalysisOptions`, Dmax, regularization, background fitting, and one-click deep analysis.

`MainWindow` still exposes `self.import_tab`, `self.check_tab`, `self.plotting_tab`, `self.analysis_tab`, `self.batch_tab`, and `self.advanced_tab` so existing refresh and tests continue to work. Navigation helpers `show_plotting_tab()` and `show_analysis_tab()` now select the shared `曲线工作台`.

Main plot type definitions live in `app/ui/plotting_tab.py` as the eight-key `PLOT_TYPE_ITEMS`. Plot data columns live in `app/core/plotting.py::PLOT_DERIVED_MAPPING` and must map to columns produced by `app/core/derived_data.py`. Do not reintroduce `invariant_contribution` or `peak_spacing` as main plot keys.

`app/core/plot_analysis.py` centralizes eight-plot diagnostics, fits, finite integrations, and selected-range statistics. It suppresses unrelated optional derived-column warnings such as missing Rg/D/R/alpha/reference values while preserving real domain warnings for `q <= 0`, `I <= 0`, and non-finite values. Fit residual tables are stored in `AnalysisResult.results["export_tables"]` for future or caller-specific export paths; the simplified export report page does not currently write plot-analysis summary, JSON, or residual CSV files.

Analysis preflight is intentionally one-to-one with the selected plot-analysis key. `linear` should only require finite points, `semilog` should require positive finite intensity, and log-log/Guinier/local-slope style analyses should require the relevant positive finite q and intensity domains. Do not route `linear` through invariant preflight or `semilog` through Guinier preflight.

## 2026-07-11 Automated Batch Analysis Schema / Stage 1 Task 1

### Reason

The approved automated 1D SAS in-situ batch workflow needs a single typed, serializable contract before batch import, quality assessment, candidate-model fitting, sequence analysis, result-package export, or GUI wiring can safely exchange analysis state.

### Touched Modules And Files

- `app/core/auto_batch_schema.py`
- `tests/test_auto_batch_schema.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- `app.core.auto_batch_schema` exposes six public types: `AnalysisStatus`, `ParameterValue`, `AnalysisEnvelope`, `ProgressEvent`, `AutoBatchConfig`, and `AutoBatchRun`.
- `AnalysisStatus` explicitly records successful, assumption-dependent, not-applicable, missing-prerequisite, fit-failed, invalid, and cancelled analyses so later exports never need to turn unavailable metrics into fabricated numeric values.
- `ParameterValue` and `AnalysisEnvelope` retain scalar values, units, bounds/uncertainty fields, fit-quality dictionaries, per-analysis tables, validity checks, assumptions, warnings, invalid reasons, and artifact paths.
- `AutoBatchConfig` defaults to strict shared batch consensus: `consensus_min_coverage=0.70` and `allow_per_frame_range_fallback=False`. Validation rejects empty batch IDs, invalid coverage, invalid bootstrap/sensitivity settings, unsupported reference modes, and invalid PCA/cluster dimensions.
- `AutoBatchRun` uses `app.core.data_model.utc_now_iso` for its `started_at` default. This module intentionally imports neither PySide nor GUI code and adds no third-party dependency.

### Tests Run

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py
```

Result: `3 passed`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `256 passed` at the initial task handoff.

### Follow-Up Risk

This stage is a data contract only. It does not yet import raw/calibrated curves, derive consensus q regions, perform fits, select models, calculate numerical metrics, write result packages, or expose GUI controls. Later stages must preserve these status/invalid-reason fields rather than replacing missing or failed results with inferred values.

## 2026-07-11 Automated Batch Analysis Metric Registry / Stage 1 Task 2

### Reason

The approved batch workflow needs one authoritative, ordered definition of every confirmed analysis method and every metric it is expected to expose. Later runners, exports, and GUI summaries must consult this registry rather than maintaining separate partial metric lists.

### Touched Modules And Files

- `app/core/metric_registry.py`
- `tests/test_metric_registry.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- `MetricSpec` and `MethodSpec` are frozen dataclasses. Every method stores its metric collection as a tuple, preventing shared mutable defaults from changing the declared schema during a run.
- `METHOD_REGISTRY` preserves the approved method and metric order for data quality, derived coordinates, model-free methods, peak/oscillation diagnostics, invariant/integrals, P(r), correlation/lamellar analysis, and shape-model output.
- `required_method_ids()` returns the full confirmed registry in that order. `applicable_method_ids(config)` applies only declared profile constraints without performing I/O, numerical fitting, or GUI work.
- P(r) requires `enable_pr=True` and a sample type of `particle`, `polymer`, or `unknown`. Correlation analysis requires `enable_correlation=True` and a sample type of `two_phase` or `lamellar`. Lamellar analysis requires `sample_type="lamellar"` and has no separate configuration flag.
- A default `AutoBatchConfig(batch_id="x")` therefore excludes P(r), correlation, and lamellar methods, while remaining methods stay available for later prerequisite/status checks.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
```

RED result before implementation: collection failed with the expected `ModuleNotFoundError: No module named 'app.core.metric_registry'`.

GREEN result after implementation: `3 passed`.

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

Result: `6 passed`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `259 passed`.

### Follow-Up Risk

The registry declares output coverage and profile eligibility only. It does not mean a given curve has enough data or physical prerequisites for a method; future runners must return explicit statuses and invalid reasons when metrics are unavailable. No raw experimental data were read or modified, and no result package was generated in this task.

## 2026-07-11 Metric Registry Review Follow-Up / Stage 1 Task 2

### Reason

Independent review found that the first registry tests only checked an unordered method subset, two P(r) membership cases, and a Guinier metric subset. That coverage could not reliably detect omitted methods, changed ordering, missing metrics in other methods, or incorrect correlation/lamellar profile rules.

### Touched Modules And Files

- `tests/test_metric_registry.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- The test module now pins the exact ordered list of all 18 method IDs returned by `required_method_ids()`.
- A complete literal expected registry compares every method's `method_id`, `region_type`, metric names and order, `sample_types`, and `config_flag`; it does not use subset or unordered-set checks.
- The applicability truth matrix asserts exact ordered outputs for default, particle P(r) enabled/disabled, two-phase correlation enabled/disabled, lamellar with correlation disabled/enabled, and mismatched sample-type/flag combinations.
- Tests verify `MetricSpec` and `MethodSpec` are frozen and that each method's metrics are tuple-backed. `METHOD_REGISTRY` intentionally remains the approved ordinary module-level `dict`, not a read-only mapping; callers must treat it as the authoritative contract and must not mutate it.
- This is a review-driven regression-coverage repair for an already-correct production implementation. No production code was changed, so there is no newly introduced RED result to report.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
```

Result: `12 passed`.

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

Result: `15 passed`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `268 passed`.

### Follow-Up Risk

The strengthened tests lock the currently approved registry contract but do not make the registry mapping itself immutable. Any future intentional change to a method, output metric, order, or profile rule must update the specification, implementation, and these exact regression expectations together. No raw experimental data were read or modified, and no result package was generated.

## 2026-07-11 Metric Registry Second Review Follow-Up / Stage 1 Task 2

### Reason

The second review identified two remaining blind spots: the P(r) truth matrix did not exercise every approved positive sample type, and the tuple assertion inspected only the Guinier method instead of the complete registry.

### Touched Modules And Files

- `tests/test_metric_registry.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- Added exact P(r)-enabled truth-matrix rows for `sample_type="polymer"` and `sample_type="unknown"`. Both must return the same ordered method list as the existing P(r)-enabled particle profile.
- Replaced the single-Guinier tuple assertion with an assertion over all `METHOD_REGISTRY.values()`, while retaining the existing frozen-dataclass and tuple-assignment failure checks.
- This is another review-driven test-only repair: the existing production registry matched the new expectations, so no production code was changed and no new RED result is claimed.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
```

Result: `14 passed`.

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

Result: `17 passed`.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `270 passed`.

### Follow-Up Risk

The metric registry remains an ordinary module-level dictionary by approved design. The test suite now verifies tuple metrics across all current entries, but future intentional registry additions still need matching exact expected entries and profile rows. No raw experimental data were read or modified, and no result package was generated.

## 2026-07-11 Automated Batch Input Manifest / Stage 1 Task 3

### Reason

The automated in-situ batch workflow needs a read-only, traceable boundary for discovering calibrated 1D curves, recording their source identity, and attaching optional experimental metadata before later consensus-range and analysis stages run.

### TDD Seams

- `discover_curve_files(input_dir)` is the public discovery seam: supported direct-child curve files must be naturally ordered while unrelated extensions are ignored.
- `collect_batch_inputs(input_dir, config)` is the public collection seam: optional metadata is attached to in-memory `CurveData` objects, the source hash is available in the manifest, and the original curve bytes remain unchanged.

### Touched Modules And Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- `BatchInputCollection` carries imported curves, the per-file manifest, isolated input failures, and warnings without writing any result directory at this stage.
- `discover_curve_files()` accepts direct-child `.csv`, `.txt`, and `.dat` files and reuses `natural_sort_key`; `collect_batch_inputs()` reuses `import_in_situ_series()` for existing column/unit inference and per-file failure isolation. When the configured metadata CSV sits in the selected curve folder, it is excluded from curve import and the curve manifest so it cannot become a false failed curve.
- `sha256_file()` reads files in 1 MiB blocks. Every discovered file records `source_file`, absolute `source_path`, `size_bytes`, `modified_time`, and `sha256` in the manifest.
- Only CSV metadata is accepted before Plan 4. A missing `metadata_match_column` raises `ValueError` with the missing column name. Metadata and optional q/intensity unit overrides affect only imported in-memory `CurveData` objects; matched rows record an absolute `metadata_source`, and overrides are labelled with `q_unit_source` or `intensity_unit_source`.
- The module imports no GUI/PySide code, adds no dependency, and never writes, renames, moves, or deletes original curves or metadata files.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

Results: `2 passed`, `20 passed`, and `19 passed`, respectively.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `272 passed`.

### Follow-Up Risk

This stage supports metadata CSV only; XLSX metadata requires the approved `openpyxl` work in Plan 4. It creates no analysis result, consensus range, fit, figure, workbook, or output package. Later stages must retain the manifest hashes and metadata provenance when serializing the run.

## 2026-07-11 Automated Batch Input Manifest Review Follow-Up / Stage 1 Task 3

### Reason

Independent review found that a late manifest-read failure could abort an otherwise usable batch, and that metadata matching did not yet make duplicate, unmatched, or sidecar-version states sufficiently auditable.

### TDD Seams

- `collect_batch_inputs(input_dir, config)` must retain successfully imported curves and manifest rows when one later manifest operation fails.
- `collect_batch_inputs(input_dir, config)` must reject ambiguous non-empty metadata keys, report unmatched sidecar keys, and attach stable provenance to each matched in-memory curve.
- `sha256_file(path, chunk_size)` must reject a non-positive chunk size rather than silently returning an invalid digest.

### Touched Modules And Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- Each curve candidate now receives a manifest row with `manifest_status` and `manifest_error`. `resolve()`, `stat()`, or chunked-hash `OSError` is isolated per file: the row is retained with unavailable fields set to `None`, and `failed_inputs` receives `{file, stage: "manifest", error}` without discarding other imports or manifest rows.
- Existing `import_in_situ_series()` failures remain in `failed_inputs`; a syntactically invalid but readable curve still receives a successful manifest row and its original importer failure record.
- `sha256_file()` validates `chunk_size > 0` and raises `ValueError("chunk_size must be positive")` otherwise.
- CSV metadata matching normalizes non-empty keys by string conversion and surrounding-whitespace removal. A missing match column raises a clear `ValueError`; duplicate non-empty keys raise `ValueError` with both data-row indices; blank/missing keys are ignored for duplicate matching.
- A metadata key with no imported curve produces a clear warning. For every matched curve, metadata records `metadata_source` (absolute path), `metadata_sha256`, `metadata_match_column`, normalized `metadata_match_key`, and zero-based `metadata_row_index` in addition to the row values.
- The configured same-directory metadata sidecar remains excluded from curve import and the curve manifest. After it is read, failure to calculate its SHA-256 raises a clear `RuntimeError` rather than silently omitting provenance.
- All operations remain read-only for original curves and metadata. No dependency, GUI code, output package, result directory, commit, push, or packaging action was added.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

Results: `10 passed`, `28 passed`, and `27 passed`, respectively.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `280 passed`.

### Follow-Up Risk

This stage remains CSV-only and non-recursive. A manifest failure preserves an explicit failed row but later result writers must serialize both that row and `failed_inputs`; no numerical analysis or output package exists yet.

## 2026-07-11 Automated Batch Input Metadata Coverage Follow-Up / Stage 1 Task 3

### Reason

Re-review found that when a metadata sidecar exists but omits a successfully imported curve, downstream code could not distinguish that condition from a batch with no sidecar at all.

### TDD Seam

- `collect_batch_inputs(input_dir, config)` must expose a stable per-successful-curve metadata match state whenever a CSV sidecar is configured, without changing raw input files or preventing the curve from being analysed later.

### TDD Evidence

The new partial-match/partial-missing-row test was added before the implementation and failed with:

```text
KeyError: 'metadata_match_status'
```

The focused input suite then passed after the minimal status and warning logic was added.

### Touched Modules And Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Implementation Notes

- When a metadata sidecar is configured, every successfully imported curve now records `metadata_match_status`.
- A matched curve records `metadata_match_status="matched"` in addition to the existing source/SHA-256/column/key/row-index provenance.
- A successful curve without a sidecar row records `metadata_match_status="no_matching_row"` and receives `Curve '<file>' has no matching metadata row in column '<column>'.` in the warnings list.
- This forward unmatched-curve warning is intentionally distinct from the existing reverse warning for a valid metadata key that has no imported curve.
- No metadata status is written when no sidecar is configured. All state changes remain confined to in-memory `CurveData.metadata`.

### Tests Run

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

Results: `11 passed`, `29 passed`, and `28 passed`, respectively.

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Result: `281 passed`.

### Follow-Up Risk

This status explains metadata coverage but does not validate whether a matched metadata value is physically meaningful. CSV-only metadata and non-recursive curve discovery remain intentional Stage 1 limits.

## Automated Batch-Consensus q Regions

`app/core/batch_consensus.py` is the read-only bridge from individual automatic q-region candidates to batch-level q ranges. Its public API is:

- **Historical description — superseded by the Task 4 safety revision below:** `ConsensusRegion` was originally described as carrying a normalized region type, a log-q-median q range, coverage, median candidate score, and stable supporting curve IDs. That former log-median interval is retained only as the later `log_median_q_range` audit field; it is not the executable shared fit range.
- `candidate_consensus(region_type, candidates, curve_count, min_coverage)`: resolves one normalized region type from candidate rows.
- `resolve_consensus_regions(curves, config)`: invokes the existing `detect_auto_regions()` reader and returns only supported normalized consensus regions.

### Selection Contract

- Real automatic candidate names are mapped at this boundary: `guinier_candidate` -> `guinier`, `power_law_candidate` -> `power_law`, `porod_candidate` -> `porod`, and `peak_candidate` -> `peak`. Risk/annotation candidates such as `low_q_upturn` are not consensus analysis ranges.
- A candidate must be fit-ready, have a non-empty curve ID, finite score, and a finite `0 < q_start < q_end` interval. Invalid rows are ignored rather than repaired.
- Candidates cluster by their log-q interval centers using `abs(delta_log_q_center) <= 0.35`. A cluster retains at most one (highest-score, deterministic-tie-break) candidate per curve ID.
- Coverage is the number of distinct supporting curve IDs divided by the distinct input curve IDs. A cluster below `config.consensus_min_coverage` (default `0.70`) is absent from the output.
- Valid clusters rank by coverage first and median candidate score second. Remaining ties use q range and sorted IDs, so reordering input candidates does not change the selected result.
- **Historical description — superseded by the Task 4 safety revision below:** the early implementation calculated `q_start` and `q_end` independently as log-q medians. The later strict-intersection rule replaces this as the executable range; the log-median pair remains audit-only and is not a physical-model conclusion.

### Read-Only Boundary And Limitations

- The module only reads `detect_auto_regions(curve).results["candidates"]`. It does not mutate `CurveData.q`, `CurveData.intensity`, `CurveData.metadata`, processing history, or source files.
- The fixed cluster threshold and coverage rule intentionally reject isolated high-score intervals. Broadly shifting peaks, phase transitions, or multiple coexisting regimes may therefore require a future explicitly configured strategy rather than an automatic per-frame fallback.
- Regression tests cover coverage priority, low-coverage rejection, curve-ID de-duplication, invalid/unready filtering, stable ordering, real candidate-type mapping, and preservation of curve arrays/metadata. They do not establish the scientific validity of an automatically detected interval for a particular material system.

## 2026-07-11 10:18:06 +08:00 Batch-Consensus q Range Safety Follow-Up / Stage 1 Task 4

### Purpose And Review Symptom

Independent review found that log-q-center clustering alone can join candidates such as `[0.90, 1.00]` and `[1.25, 1.35]`: their centers are close enough for the `0.35` threshold, but they have no common q interval. The former independent log-median endpoints would have created a fabricated shared analysis range. Review also found that a foreign candidate ID, `None` coerced to the string `"None"`, ordinary truthy readiness values, and same-score alternatives with different point counts needed explicit safety rules.

### Touched Files

- `app/core/batch_consensus.py`
- `tests/test_batch_consensus.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Safety-Revised Algorithm Contract

- Log-q center clustering remains the candidate-cluster step: `abs(delta_log_q_center) <= 0.35`, with a `1e-12` numerical tolerance solely to honor the exact mathematical boundary.
- After deterministic per-curve selection, executable `ConsensusRegion.q_range` is the strict intersection `(max(q_start), min(q_end))`. It is emitted only when `q_start < q_end`, so it is contained by every supporting candidate interval.
- `ConsensusRegion.log_median_q_range` preserves the previous independent log-median endpoints only as an audit statistic. It must never be used as the q range for later shared fits.
- A candidate is eligible only if `fit_ready is True` (not merely truthy), its curve ID is a non-empty string, its score and interval endpoints are finite, and `0 < q_start < q_end`. Missing, negative, or non-finite `n_points` is treated as `0.0` rather than a quality bonus.
- Same-curve candidate selection uses score, then valid `n_points`, then stable q/ID ordering. Different clusters rank coverage, median score, median valid `n_points`, then stable q/ID ordering.
- Coverage uses distinct IDs and cannot exceed `1.0`: a non-positive declared curve count or more distinct supporters than declared curves yields no consensus.
- `resolve_consensus_regions()` accepts a detector row only when `candidate["curve_id"] == curve.curve_id` for the curve just inspected. Foreign or stale rows are ignored without modifying their source dicts.

### TDD And Verification

The expanded safety tests were written before the revision. Their first run reported `8 failed, 6 passed`; failures showed the old log-median executable range, a fabricated no-overlap consensus, missing `n_points` tie-breaking, `"None"` ID coercion, coverage above one, and foreign-ID acceptance. After the minimal revision:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_consensus.py
# 15 passed in 0.81s

python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_deep_scan.py tests\test_batch_consensus.py
# 35 passed in 1.86s

python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py
# 43 passed in 1.34s

python -B -m py_compile app\core\batch_consensus.py tests\test_batch_consensus.py
# exit 0

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
# 296 passed in 6.14s
```

### Follow-Up Risks

- Strict intersection is intentionally conservative. A genuinely shifting peak or a phase-transition sequence may have no batch-wide common interval even if its centers cluster; later stages must report this as absent consensus rather than infer a per-frame fallback.
- `n_points`, candidate score, and interval overlap evaluate computational suitability only. They do not establish a unique morphology, model validity, or causal material mechanism.
- The fixed clustering threshold remains a documented operational setting. Any future change must be explicit and recorded with its sensitivity implications.

## 2026-07-11 10:33:36 +08:00 Automated Batch Failure-Isolating Orchestrator / Stage 1 Task 5

### Stable Core API

`app/core/auto_batch.py` provides the Stage 1 execution boundary:

```python
run_auto_batch(
    input_dir,
    config,
    *,
    progress_callback=None,
    cancel_requested=None,
    analysis_runner=None,
) -> AutoBatchRun
```

- `analysis_runner(curve, method_id, q_range, config)` is deliberately injected and must return a non-empty `list[AnalysisEnvelope]`. Plan 2 installs the production runner and may return multiple envelopes for one method (for example, multiple candidate shape models).
- Until Plan 2, the default runner returns one `NOT_APPLICABLE` envelope per scheduled method with `invalid_reason="production runner is installed by Plan 2"`. It does not synthesize fitted parameters.
- `AutoBatchRun.config_snapshot` is `asdict(config)`. `AutoBatchRun.consensus_regions` stores only validated finite ascending `(q_start, q_end)` tuples, never detector objects or descriptive audit intervals.
- The module is core-only (no PySide6 imports), introduces no dependency, writes no output package, and reads raw curve files only through `collect_batch_inputs()`.

### q-Range Routing And Strictness

- `guinier` uses `guinier`; `power_law`, `local_slope`, and `crossover` use `power_law`; `porod` uses `porod`; `peaks`, `shoulders`, `oscillations`, and `lamellar` use `peak`.
- When a required consensus range is absent, the method receives `None` and a warning. The orchestrator does not inspect a single curve to create an automatic fallback range, regardless of whether a caller later adds a UI option around `AutoBatchConfig.allow_per_frame_range_fallback`.
- Full-range methods use only finite q values. Fewer than two distinct finite q values yield `None` and an audit warning; no `min()` or `max()` operation is applied to an empty/NaN-only array.

### Failure, Progress, And Cancellation Semantics

- A failed input row, consensus-resolution failure, malformed consensus value, runner exception, invalid runner result type, or returned `FIT_FAILED`/`INVALID` envelope makes the completed run `partial_success` while preserving all unaffected envelopes.
- A runner exception or contract violation becomes exactly one `FIT_FAILED` envelope for that curve/method. Non-list outputs, empty lists, and list elements that are not `AnalysisEnvelope` instances are visible errors rather than silent omissions.
- A failing progress callback records a warning and cannot interrupt later analysis jobs. A failing or truthy cancellation callback safely stops input collection, consensus resolution, and later analysis jobs, sets `status="cancelled"`, sets `finished_at`, and records the reason. No skipped job receives a fabricated envelope.
- Progress events are emitted only after a completed method job and use `completed_units`/`total_units` based on the scheduled curve-method job count. Multiple envelopes for one job do not inflate progress totals.

### TDD Evidence And Current Limit

- The test module was added before the implementation and initially failed at import with `ModuleNotFoundError: No module named 'app.core.auto_batch'`.
- A later strengthened immediate-cancellation test first failed with `Failed: input collection must not run after immediate cancellation`, then passed after the initial cancellation guard moved before input collection.
- `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch.py` then reported `13 passed`.
- The Stage 1 focused regression command reported `89 passed`; the full regression suite reported `309 passed`; `python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py` exited `0`.
- This stage is orchestration only. It establishes traceability and failure behavior but is not an SAS fitting engine; Plan 2 remains responsible for the real per-method and candidate-model calculations.

## 2026-07-11 12:17:16 +08:00 Task 5 Review Follow-Up: Cancellation Gates And Runner Status Contract

### Cancellation Gate Contract

`run_auto_batch()` checks the optional `cancel_requested` callback at four scheduling boundaries:

1. Before `collect_batch_inputs()` performs any input I/O.
2. After imported curves, manifest rows, failures, and warnings have been copied into `AutoBatchRun`, but before `resolve_consensus_regions()` starts.
3. After consensus resolution returns or fails, but before the first curve-method runner may start.
4. Before every subsequent curve-method job.

At any gate, a truthy callback result—or an exception from the callback, which is conservatively treated as cancellation—sets `run.status` to `"cancelled"`, sets `finished_at`, retains work that completed earlier, records a warning, and does not create envelopes for skipped work. The post-input and post-consensus gates are intentionally separate so a cancellation cannot be delayed into an unnecessary detector/consensus operation or a first numerical runner call.

### Runner Envelope Status Contract

- Every returned item must be an `AnalysisEnvelope`, and every `AnalysisEnvelope.status` must be either an `AnalysisStatus` instance or a string equal to one of its enum values.
- Valid strings are normalized in place to `AnalysisStatus` before later status logic. This keeps downstream exports and status comparisons type-stable.
- Invalid strings, lists, `None`, and other malformed/unhashable status values are rejected inside the current runner-call `try` block. The orchestrator emits exactly one `FIT_FAILED` envelope for that current curve/method and continues later jobs where safe.
- An empty runner list remains an invalid runner contract and likewise yields one visible `FIT_FAILED` envelope.
- Returned `FIT_FAILED`, `INVALID`, and `CANCELLED` envelopes make the final run `partial_success`. A returned `CANCELLED` envelope is method-level information only; it never changes the complete batch to `cancelled`. Batch-level cancellation is controlled exclusively by `cancel_requested`.

### Review-Fix TDD Evidence

- Tests for post-input and post-consensus callback sequences, invalid/unhashable statuses, valid string normalization, empty runner output, and returned non-success envelopes were written before the repair.
- Their first focused run reported `7 failed, 3 passed, 13 deselected in 1.49s`. The failures demonstrated missing cancellation gates, invalid status acceptance, an unhashable status escaping set membership, non-normalized valid strings, and a returned `CANCELLED` envelope ending as `completed`.
- After the minimal repair, the same focused selection reported `10 passed, 13 deselected in 1.62s`; `tests\test_auto_batch.py` reported `23 passed in 1.30s`; the Stage 1 focused suite reported `99 passed in 2.60s`; the full suite reported `319 passed in 6.47s`.
- `python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py` exited `0`. No source experimental data were changed.

## 2026-07-11 12:28:57 +08:00 Stage 1 Automated Batch Foundation: Stable API And Contract

This section is the authoritative completion contract for Plan 1. It supersedes any earlier wording that described a log-median interval as an executable shared fit range.

### Stable Core API

- `AutoBatchConfig`: typed run input for the batch ID, sample profile, allowed models, unit overrides, strict-consensus settings, metadata sidecar, and later-stage options. It is a mutable dataclass rather than a frozen object; callers must treat one instance as unchanged once `run_auto_batch()` has started. The actual run-start snapshot is `AutoBatchRun.config_snapshot = asdict(config)`.
- `METHOD_REGISTRY` (the Metric Registry): the authoritative ordered output contract. Its `MethodSpec` and tuple-valued `MetricSpec` declarations define method IDs, expected metric names, nominal region dependencies, and profile eligibility. `required_method_ids()` and `applicable_method_ids(config)` select declared methods only; they do not claim that a curve has the numerical or physical prerequisites to produce a result.
- `collect_batch_inputs(input_dir, config) -> BatchInputCollection`: discovers calibrated `.csv`, `.txt`, and `.dat` files in natural filename order, imports through the existing batch importer, and returns successful curves, a manifest, failed-input rows, and warnings. It performs read-only source access. Each manifest row records path, size, modification time, SHA-256, and manifest status; an optional CSV sidecar records its source/hash and a per-curve metadata match state (`matched` or `no_matching_row`). Duplicate, unmatched, unreadable, or unsupported metadata states remain explicit failures or warnings rather than silent repairs. XLSX metadata is intentionally deferred to Plan 4.
- `resolve_consensus_regions(curves, config) -> dict[str, ConsensusRegion]`: reads temporary automatic-region candidates without changing the curves. `ConsensusRegion.q_range` is the strict common interval supported by every selected candidate; `log_median_q_range` is audit-only. Candidates below the configured coverage threshold (default `0.70`) or without an open common interval are omitted. No code in Stage 1 falls back to a per-frame q range when consensus is absent.
- `run_auto_batch(input_dir, config, *, progress_callback=None, cancel_requested=None, analysis_runner=None) -> AutoBatchRun`: composes the input collector, consensus resolver, registry eligibility, and per-curve runner into an in-memory run record. It is the Stage 1 execution boundary, not a completed result-package exporter.

### Stage Boundaries, Statuses, And Runner Contract

The Stage 1 flow is `collect_batch_inputs()` -> `resolve_consensus_regions()` -> applicable registry methods -> `AnalysisEnvelope` rows in `AutoBatchRun`. Analysis envelopes use the explicit `AnalysisStatus` values `success`, `assumption_dependent`, `not_applicable`, `missing_prerequisite`, `fit_failed`, `invalid`, and `cancelled`; unavailable or failed quantities must not be replaced by fabricated numbers.

`analysis_runner(curve, method_id, q_range, config)` is injectable for Plan 2 and must return a non-empty `list[AnalysisEnvelope]`. It may return several envelopes for one scheduled method. Every returned envelope must have `curve_id == curve.curve_id` and `analysis_type == method_id`; a status, curve identity, or method identity violation is isolated as exactly one `FIT_FAILED` envelope for that scheduled job while unaffected jobs continue. The orchestrator deliberately does not require an envelope `q_range` to equal the requested consensus/full range, because Plan 2 may need to report the concrete fit interval actually used. A completed run becomes `partial_success` when such failures are present.

The cancellation callback is checked before source input, between input collection and consensus, between consensus and the first job, and before each later job. A truthy callback value or callback exception ends the batch as `cancelled`, records `finished_at` and a warning, preserves earlier work, and does not fabricate skipped envelopes. A method-level `CANCELLED` envelope is not equivalent to batch cancellation.

Until Plan 2 supplies a production runner, the default runner returns only `NOT_APPLICABLE` envelopes with the reason that the production runner is installed by Plan 2. Consequently, Stage 1 keeps results in memory only: it does not yet calculate the requested SAS fits, select a model, write Excel/CSV/JSON, render residual/summary figures, or expose GUI controls.

### Completed Follow-Up Regression Coverage

The two independent-review coverage suggestions are now direct regression tests:

1. `candidate_consensus(..., [])`, `resolve_consensus_regions([])`, and duplicate `CurveData.curve_id` inputs are exercised directly. Coverage remains bounded and supporting IDs are deduplicated without changing curve data.
2. A cancellation sequence of `[False, False, False, False, True]` executes the first scheduled job, preserves its envelope, then cancels before the second runner call.

These tests verify scheduling and consensus-boundary behavior only; they do not change raw data or establish a material-science conclusion.

## Common Fit Diagnostics (Stage 2 Task 1)

Reusable numerical fit diagnostics live in `app/core/fit_diagnostics.py`.  This core-only module performs no fitting, GUI work, file I/O, or raw-data mutation; fitting methods supply selected arrays and retain responsibility for declaring their scientific assumptions.

- `FitDiagnostics` is a frozen, JSON-serializable record.  `to_dict()` normalizes every numeric value (including NumPy scalars) to a native finite `int`/`float` or `None`, every flag to `bool`/`None`, and every reason/basis to `str`/`None`.  `fit_diagnostics()` returns this native-Python dictionary form with the fixed keys `n`, `parameter_count`, `dof`, `rss`, `wrss`, `rmse`, `mae`, `R2`, `adjusted_R2`, `chi_square`, `reduced_chi_square`, `AIC`, `AICc`, and `BIC`.
- Any statistic that is unavailable or numerically unreliable is `None`, never an invented zero.  Finite paired observed/fitted points define unweighted statistics.  Adjusted R2 and reduced chi-square remain `None` when their applicable degrees of freedom are not positive.
- A malformed, misaligned, non-finite, or non-positive `sigma` never suppresses the valid unweighted statistics.  The returned `weighted`, `weighted_point_count`, `weighted_dof`, `sigma_aligned`, `invalid_sigma_point_count`, `non_finite_weighted_residual_point_count`, and `weighting_reason` fields distinguish invalid error values from finite errors whose residual/standardization overflows.  With partially valid errors, chi-square uses only aligned valid standardized-residual points.
- `fit_diagnostics(..., sigma_is_absolute=True)` treats effective valid sigma as absolute uncertainties and calculates AIC/AICc/BIC from `chi_square + sum(log(2*pi*sigma**2))` over the actual weighted points.  It reports `information_criterion_basis="absolute_sigma_gaussian"` and the weighted point count.  When effective sigma are explicitly relative (`sigma_is_absolute=False`), all three information criteria are `None` with `information_criterion_basis="unavailable_relative_sigma"` and reason `relative_sigma`; no unweighted RSS criterion is silently reused for weighted model selection.  Without effective weighting, residual-variance criteria are labelled `unweighted_residual_variance`.
- `parameter_records()` always emits the same parameter-row schema: `name`, `value`, `unit`, `initial`, `lower_bound`, `upper_bound`, `stderr`, `ci95_low`, `ci95_high`, and `bound_hit`.  It accepts sequence or name-keyed optional metadata, uses `None` for unavailable uncertainty, and uses a tolerance (not exact float equality) for bound flags.  Bounds use a stable rule: list/tuple entries that are per-parameter `(lower, upper)` pairs are interpreted by parameter; a SciPy vector form must be `(lower_array, upper_array)` with NumPy arrays; an `(n_parameters, 2)` NumPy array is also per-parameter.
- `covariance_to_correlation()` returns JSON-safe nested lists.  Zero/negative/non-finite variances and non-finite correlations become `None`; non-square or asymmetric covariance input raises a clear `ValueError` rather than being silently repaired.  For all-finite symmetric matrices, it rejects materially non-positive-semidefinite covariance using `eigvalsh` and the documented relative tolerance `1e-10 * max(1, max(abs(covariance)))`.  A partially non-finite matrix is not asserted PSD; only unavailable correlations become `None`.
- `build_residual_rows()` preserves one row per original input point, including invalid points.  Its required q/observed/fitted/residual/standardized-residual/sigma/weight/inclusion fields make exclusions and unusable weights visible.  Inconsistent row-array lengths raise a predictable `ValueError`.

These diagnostics describe the numerical result conditional on a chosen model, range, data preprocessing, and weighting convention.  They do not prove model uniqueness, a material microstructure, or a causal mechanism.

## Complete Model-Free Fit Outputs (Stage 2 Task 2)

`app/core/model_free.py` keeps the public signatures of `guinier_analysis()`, `power_law_analysis()`, and `local_slope()` while extending their `AnalysisResult.results` payloads for batch export and audit.

- Guinier and power-law fits now record the actual selected `q_start`/`q_end`, fitted and excluded point counts, all selected-fit residual rows, and raw-row provenance in every exclusion (`original_index`, q, intensity, error, and reason).  Legacy fields such as `qRg_min`/`qRg_max`, `R2`, and `residuals` remain for callers that already use them; the explicit `qminRg`/`qmaxRg`, `fit_quality`, `parameter_records`, `uncertainty`, `validity`, and `assumptions` fields are the traceable contract for new exports.
- `fit_quality` comes from `fit_diagnostics()` in the actual transformed coordinate.  It contains R2, RMSE, chi-square/reduced chi-square, AIC/AICc/BIC, and an explicit information-criterion basis.  `residual_rows` contains only points that truly entered the line fit; excluded raw points are never disguised as zero residuals.
- When an aligned error column exists, log-domain fitting uses the physically propagated absolute uncertainty `sigma_lnI = error / I`.  Weighting is used only if **all** selected log-domain errors are finite and positive.  Missing, mismatched, or partly invalid errors trigger an unweighted fit over all otherwise valid q/I points; `error_audit` records the reason and original indices so a partial error column cannot be represented as a fully weighted fit or silently bias which curve points enter the fit.
- Parameter rows retain a fixed schema and include derived Guinier `Rg`/`I0` and power-law `alpha`/prefactor uncertainty where finite covariance estimates permit it.  A non-negative Guinier slope leaves `Rg`, `qminRg`, and `qmaxRg` as `None` and sets a clear validity reason instead of returning a fabricated physical size.
- Local-slope outputs keep the former `q_mid`, `alpha`, and `plateau_candidate_ranges` compatibility fields and add row-level `point_rows` (`q`, `alpha`, `valid`, reason, and raw provenance) plus plateau objects with `plateau_id`, q bounds, alpha mean/std, point count, and a stability score clipped to `[0, 1]`.  The local derivative and any plateau remain descriptive; neither alone establishes a material mechanism.

All three methods operate on local NumPy arrays only.  They do not sort, alter, remove, or write `CurveData` arrays or raw experimental source files.

### Task 2 Review Follow-Up: Weighting, Derivative Semantics, And Unperformed Fits

- For a fit with a valid **absolute** propagated `sigma_lnI`, the parameter covariance is the unscaled WLS matrix `(Xᵀ W X)^-1` (implemented through `numpy.polyfit(..., cov="unscaled")`).  It is not multiplied by the observed residual variance.  This preserves non-zero parameter CI for an exact synthetic curve with stated measurement uncertainty; unweighted OLS continues to use its residual-scaled covariance convention.
- `eligible_points` is the number of q/I points that passed the selected log-domain rules.  `actual_fit_points` is the number that actually entered a successful linear fit, and `fit_not_performed_rows` preserves each eligible row when the line cannot be established (for example, one eligible point or non-distinct transformed x).  The legacy `fit_points` field remains the eligible-count compatibility field and explicitly declares that semantic in `fit_points_semantics`; exporters must use `actual_fit_points` with `residual_rows` when reporting fit execution.
- When a fit is not performed, `actual_fit_points=0`, residual rows are empty, fit diagnostics use `n=0`, `weighted_fit=False`, and `error_audit.weighting_decision="no_fit_performed"`.  The audit retains the pre-fit error decision separately so data availability is visible without implying that weighting actually occurred.
- `local_slope()` calculates a local derivative, not an OLS or WLS regression.  It calls the shared domain selector in a non-weighting mode: `error_audit.strategy="not_used_for_local_derivative"` and `weighting_decision="not_applicable"`.  It must not emit ordinary-least-squares or weighted-fit wording solely because the input lacks an error column.

## Extended Numerical Features (Stage 2 Task 3)

The extended-feature modules expose numerical candidates and audit information only. None of a peak, shoulder, crossover, oscillation, Kratky maximum, or Porod plateau establishes a unique morphology, conformation, correlation, or material mechanism.

- `detect_peaks()` stably sorts selected local arrays and collapses duplicate q rows by mean intensity before any width calculation. It retains legacy peak keys and adds `prominence`, `snr`, `valid`, and `validity_reason`. If a peak is demonstrably edge-truncated or lacks two usable half-height crossings, all dependent width/area/size quantities (`FWHM`, `HWHM`, FWHM-derived areas, `correlation_length`, and `asymmetry`) are `None` and the validity audit explains why.
- `porod_deep_analysis(..., two_phase_confirmed=False)` preserves old calls but blocks absolute surface candidates unless the caller explicitly confirms a two-phase system in addition to absolute intensity, non-zero contrast, a positive stable plateau, and a Porod-like exponent. The boolean is stored in parameters, results, assumptions, and validity checks.
- `kratky_metrics()` keeps legacy `q_K`, `q2I_max`, and `d_K`, but only reports width/area when the same q index is an internal complete peak. `width_peak_q`, `width_peak_index`, `width_peak_matches_q_K`, `enriched_peak_identity`, and `peak_completeness_status` make a boundary/global-maximum mismatch explicit. Duplicate q rows are collapsed locally with a warning before peak-width calculations.
- `extended_integrals()` collapses duplicate q rows before integration. A non-finite `q^n I(q)` product makes its corresponding weighted integral unavailable (`None`) with a warning rather than exporting `inf`. Finite-range band contributions and positive-contribution quantiles remain descriptive measured-range quantities.
- Shoulder and oscillation rows use the labels `numerical_shoulder_candidate` and `numerical_oscillation_*_candidate`, plus edge/completeness/validity/provenance fields. Oscillation analysis rejects non-finite prominence input and records the deterministic `find_peaks` minimum-index-distance strategy (`min_points // 4`, minimum one point) in both result-level and row-level provenance.

All sorting, duplicate handling, derivatives, extrema, and integrations use local arrays. The functions never modify raw `CurveData` arrays or source experimental files.

### Task 3 Independent-Review Safety Recovery (2026-07-11)

The post-implementation review added a stricter numerical-publication rule: a scalar exposed through a Task 3 result is either a native finite value or `None`; intermediate finite operands are not sufficient evidence that a reduction is safe. The repair retains the public signatures and legacy result keys while making unavailable values explicit.

- Duplicate-q consolidation in extended features, peak detection, and Kratky metrics uses a scaled group mean instead of an overflow-prone weighted sum. The collapsed outputs are finite-audited before downstream gradients or extrema. This is local-array processing only and never mutates a `CurveData` array.
- `extended_integrals()` routes every full-range and q-band trapezoid through a finite guard. An overflowed `Q_low`, `Q_mid`, or `Q_high` is `None` and emits an audit warning. Contribution quantiles are likewise withheld if their cumulative trapezoidal reduction is unsafe.
- Porod statistics deliberately withhold mean/std/CV/range/noise when finite values exceed the safe statistical-reduction range. Absolute surface candidates require a literal Python `True` for `two_phase_confirmed`, an exactly finite numeric contrast whose square and `2*pi*contrast**2` denominator are both finite and positive, a valid contiguous plateau candidate, and a finite positive candidate result. The all-selected-range plateau remains descriptive; it is not used as a substitute for the contiguous candidate.
- Peak `baseline` and full `area` are explicitly based on the SciPy prominence-contour convention, not a physical background fit. If either prominence base touches the selected q-range boundary, `baseline_edge_limited=True`, full `area=None`, and the peak is not valid even if two half-height crossings support FWHM. FWHM-local quantities retain separate provenance and validity.
- Peak/Kratky/crossover/shoulder/oscillation d-spacings, widths, areas, SNRs, correlations, and aggregate spacings receive a final finite guard. An unavailable scalar carries a warning or row-level reason; a peak/Kratky result cannot remain valid/complete while exporting a non-finite derivative.
- Crossover, shoulder, oscillation, and shape-distance count/threshold arguments reject booleans, non-numeric values, non-integers where counts are required, and all `NaN`/`inf` values before slicing or SciPy calls. Shoulder provenance records the concrete peak-prominence threshold, point spacing, candidate score, and maximum score.
- Oscillation completeness is based on SciPy prominence `left_bases`/`right_bases`, not only an extrema index. A prominence contour that reaches either selected q-range boundary is `edge_truncated`, `valid=False`, and records its contour support in provenance.

The regression suite includes finite-but-extreme duplicate groups, integration and statistical reduction overflows, `NaN`/`inf` thresholds, truthy non-boolean phase flags, unsafe contrast squaring, invalid contiguous plateaux, edge-supported prominence contours, and tiny-q d-spacing overflows. These numerical controls make results auditable; they do not make a curve descriptor a proof of a material mechanism.

## Conditional Advanced Analyses (Stage 2 Task 4)

`compute_pr()`, `invariant_with_extrapolation()`, `compute_correlation_function()`, and `lamellar_analysis()` retain their public signatures. Their result dictionaries now share an explicit conditional-result convention:

- `prerequisites` records whether the sample model, calibration, contrast, q coverage/extrapolation, and Porod plateau are satisfied, missing, assumed, not required, or not applicable for that specific analysis.
- `assumption_status="assumption_dependent"` and `analysis_status="assumption_dependent"` remain present even when a numerical inversion or transform converges. A remaining structural/model assumption must not yield `reliability_label="high"`.
- A quantity that cannot honestly be calculated is `None`, with `<metric>_status` and `<metric>_invalid_reason` where it is an absolute or conditionally interpreted quantity. A missing quantity is never encoded as `0`.

P(r) keeps its legacy `Rg_from_pr`, `distribution_peak_r`, `fit_I`, and residual fields and adds the registered aliases `Rg_pr`, `peak_r`, `peak_height`, `peak_count`, `tail_score`, `negative_fraction`, `smoothness`, `backfit_rmse`, and `backfit_chi_square`. `export_tables["pr_distribution"]` is the real-space r/P(r) table; `export_tables["pr_backfit"]` provides q, observed I(q), back-calculated I(q), and residual rows. A statistical chi-square is `None` with a missing-prerequisite reason until aligned per-point uncertainty is available; RMSE remains an unweighted numerical diagnostic.

Invariant analysis preserves measured `Q_measured` and uses local selected arrays for all integrations. `export_tables["invariant_integrand"]` contains selected q, observed I(q), and q²I(q) rows; a non-finite row integrand is represented as `None`. Disabled or failed tail extrapolations return `None` for their individual contribution and explicit status/reason; `Q_total` is clearly labelled as finite-range, incomplete, or model-dependent. A `porod_q^-4` contribution is accepted only when the tail `q^4 I(q)` values form a finite, positive plateau with relative spread no larger than `0.15`. `volume_fraction` is the compatibility-facing conditional quantity; it stays `None` with `volume_fraction_status="missing_prerequisite"` and a reason unless absolute intensity, finite non-zero contrast, sufficient valid q data, and a finite positive invariant are available. Even then, its status remains `assumption_dependent` because this public signature does not confirm the required two-phase sample model.

Correlation analysis supplies the full `r`/correlation table and reports `long_period`, `interface_thickness`, and `damping_length` only as finite-q, model-dependent candidates. It documents transform normalization and does not require absolute intensity or contrast for its normalized descriptor. Lamellar analysis supplies `q0`, `d0=2*pi/q0`, per-peak `order_index`, per-peak `deviation_from_integer_order`, and an order-index back-fit RMSE. q0/d0 require the unconfirmed assignment of the first detected peak as the fundamental order; neither establishes lamellar morphology by itself.

All four functions operate only on local NumPy arrays and perform no file I/O, GUI work, export work, dependency installation, or mutation of `CurveData` arrays.

### Task 4 Independent-Review Safety Follow-Up

`METHOD_REGISTRY` is a binding output contract for the Task 4 methods. Each registered metric must always appear in its method result. A numerically unavailable metric is `None` and carries `<metric>_status` plus `<metric>_invalid_reason`; consumers must not infer a zero from a missing calculation.

For invariant analysis, `Q_low`, `Q_mid`, and `Q_high` have a deliberately different meaning from `Q_low_q_extrapolated` and `Q_high_q_extrapolated`. They are finite-range integrals of `q^2 I(q)` over three equal-width q intervals across the selected q range. `Q_band_definition` and `q_band_boundaries` make this explicit, and extrapolated 0→qmin / qmax→infinity tails remain separate fields. Any insufficient-point, non-finite integrand, overflowed integration, or invalid boundary makes the affected band `None` with status/reason. The measured invariant and total invariant follow the same finite-or-`None` rule. Non-finite input contrast is withheld as `None` in both results and parameters.

Porod high-q extrapolation is accepted only when the user selected `porod_q^-4`, at least three tail points are available, **every** selected `q^4 I(q)` value is finite and strictly positive, relative spread is at most `0.15`, and the tail integral is finite and positive. A requested but under-sampled tail is `missing_prerequisite`; a non-finite/non-positive/unstable tail is `invalid_value`. Neither condition passes the `porod_plateau_valid` validity check.

P(r) validates Dmax as finite and strictly positive and regularization as finite and non-negative before allocating the r grid. Its output parameter values are exactly the values actually used (default regularization is `1e-2`). With fewer than 12 valid q points, a numerically failed solve, or a non-finite reduction, P(r) and back-fit tables are empty and unavailable scalar metrics are `None`, rather than a placeholder zero distribution or NaN rows. When `CurveData.error` is aligned with q and every selected value is finite and strictly positive, `backfit_chi_square = sum((I_observed - I_back_calculated)^2 / error^2)` is calculated. Missing, invalid, or misaligned errors remain `None + missing_prerequisite + reason`.

Correlation rejects a supplied `r_max` unless it is finite and strictly positive, with a finite fallback default when q spacing cannot safely determine rmax. `correlation_length` is explicitly the existing thresholded damping-length candidate. The current normalized transform cannot identify hard-phase thickness, soft-phase thickness, or phase fraction, so those registered metrics intentionally remain `None + missing_prerequisite + reason`. Lamellar `peak_orders` is the ordered list of per-peak integer candidate indices. All reciprocal length calculations and peak-table cells are finite-guarded; tiny-q or tiny-FWHM overflows produce `None` with an invalid reason.

## Complete Shape-Model Fits (Stage 2 Task 5)

`app/core/model_fitting.py` now has two execution boundaries. `fit_shape_model_complete()` is the complete single-model contract; `fit_shape_model()` remains a compatibility wrapper around it. `fit_all_allowed_models()` is the bounded batch comparison boundary and always returns one `AnalysisResult` for every requested registered model, even when individual models fail.

- Complete fit result fields include legacy `parameters`, `fit_q`, `fit_I`, `residuals`, and `export_tables["fit_curves"]`, plus `parameter_records`, `fit_quality`, `covariance`, `parameter_correlation`, finite-or-null covariance condition/correlation summaries with reasons, `identifiability_status`, `residual_rows`, `derived_parameters`, selected/excluded-row audit fields, and `attempts`. All numerical output is native finite data or `None`; unavailable values carry a companion reason at the relevant result/parameter/derived level.
- Attempt priority is warm start, batch median, curve-aware defaults, and two deterministic jittered defaults. The ordinary complete path evaluates every candidate and selects the successful minimum finite AICc; if no candidate has AICc, it falls back to the lowest finite RMSE. This logic is deterministic and does not mutate the input arrays.
- `fit_all_allowed_models()` invokes the same complete fitter with a documented retry-on-failure mode and a 300-function-evaluation per-start budget. It always iterates the full requested model list. A valid first candidate stops only later starts for that **same** model; it does not stop later model names. Unexecuted starts are absent from `attempts`, not represented as false successes. The result records `error_audit.attempt_selection_policy` so batch users cannot confuse this with the standalone all-candidate AICc selection.
- Identifiability is deliberately separate from numerical convergence. `weak` begins at absolute parameter correlation `0.95`, covariance condition number `1e8`, or a parameter bound hit. `non_identifiable` begins at correlation `0.995`, condition number `1e12`, or unavailable/invalid covariance information. A non-identifiable fit adds an error-level validity check and therefore cannot retain a high reliability outcome solely on residual quality.
- `app/core/model_parameters.py` owns `DERIVED_PARAMETER_BUILDERS` and `derived_model_parameters()`. It accepts either simple parameter values or legacy parameter records. Sphere, core-shell sphere, ellipsoid, cylinder, disk, surface-fractal, and lamellar mappings return per-quantity `{value, unit, reason}` records. Domain errors, zero denominators, and arithmetic overflow are normalized to `None + reason`.

The implementation is core-only: no GUI, exporter, package, dependency, raw-data, or source-file behavior was added. Shape-model outputs remain conditional descriptions and must not be interpreted as unique structural proof.

## Task 5 Review Remediation: Batch Contract Is Complete By Default

This section supersedes the earlier Task 5 wording that described `fit_all_allowed_models()` as a bounded retry-on-failure / first-valid path. That default behavior was removed after independent review because it changed the approved model-selection contract.

- `fit_all_allowed_models()` now invokes the same complete path as `fit_shape_model_complete()` for every requested model: warm start, batch median, defaults, then two deterministic jittered starts. It always records every actually executed candidate, selects from the full valid set, and still isolates a failure in one model from all later model names.
- Single and batch fitting both use `MAX_FUNCTION_EVALUATIONS = 20000`, preserving the prior single-fit default. There is no smaller default batch budget and no private first-success flag. A future faster mode would require an explicit approved opt-in API and a result label that prevents it from being confused with a complete comparison.
- Selection is two-stage and deterministic: if one or more valid attempts have finite AICc, choose the smallest AICc and retain earliest attempt order for an exact tie. Only if every valid attempt lacks finite AICc is the smallest finite RMSE used. RMSE is not an AICc tie-breaker.
- `tests/test_complete_model_fitting.py` contains controlled public batch tests that set the warm-start AICc to 99 and later candidates to 95, verify all attempts exist and the selected attempt has AICc 95, then separately verify RMSE fallback only when all AICc values are null. A controlled all-model failure-isolation test preserves coverage without treating optimizer runtime as the contract.

The scientific interpretation limit is unchanged: an AICc-selected numerical model is conditional on the selected q range, background treatment, uncertainty convention, and model assumptions, and does not establish unique sample morphology.

### Observed Default Complete-Batch Runtime

After restoring the complete batch contract, a public smoke run over all ten models on a 36-point in-memory `exp(-q)` curve reached the 60.4-second command limit before returning final results. The workload deliberately included the full warm/median/default/two-jitter sequence and the shared 20,000-function-evaluation cap for every model.

The practical bottleneck is the repeated orientation-average evaluation in ellipsoid, cylinder, and disk candidates when they are optimized against an implausible curve, not an early exit in the model loop. This observation does **not** authorize a default shortcut: no batch budget reduction, first-valid stop, or hidden fast path is enabled. Any future high-throughput alternative must be separately approved, explicitly opted into, and return a result that cannot be mistaken for the complete all-candidate comparison.

## Optional Bootstrap and q-Range Sensitivity (Stage 2 Task 6)

`app/core/uncertainty_analysis.py` is a pure in-memory uncertainty helper. It does not own a curve, fit model, GUI action, export, or file path. A caller supplies the numerical callback and decides whether to attach its result to a later batch/report workflow.

- `bootstrap_fit(fit_callback, ...)` requires a pool of included point indices: pass `included_indices=` explicitly or attach `included_indices`, `included_point_indices`, `valid_indices`, or `indices` to the callback. It copies the pool, uses `numpy.random.default_rng(seed)`, and passes an equal-length replacement sample to each callback invocation. The summary records `seed`, `sample_count`, every resampled index row, and successful/failed refit counts.
- `range_sensitivity(range_callback, (q_low, q_high), ...)` perturbs each endpoint by `(-fraction, 0, +fraction)` times the original interval width and evaluates the nine lower/upper combinations. Every actual or rejected candidate appears in `attempts` with q range, shifts, success, finite parameters, and an objective reason when unavailable.
- `UncertaintySummary` is frozen and `to_dict()` emits native JSON-safe fields. Its statistics use `p2_5`, `p50`, and `p97_5` quantiles. Coefficient of variation is sample standard deviation divided by absolute mean; unavailable CV has a per-parameter reason. `sensitivity_score = max(CV / (1 + CV))` across finite CV values, so it is bounded in `[0, 1]`; it remains `None` with `sensitivity_reason` when that calculation is not defensible.
- Both interfaces take `enabled` and `minimum_valid_fits`. Disabled calculations make no callback calls and return `status="not_enabled"`; insufficient successes return `status="insufficient_valid_fits"` with empty uncertainty statistics. Callback exceptions are isolated as failed attempt rows. These statuses describe the optional diagnostic only and never invalidate a primary fit.
- To support existing `AutoBatchConfig` without introducing a dependency on the batch runner, both interfaces also accept a duck-typed `config=` object or mapping. Bootstrap reads `enable_bootstrap`, `bootstrap_samples`, and `bootstrap_seed`; range sensitivity reads `enable_range_sensitivity` and `sensitivity_boundary_fraction`. The config values override the corresponding function defaults when supplied.

The calculated spread is conditional on the selected included points, resampling seed, q-range perturbation definition, callback behavior, model assumptions, and primary fit setup. It must not be treated as independent experimental replication, a unique structural assignment, or causal evidence.

### Task 6 Review Remediation: Strict Optional-Input Boundary

The optional uncertainty APIs now distinguish control metadata from numerical fit parameters and normalize unsafe public inputs before any callback/RNG execution.

- `_finite_float()` rejects Python and NumPy booleans. When a callback returns a direct mapping (rather than explicit `parameters`/`parameter_records`), known metadata keys such as `converged`, `status`, `reason`, errors, warnings, validity flags, and count fields are ignored. A direct metadata-only mapping has no finite fitted parameter and becomes `callback_returned_no_finite_parameters`; it cannot create quantiles, CV, a sensitivity score, or a false completed status. Mixed direct mappings retain genuine numeric parameters while ignoring metadata.
- `range_sensitivity()` uses an exact q-bound validator before callback execution. It accepts only exactly two non-string, non-mapping iterable elements that are non-boolean finite numeric scalars and strictly ascending. Extra/missing bounds, scalar/string inputs, boolean bounds, NaN/inf, or non-ascending values return `status="invalid_input"`, `q_range_must_contain_two_finite_ascending_bounds`, no attempts, and no callback calls.
- Bootstrap seed normalization accepts only non-negative finite integer scalars that are not booleans or strings. Invalid direct/config seed values return a JSON-safe `invalid_input` summary with reason `seed_must_be_non_negative_finite_integer`, null seed, and no callback/RNG attempts. A defensive RNG-construction catch preserves that same optional-failure boundary for platform-specific invalid seed handling.

These failures are diagnostics of the optional uncertainty request, not of the primary SAS fit. Consumers must not elevate a malformed callback/configuration into a model-validity conclusion.

### Task 6 Final-Review Scalar and Array Boundary

The uncertainty helper treats parameter values, q-range endpoints, and RNG seeds as public scalar contracts rather than relying on NumPy/Python coercion.

- `_finite_float()` accepts only a finite native or NumPy numeric scalar. It rejects booleans, text, bytes, and every `numpy.ndarray`, including 0d arrays and one-element arrays. Therefore callback output such as `{ "radius": np.array([7.0]) }` is a failed optional refit (`callback_returned_no_finite_parameters`), not an invented `radius=7.0` value.
- A NumPy q-range must have `ndim == 1` and `size == 2`; it is checked before `range_sensitivity()` generates variants or calls a callback. A two-dimensional `(2, 1)` array is not flattened into an interval. A one-dimensional numeric array such as `np.array([0.01, 0.1])` remains an accepted boundary pair.
- Bootstrap seeds are deliberately narrower: native `int` and NumPy integer scalars are allowed only when non-negative; floats, booleans, strings, and all arrays are invalid. The same rule applies to direct keyword and duck-typed config values before `numpy.random.default_rng()` is reached.

This defensive parsing preserves reproducibility and auditability, but it does not turn bootstrap/range perturbation into independent replication or proof of a material mechanism.

## Production Batch Runner and Stable Model Selection

`app/core/analysis_runner.py` is the production-only dispatch boundary for `auto_batch`. Its `ANALYSIS_HANDLERS` mapping is deliberately explicit and is checked against the applicable registry methods before batch input work begins. A missing handler raises `BatchConfigurationError`; an analysis exception becomes a single registry-complete `FIT_FAILED` envelope so later methods and curves can still run.

Every `AnalysisEnvelope` contains one `ParameterValue` for each metric listed in `METHOD_REGISTRY`. A quantity that a numerical method cannot calculate is represented as `value=None` with an explicit status/reason rather than being omitted or converted to zero. Shape-model analysis returns one envelope per allowed model; its fit quality retains AICc, BIC, convergence, bound-hit information, and a relative-stderr uncertainty summary when available.

`app/core/model_selection.py` only aggregates already-produced shape-model envelopes. It does not rerun fits. The ranking order is coverage (descending), median AICc/BIC rank, residual-pass rate, bound-hit rate, and uncertainty. Models with coverage below `0.70` remain in `AutoBatchRun.rankings` but cannot become `AutoBatchRun.main_model`. The selected main model is fixed for the entire completed batch. `transition_flags` records an alternative per-frame winner only after it remains best for three consecutive frames; the flag is a review cue and never changes the main model automatically.

`run_auto_batch()` keeps its injected-runner seam for tests and specialized callers. With no injected runner it uses the production registry runner, preserves cancellation and per-method failure isolation, then fills `rankings`, `main_model`, and `transition_flags` only after a non-cancelled loop completes. No handler mutates `CurveData`, raw experiment files, or source imports.

## Stage 2 Task 8: Documentation Contract

`docs/method_notes.md` now mirrors all 18 `METHOD_REGISTRY` entries and records their scalar fields, detailed tables, unit roles, prerequisites, and interpretation limits. `docs/advanced_methods.md` is the authoritative current description of P(r), invariant/extrapolation, correlation, lamellar analysis, all 10 `MODEL_SPECS`, model-level tables, uncertainty, and stable batch selection; obsolete “reserved” descriptions were removed.

Future registry or model changes must update both documents in the same change. A metric that is unavailable remains an explicit null with status/reason. Documentation and UI/report text must never imply that convergence, R², AICc/BIC, bootstrap stability, sequence continuity, or a numerical rank proves unique morphology or mechanism.

Task 8 verification on 2026-07-11: `compileall` passed; the fit-diagnostics/analysis-runner/model-selection/complete-fitting suite passed 57 tests; the complete Qt-offscreen/Agg suite passed 510 tests; `git diff --check` and the scoped conflict-marker check passed. Git status was inspected only and retained all pre-existing Stage 1/2 changes; no commit or package was created.

## Stage 3: In-situ Sequence Analysis

`app/core/sequence_analysis.py` is a read-only post-processing layer over imported curves and completed envelopes. It chooses an explicit configured metadata axis when complete, otherwise `frame_index`, then `sequence_order`; missing axis values retain stable input order. It produces a frame table, a long parameter-trajectory table, reference-curve RMSE/MAE/relative absolute area, and robust consecutive-difference flags. Optional controls produce descriptive linear trends and NumPy-only PCA/deterministic k-means summaries on a common interpolated q grid.

`AutoBatchRun.sequence_results` stores the JSON-safe result. The production batch runner invokes it only when `enable_sequence_analysis` is true and isolates failures without changing individual method envelopes. Reference modes are `first`, `previous`, and `selected`; a missing selected curve is an explicit warning. Change flags, trends, PCA, and clusters are review aids, not proof of phase transition, kinetics, causality, or mechanism.

## Stage 4: Result Package and One-click GUI

`app/core/result_package.py` exports a completed `AutoBatchRun` into a newly created directory. It refuses an existing target and writes into a unique incomplete sibling before the final rename. The package contains the full JSON record, parameter and fit-quality summaries, model rankings, source manifest/failures/warnings, sequence tables, PCA/cluster scores, an analysis-table index, individual method/model tables, and a Chinese README with interpretation limits.

`app/ui/auto_batch_tab.py` adds the “全自动批量分析” page. The user selects a read-only curve directory, result parent, batch name, sample type, and optional assumption-dependent methods. A `QThread` worker runs the production batch and exporter without blocking the GUI and creates a run-ID-specific result folder. It does not change source curves or silently overwrite an old result.

Final Stage 3/4 verification on 2026-07-11: `compileall` passed; the combined result-package/GUI/sequence/regression suite passed 62 tests; the complete Qt-offscreen/Agg suite passed 517 tests. `git diff --check` and the scoped conflict-marker check passed. Git status was inspected and all pre-existing Stage 1/2 changes were preserved; no dependency, package, commit, or push was created.

## 2026-07-11 - Review Remediation: Sequence Safety And Cancellation

- Symptom: reversed/unsorted q could invalidate reference-area integration; NaN intensity could reach SVD; failed methods lost registry fields; cancelled GUI runs were exported as complete; new Chinese UI/README strings were mojibake.
- Root cause: only the reference q array was sorted, exploratory preprocessing did not enforce finite positive pairs, failure envelopes were created without registry parameters, and the initial GUI/export slice had no cancellation-state contract.
- Fix: sort local curve copies before interpolation/integration; filter finite positive q/I pairs before the common-grid PCA path; populate failed/cancelled parameters and units from `METHOD_REGISTRY`; materialize all known unexecuted jobs as cancelled envelopes; check cancellation again after each runner; add a thread-safe cancellation event; export cancelled runs with `_incomplete`; replace corrupted strings with UTF-8 Chinese.
- Tests: added public-seam regression coverage in `test_sequence_analysis.py`, `test_auto_batch.py`, `test_result_package.py`, and `test_auto_batch_ui.py`.
- Follow-up: the full results-package roadmap (Excel workbook, plots, and per-fit directory contract) remains separate unfinished work.
