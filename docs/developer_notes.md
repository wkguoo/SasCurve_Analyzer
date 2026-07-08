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
