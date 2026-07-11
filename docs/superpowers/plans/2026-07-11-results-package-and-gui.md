# Results Package and GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the one-click GUI workflow and non-destructive result package containing the 16-sheet summary workbook, complete CSV/JSON fit artifacts, figures, manifest, progress and safe cancellation.

**Architecture:** A core result writer creates an atomic time-stamped package from `AutoBatchRun`; a thin PySide6 tab collects one-time batch settings and runs the core workflow in a worker thread. The GUI never performs numerical analysis directly.

**Tech Stack:** Python 3.x, pathlib, json, pandas, openpyxl, matplotlib, PySide6, pytest; Plans 1–3 interfaces.

## Global Constraints

- Prerequisites: Plans 1–3 are complete and green.
- Add only `openpyxl` as the workbook dependency; request approval before downloading/installing if it is absent.
- Write results only under a new `results/<batch>_<timestamp>`-style directory selected by the user.
- Never overwrite raw files or an existing result package.
- Pointwise tables exceeding Excel limits remain complete in CSV; Excel stores summaries and paths.
- GUI remains responsive; cancellation is checked between atomic curve/method/model operations.
- Do not automatically package, commit or push.

---

## File Structure

- Modify `requirements.txt`: add `openpyxl`.
- Modify `app/core/batch_inputs.py`: add XLSX/XLSM metadata reading after `openpyxl` is available.
- Create `app/core/auto_batch_export.py`: staging directory, manifest, CSV/JSON artifacts, Excel workbook and finalization.
- Create `app/core/auto_batch_figures.py`: export fit/residual/sequence figures from stored tables.
- Create `app/ui/auto_batch_worker.py`: QObject worker and signals.
- Create `app/ui/auto_batch_tab.py`: batch form, preview, progress, cancel and result path.
- Modify `app/ui/advanced_workspace_tab.py`, `app/ui/main_window.py`, and optionally `app/core/settings.py` for the default result root.
- Add `tests/test_auto_batch_export.py`, `tests/test_auto_batch_excel.py`, `tests/test_auto_batch_worker.py`, `tests/test_auto_batch_ui.py`, `tests/test_auto_batch_end_to_end.py`, and `tests/test_input_integrity.py`.
- Update README, user manual, method notes, developer notes and CHANGELOG.

### Task 1: XLSX Metadata and Atomic Result Package Lifecycle

**Files:**
- Modify: `requirements.txt`
- Modify: `app/core/batch_inputs.py`
- Extend: `tests/test_batch_inputs.py`
- Create: `app/core/auto_batch_export.py`
- Test: `tests/test_auto_batch_export.py`

**Interfaces:**
- Produces: `ResultPackagePaths`, `create_staging_package()`, `write_manifest()`, `mark_incomplete()`, `finalize_package()`.

- [ ] **Step 1: Add `openpyxl` to requirements**

Append exactly:

```text
openpyxl
```

Do not install it silently. First run `python -c "import openpyxl; print(openpyxl.__version__)"`; if missing, request user approval before `python -m pip install -r requirements.txt`.

- [ ] **Step 2: Add a failing XLSX metadata test**

```python
def test_xlsx_metadata_is_loaded_after_openpyxl_is_declared(tmp_path):
    path = tmp_path / "metadata.xlsx"
    pd.DataFrame([{"source_file": "frame_001.csv", "time_s": 1.0}]).to_excel(path, index=False)
    table = load_metadata_table(path)
    assert table.to_dict("records") == [{"source_file": "frame_001.csv", "time_s": 1.0}]
```

- [ ] **Step 3: Run the metadata test and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py::test_xlsx_metadata_is_loaded_after_openpyxl_is_declared`.

Expected: failure with `Unsupported metadata file before Plan 4: .xlsx`.

- [ ] **Step 4: Extend metadata loading explicitly**

```python
def load_metadata_table(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source)
    if source.suffix.lower() in {".xlsx", ".xlsm"}:
        return pd.read_excel(source, engine="openpyxl")
    raise ValueError(f"Unsupported metadata file: {source.suffix}")
```

- [ ] **Step 5: Run metadata tests and verify GREEN**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py`. Expected: all tests pass.

- [ ] **Step 6: Write failing package-lifecycle tests**

```python
from pathlib import Path

import pytest

from app.core.auto_batch_export import create_staging_package, finalize_package, mark_incomplete


def test_finalize_creates_new_timestamped_directory_without_overwrite(tmp_path: Path):
    package = create_staging_package(tmp_path, "series", timestamp="20260711_120000")
    (package.staging_dir / "manifest.json").write_text("{}", encoding="utf-8")
    final = finalize_package(package)
    assert final.name == "series_20260711_120000"
    assert (final / "manifest.json").exists()
    with pytest.raises(FileExistsError):
        create_staging_package(tmp_path, "series", timestamp="20260711_120000")


def test_incomplete_package_is_preserved_and_marked(tmp_path: Path):
    package = create_staging_package(tmp_path, "series", timestamp="20260711_120001")
    target = mark_incomplete(package, reason="cancelled")
    assert target.name.endswith("_incomplete")
    assert (target / "INCOMPLETE.json").exists()
```

- [ ] **Step 7: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_export.py`.

- [ ] **Step 8: Implement same-filesystem staging and finalization**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class ResultPackagePaths:
    root: Path
    staging_dir: Path
    final_dir: Path
    tables_dir: Path
    fits_dir: Path
    figures_dir: Path


def create_staging_package(output_root, batch_id, *, timestamp=None):
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir = root / f"{batch_id}_{stamp}"
    if final_dir.exists() or (root / f"{batch_id}_{stamp}_incomplete").exists():
        raise FileExistsError(final_dir)
    staging = root / f".{batch_id}_{stamp}_{uuid4().hex}.staging"
    tables, fits, figures = staging / "tables", staging / "fits", staging / "figures"
    for folder in (tables, fits, figures):
        folder.mkdir(parents=True, exist_ok=False)
    return ResultPackagePaths(root, staging, final_dir, tables, fits, figures)


def finalize_package(package):
    if not (package.staging_dir / "manifest.json").exists():
        raise ValueError("manifest.json is required before finalization")
    return package.staging_dir.replace(package.final_dir)


def mark_incomplete(package, *, reason):
    (package.staging_dir / "INCOMPLETE.json").write_text(json.dumps({"reason": reason}, ensure_ascii=False, indent=2), encoding="utf-8")
    target = package.final_dir.with_name(package.final_dir.name + "_incomplete")
    return package.staging_dir.replace(target)
```

- [ ] **Step 9: Run lifecycle tests**

Run the Step 7 command. Expected: all lifecycle tests pass.

### Task 2: Complete CSV, JSON, Manifest and Figure Artifacts

**Files:**
- Modify: `app/core/auto_batch_export.py`
- Create: `app/core/auto_batch_figures.py`
- Test: `tests/test_auto_batch_export.py`

**Interfaces:**
- Produces: `write_detail_tables(run, package)`, `write_fit_artifacts(run, package)`, `write_run_log(run, package)`, `export_all_figures(run, package)`, `export_auto_batch_run(run, output_root) -> Path`.

- [ ] **Step 1: Write failing artifact completeness test**

```python
def test_complete_artifact_tree(auto_batch_run_complete, tmp_path):
    package = create_staging_package(tmp_path, "series", timestamp="20260711_120002")
    write_detail_tables(auto_batch_run_complete, package)
    write_fit_artifacts(auto_batch_run_complete, package)
    write_manifest(auto_batch_run_complete, package)
    assert (package.tables_dir / "curve_metrics_long.csv").exists()
    assert (package.tables_dir / "analysis_parameters.csv").exists()
    assert (package.tables_dir / "fit_quality.csv").exists()
    assert (package.tables_dir / "model_parameters.csv").exists()
    assert (package.tables_dir / "model_ranking.csv").exists()
    assert list(package.fits_dir.rglob("result.json"))
    assert list(package.fits_dir.rglob("residuals.csv"))
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_export.py`.

- [ ] **Step 3: Implement authoritative long-table flatteners**

Write one row per parameter and one row per fit-quality record. Include curve/frame/method/model IDs, q range, value, unit, status, invalid reason, reliability and artifact path. Serialize numpy values through an explicit JSON converter; never stringify numeric CSV cells.

- [ ] **Step 4: Write per-fit directories and figures**

For every fit create `fits/<safe_frame>/<safe_analysis_or_model>/` containing `result.json`, `fit_points.csv`, `residuals.csv`, `covariance.csv`, `correlation.csv`, `fit.png`, and `residuals.png`. Sanitize path segments and retain original names in JSON.

- [ ] **Step 5: Build manifest and run log**

Manifest includes run/config IDs, software version, input hashes, batch status, counts, consensus regions, main model, transition flags and every output path relative to package root. `run_log.md` records objective facts and failures without action-guidance text.

- [ ] **Step 6: Implement the single package-export entry point**

```python
def export_auto_batch_run(run, output_root) -> Path:
    package = create_staging_package(output_root, run.batch_id)
    try:
        write_detail_tables(run, package)
        write_fit_artifacts(run, package)
        export_all_figures(run, package)
        write_summary_workbook(run, package)
        write_run_log(run, package)
        write_manifest(run, package)
        if run.status == "cancelled":
            return mark_incomplete(package, reason="cancelled")
        return finalize_package(package)
    except Exception as exc:
        if package.staging_dir.exists():
            mark_incomplete(package, reason=f"export_failed: {exc}")
        raise
```

All paths written to tables/manifest are relative to `package.staging_dir`, so they remain valid after the directory rename.

- [ ] **Step 7: Run focused export and figure tests**

Run `$env:MPLBACKEND='Agg'; python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_export.py tests\test_figure_export.py tests\test_sequence_figures.py`.

Expected: all tests pass.

### Task 3: Sixteen-Sheet Summary Workbook

**Files:**
- Modify: `app/core/auto_batch_export.py`
- Test: `tests/test_auto_batch_excel.py`

**Interfaces:**
- Produces: `write_summary_workbook(run, package) -> Path`.

- [ ] **Step 1: Write failing workbook-contract test**

```python
from openpyxl import load_workbook


EXPECTED_SHEETS = [
    "00_ReadMe", "01_Frame_Summary", "02_Metrics_Long", "03_Analysis_Parameters",
    "04_Fit_Quality", "05_Model_Parameters", "06_Parameter_Covariance",
    "07_Model_Ranking", "08_Peaks_Oscillations", "09_Integrals",
    "10_Sequence_Trends", "11_Uncertainty", "12_Advanced_Conditional",
    "13_QC_Failures", "14_Metadata", "15_Run_Config",
]


def test_workbook_has_exact_contract(auto_batch_run_complete, tmp_path):
    package = create_staging_package(tmp_path, "series", timestamp="20260711_120003")
    path = write_summary_workbook(auto_batch_run_complete, package)
    workbook = load_workbook(path, read_only=True, data_only=True)
    assert workbook.sheetnames == EXPECTED_SHEETS
    headers = [cell.value for cell in next(workbook["03_Analysis_Parameters"].iter_rows())]
    assert {"curve_id", "analysis_type", "parameter_name", "value", "unit", "status", "invalid_reason", "q_start", "q_end"} <= set(headers)
```

- [ ] **Step 2: Run and verify RED**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_excel.py`.

- [ ] **Step 3: Implement workbook dataframes and exact sheet order**

Build all 16 DataFrames before opening `pd.ExcelWriter(engine="openpyxl")`. Empty sheets still receive their required headers. `01_Frame_Summary` is wide and convenient; all other authoritative result tables are long.

- [ ] **Step 4: Enforce numeric types and Excel row limits**

Do not concatenate units into values. Replace non-finite floats with blank cells. If a table exceeds 1,048,575 data rows, write a compact sheet containing row count, CSV relative path and SHA256; keep the complete table in CSV.

- [ ] **Step 5: Add restrained formatting**

Freeze top rows, enable filters, bold headers, set readable widths, color status cells consistently, and add hyperlinks to relative artifacts. Do not add formulas that change scientific values.

- [ ] **Step 6: Run workbook and round-trip tests**

Run `python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_excel.py`.

Expected: exact sheet order, fields, numeric types and hyperlinks pass.

### Task 4: GUI Form and Safe Worker Thread

**Files:**
- Create: `app/ui/auto_batch_worker.py`, `app/ui/auto_batch_tab.py`
- Modify: `app/ui/advanced_workspace_tab.py`, `app/ui/main_window.py`
- Test: `tests/test_auto_batch_worker.py`, `tests/test_auto_batch_ui.py`

**Interfaces:**
- `AutoBatchWorker` signals: `progress(dict)`, `completed(str)`, `failed(str)`, `cancelled(str)`.
- `AutoBatchTab` exposes input/output selectors, batch/sample/model settings, preview, start/cancel controls and factual output log.

- [ ] **Step 1: Write failing UI structure tests**

```python
def test_main_window_exposes_one_click_auto_batch_tab():
    window = MainWindow()
    try:
        assert hasattr(window, "auto_batch_tab")
        names = [window.advanced_workspace_tab.tabs.tabText(i) for i in range(window.advanced_workspace_tab.tabs.count())]
        assert "一键自动分析" in names
        assert window.auto_batch_tab.start_button.isEnabled()
        assert not window.auto_batch_tab.cancel_button.isEnabled()
    finally:
        window.close()


def test_config_is_created_once_for_whole_batch(auto_batch_tab, tmp_path):
    auto_batch_tab.input_path.setText(str(tmp_path))
    auto_batch_tab.batch_id.setText("series")
    auto_batch_tab.sample_type.setCurrentText("particle")
    config = auto_batch_tab.build_config()
    assert config.batch_id == "series"
    assert config.sample_type == "particle"
```

- [ ] **Step 2: Run and verify RED**

Run `$env:QT_QPA_PLATFORM='offscreen'; python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_ui.py`.

- [ ] **Step 3: Implement the focused tab**

The tab contains: input directory, optional metadata file, output root, batch ID, sample type, q/I units, checkable allowed-model list, conditional prerequisites, preview button, start button, cancel button, progress bar, current operation label and read-only factual log. Use existing `action_button()` and `apply_help()`.

- [ ] **Step 4: Implement QObject worker and cancellation token**

```python
class AutoBatchWorker(QObject):
    progress = Signal(dict)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal(str)

    def __init__(self, input_dir, output_root, config):
        super().__init__()
        self.input_dir = input_dir
        self.output_root = output_root
        self.config = config
        self._cancel = False

    @Slot()
    def run(self):
        try:
            run = run_auto_batch(self.input_dir, self.config, progress_callback=lambda event: self.progress.emit(asdict(event)), cancel_requested=lambda: self._cancel)
            path = export_auto_batch_run(run, self.output_root)
            (self.cancelled if run.status == "cancelled" else self.completed).emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def cancel(self):
        self._cancel = True
```

- [ ] **Step 5: Wire worker lifecycle and state restoration**

Move worker to `QThread`; disable configuration/start while running; enable cancel; always stop/delete thread and restore controls on completed/failed/cancelled. Display the final path as a selectable string; do not automatically open external programs.

- [ ] **Step 6: Run UI and existing style/safety tests**

Run `$env:QT_QPA_PLATFORM='offscreen'; python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_worker.py tests\test_auto_batch_ui.py tests\test_ui_style.py tests\test_ui_safety.py`.

Expected: all tests pass.

### Task 5: End-to-End Contract and Input Integrity

**Files:**
- Create: `tests/test_auto_batch_end_to_end.py`, `tests/test_input_integrity.py`

**Interfaces:**
- Tests the complete `input folder -> AutoBatchRun -> result package` workflow.

- [ ] **Step 1: Build small deterministic fixtures**

Create test-generated calibrated q-I curves for at least three frames with optional error and metadata CSV. Generate them inside `tmp_path`; do not add experimental data to the repository.

- [ ] **Step 2: Write the end-to-end assertion**

```python
def test_end_to_end_creates_complete_package(in_situ_fixture_dir, tmp_path):
    config = AutoBatchConfig(batch_id="series", sample_type="particle", allowed_models=["sphere", "ellipsoid"])
    run = run_auto_batch(in_situ_fixture_dir, config)
    final = export_auto_batch_run(run, tmp_path / "results")
    assert (final / "analysis_summary.xlsx").exists()
    assert (final / "manifest.json").exists()
    assert (final / "tables" / "model_parameters.csv").exists()
    assert len(list((final / "fits").rglob("residuals.csv"))) >= 6
```

- [ ] **Step 3: Write input hash integrity assertion**

Hash every input before and after run/export and assert equality. Also assert no new file appears inside the input directory.

- [ ] **Step 4: Add partial failure and cancellation scenarios**

Include one malformed file and one forced model failure. Assert batch `partial_success`, valid curves remain exported, failure sheet has reasons, and no false zero parameters appear. Cancel a run and assert `_incomplete` output plus `cancelled` status.

- [ ] **Step 5: Run end-to-end tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_end_to_end.py tests\test_input_integrity.py
```

Expected: all tests pass.

### Task 6: User Documentation, Changelog and Final Verification

**Files:**
- Modify: `README.md`, `docs/user_manual_zh.md`, `docs/method_notes.md`, `docs/advanced_methods.md`, `docs/developer_notes.md`, `CHANGELOG.md`

- [ ] **Step 1: Document beginner workflow and outputs**

Explain purpose, input files, optional metadata, batch settings, start/cancel, output directory, 16 workbook sheets, success/partial-success judgement, invalid blank values, and how to trace fit/residual files.

- [ ] **Step 2: Document scientific boundaries**

State that model ranking is not structure proof; P(r), correlation, absolute quantities, kinetics, PCA and clustering are conditional/exploratory; input must already be corrected/calibrated.

- [ ] **Step 3: Append the final mandatory CHANGELOG record**

Include every file, reason, run command, outputs, checks, risks, raw-data safety, dependency change, and no package/commit/push.

- [ ] **Step 4: Run compile and complete tests**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m compileall -q main.py app\core app\ui
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_export.py tests\test_auto_batch_excel.py tests\test_auto_batch_worker.py tests\test_auto_batch_ui.py tests\test_auto_batch_end_to_end.py tests\test_input_integrity.py
python -B -m pytest -q -p no:cacheprovider
git diff --check
```

Expected: compile, focused tests, full tests and whitespace checks pass.

- [ ] **Step 5: Perform a manual GUI smoke check**

Run `python main.py`, select generated non-private fixture curves, execute the one-click workflow, and verify the progress display and final path. Do not use unpublished experimental data for the smoke test.

- [ ] **Step 6: Handoff without packaging or Git mutation**

Report modified files, exact test results, launch command, input/output conventions, success criteria and known limitations. Show `git status --short`. Do not commit, push or package unless the user separately requests it.
