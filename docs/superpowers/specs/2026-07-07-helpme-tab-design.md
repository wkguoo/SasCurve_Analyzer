# Helpme Tab Design

Date: 2026-07-07

## Goal

Add an in-application `新手帮助` tab that teaches first-time users how to use SAS Curve Analyzer from imported calibrated 1D SAS curve data through checking, plotting, model-free analysis, formal-record selection, and export.

## User Decision

The approved placement is an application tab beside the existing workflow tabs, not a separate dialog and not a documentation-only page.

## Scope

In scope:

- Add a PySide6 help tab class under `app/ui/`.
- Register the tab in `MainWindow` after the existing workflow tabs.
- Present a detailed Chinese beginner guide inside the app.
- Cover both single-curve and batch in situ workflows.
- Explain input data requirements, q/I/error columns, units, and calibrated-data assumptions.
- Explain when to use validation, plotting, model-free analysis, batch comparison, records, templates, advanced features, and exports.
- Include method-boundary warnings so users do not overinterpret descriptive metrics.
- Add UI smoke tests for the tab and key content.
- Record the change in `CHANGELOG.md` and `docs/developer_notes.md`.

Out of scope:

- No numerical analysis changes.
- No import/export schema changes.
- No new external packages.
- No interactive tutorial engine, sample-data launcher, or embedded web view.
- No duplicate full Markdown manual file in this change.

## Recommended Approach

Use one scrollable `QTextEdit`-based page. The page should be read-only, styled consistently with the existing Qt theme, and contain sectioned Chinese text. This matches the current UI style, keeps the implementation small, and avoids maintaining a complex multi-widget tutorial surface.

## UI Design

Add `app/ui/help_tab.py` with `HelpTab(QWidget)`.

The tab should include:

- A short title and purpose statement.
- A beginner workflow map:
  1. Prepare calibrated 1D data.
  2. Import one file or a numbered in situ series.
  3. Select the active curve from the left list.
  4. Run data checks.
  5. Plot the curve and inspect warnings.
  6. Choose q ranges and run model-free analyses.
  7. Compare or average batches when needed.
  8. Mark important curves/results as formal records.
  9. Export reports, feature tables, Origin tables, or project folders.
- A data-format section with examples of required and optional columns.
- A per-tab usage guide matching the existing tab names.
- An analysis-method guide covering Guinier, power law, local slope, peak detection, invariant, information budget, Kratky, and Porod metrics.
- A batch/in situ section explaining natural sorting, metadata, long-table export, and matrix export requirements.
- A reporting section explaining formal records, Markdown reports, complete analysis bundles, and saved project folders.
- A troubleshooting section for missing columns, invalid log plots, empty analyses, missing error columns, mismatched q grids, and experimental advanced results.

## Architecture

`HelpTab` is UI-only. It depends only on PySide6 widgets and the shared `apply_help()` helper. It must not call `app/core` numerical routines or mutate project state.

`MainWindow` owns the new tab instance just like the other tab classes. `_configure_tab_help()` gains a tooltip entry for the new index.

## Error Handling

The help tab has no user-triggered computation, so runtime error handling is limited to normal widget construction. Content should avoid promises that depend on unavailable sample files or installed external tools.

## Testing

Add focused tests in `tests/test_ui_style.py` or a nearby UI test file:

- Construct `MainWindow` in offscreen Qt mode and assert that one tab is named `新手帮助`.
- Assert the tab tooltip describes beginner guidance.
- Assert the help text contains key workflow terms such as `数据导入`, `数据检查`, `无模型分析`, `导出报告`, `Origin 长表`, and `方法边界`.

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
python -m pytest tests/test_ui_style.py -q
python -m py_compile main.py app\core\*.py app\ui\*.py
```

## Documentation And Records

Because repository guidelines require recording every behavior change, update:

- `CHANGELOG.md` with date, reason, touched files, fix summary, tests run, and follow-up risk.
- `docs/developer_notes.md` with a short note that the beginner help tab is maintained in `app/ui/help_tab.py` and should stay aligned with tab labels, export names, and method caveats.

## Risks

The main maintenance risk is drift: future tabs, export names, or analysis methods may change without updating the help text. Mitigate this with a smoke test for key terms and a developer note requiring help text updates when workflow labels or user-facing capabilities change.
