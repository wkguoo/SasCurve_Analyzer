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

## Settings

Settings are handled by `app/core/settings.py`.

`load_settings()` returns defaults if the settings file is missing, invalid, or incomplete. `save_settings()` writes JSON. `MainWindow` loads settings on startup and applies defaults to import, plotting, and export flows.

Do not read arbitrary sensitive paths for settings. Keep the default settings file local and explicit.

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

## History And Formal Records

Use `ProjectState.history_records` for project-level actions such as import, q unit conversion, analysis, group creation, averaging, comparison, export, project save, and formal-record actions.

Use `CurveData.processing_history` for provenance of derived curve objects.

Formal records may reference curves, analysis results, comparison results, or reserved figure entries. Marking or unmarking a formal record should add a history record.

## Structured Method Warnings

Use `app/core/method_warnings.py` for reusable method warnings. Convert `MethodWarning` objects with:

- `warning_to_dict()`
- `warning_to_text()`

Keep `AnalysisResult.warnings` for backward-compatible text output and use `AnalysisResult.structured_warnings` for code, severity, message, and suggested action.

## Information-Budget Analysis

`information_budget()` lives in `app/core/model_free.py`. It is a finite-range, model-free companion to invariant analysis and answers where the measured invariant signal is concentrated across log-q scale.

The analysis sorts valid `q > 0` points before integration, computes `q^3 I(q)` for log-q contribution density, and returns cumulative Q, `q_Q10`, `q_Q50`, `q_Q90`, `d_Q50`, dominant `q3I_peak_q`/`q3I_peak_d`, normalized `Q_entropy`, low/mid/high contribution fractions, and observable d bounds from the selected q range.

Use `create_curve_figure(..., plot_type="invariant_contribution")` for the q^3I versus ln q view. This plot is useful for scale-budget inspection; it is not an extrapolated 0-to-infinity invariant and should be reported with the selected q range.

Low/mid/high fractions default to log-q tertiles. If material-specific q bands are known, pass explicit `q_bands=(low_mid_q, mid_high_q)` to keep comparisons consistent across samples.

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

Extend `create_curve_figure()` in `app/core/plotting.py`, then add the plot name to `app/ui/plotting_tab.py`. Logarithmic transforms must filter invalid values before calling `np.log`.

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
