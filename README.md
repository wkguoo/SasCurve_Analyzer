# sas_curve_analyzer

[English](#english) | [简体中文](#简体中文)

![status](https://img.shields.io/badge/status-active-brightgreen)
![python](https://img.shields.io/badge/python-3.x-blue)
![platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![license](https://img.shields.io/badge/license-MIT-green)

## English

## Overview

`sas_curve_analyzer` is a local desktop application for importing, checking, visualizing, comparing, and reporting calibrated one-dimensional small-angle scattering curves.

The software is intended for materials researchers working with reduced 1D SAXS/SANS/WAXS-SAXS curve files. It focuses on practical curve inspection, non-destructive data handling, model-free feature extraction, batch comparison, and traceable reporting.

## Scope

Supported input data:

- One-dimensional curves that have already been reduced and calibrated.
- Files containing at least q and I(q) columns.
- Optional error, sigma, err, std, or uncertainty columns.
- Text-based `.csv`, `.txt`, and `.dat` files with comma, tab, or whitespace separation.

This software does not perform:

- Intensity correction.
- Background subtraction.
- Transmission correction.
- Thickness correction.
- Exposure-time normalization.
- Absolute intensity calibration.
- Two-dimensional detector image integration.
- Complex structural model fitting.
- Automatic material structure identification.

## Features

### Data Import And Validation

- Import `.csv`, `.txt`, and `.dat` curve files.
- Skip comment lines beginning with `#`, `;`, or `//`.
- Detect common separators automatically.
- Treat error/sigma columns as optional.
- Automatically recognize common columns such as `q_A_inv` and `intensity_cm_inv`.
- Preview selected files before import, including first rows, inferred columns, q/I ranges, NaN counts, duplicate q, non-positive q/intensity, and error-column issues.
- Check q ordering, duplicate q values, NaN values, slight/significant negative intensity values, zero intensity values, and invalid error values.

### Batch Import For In Situ Series

The application supports importing a numbered sequence of 1D curve files, for example:

```text
ti15_00001_abs2d_cm-1.csv
ti15_00002_abs2d_cm-1.csv
ti15_00003_abs2d_cm-1.csv
```

Batch import uses natural sorting, so frame 10 is imported after frame 9 rather than after frame 1. File names such as `ti15_00001_abs2d_cm-1.csv` are parsed into frame metadata:

- `series_id`: `ti15`
- `frame_label`: `00001`
- `frame_index`: `1`
- `sequence_order`: import order after sorting

For files with `q_A_inv,intensity_cm_inv`, the q unit is inferred as `A^-1`, the intensity unit is inferred as `cm^-1`, and missing error/sigma columns are accepted. Imported frame metadata can be used by downstream comparison and reporting workflows.

### Non-Destructive Data Handling

- q unit conversion between `A^-1` and `nm^-1` creates a new curve.
- Batch averaging creates a new curve.
- Original imported data are not modified.
- Curve-level processing history and project-level operation history are recorded separately.

### Visualization

- Linear, semi-log, log-log/power-law, Guinier, Kratky, Porod, invariant-integrand, log-q contribution, local-slope, and peak/d-spacing plots.
- Error bars when an error column is available.
- Manual X/Y axis limits and quick full/low/mid/high q range buttons.
- Cursor readout for the current plot coordinate, including derived q/I values for transformed views.
- The coordinate readout is shown as its own row, so longer transformed-coordinate text does not compress range controls.
- Linked navigation from supported plot views to the corresponding model-free analysis.
- Optional approximate real-space scale axis using `d = 2π/q` on raw-q plots.
- Safe filtering for logarithmic plots, including `I(q) <= 0` and `q <= 0` where required.
- Figure export presets for screen preview, presentation, and draft-publication outputs.

### Model-Free Analysis

- Guinier analysis.
- Power-law slope analysis.
- Local slope calculation.
- Peak and shoulder detection.
- Finite q-range invariant.
- Kratky representation metrics.
- Porod representation metrics.
- Linked navigation back to the matching plot view for the selected analysis.
- Conversion of the current plotting x-axis range back to a positive raw q analysis range.
- Preflight q-range checks before analysis, including point counts, finite/log-usable points, non-positive q/intensity filtering, and next-action guidance.

Each analysis returns an `AnalysisResult` with the q range, parameters, numerical results, text warnings, structured method warnings, timestamp, and input curve version.

### Batch Comparison

- Create curve groups from selected curves.
- Average selected replicate curves.
- Compare selected curve A and curve B with difference, ratio, or relative difference.
- Sequence management table for reviewing import order, frame metadata, q ranges, point counts, and warnings.
- Export `sequence_index.csv` for in situ/time-series audit.
- Use interpolation on a common q grid when curves do not share the same q grid.
- Display normalization is for shape comparison only and does not alter original intensity data.

### Records And Reporting

- Project menu actions for creating, opening, saving, and saving-as project folders.
- Dirty-state tracking with a title-bar marker and close-time unsaved-change confirmation.
- Project-level history records for import, q unit conversion, analysis, group creation, averaging, comparison, export, project save, and formal-record actions.
- Formal records for selected curves, analysis results, and comparison results.
- Common import, analysis, export, figure-export, and project lifecycle failures use fact-only layered messages with status, observed facts, original-data safety, and technical details.
- Export curve CSV files, analysis JSON/CSV files, feature tables, figures, Markdown reports, and project folders.
- Project-internal curve data are saved as JSON files.

### Advanced And Experimental Interfaces

- Experimental P(r) interface reserved for future validated indirect Fourier transform support.
- Reserved correlation-function interface.
- Reserved low-q and high-q extrapolation interfaces, disabled by default.
- Plugin base classes for adding analysis extensions.
- Settings-accessible model/formula catalog covering plotting views, model-free methods, shape/form-factor models, empirical models, P(r), correlation, and extrapolation interfaces.

Experimental and reserved interfaces should not be used as sources of formal quantitative physical conclusions.

## Installation

From the project root:

```powershell
python -m pip install -r requirements.txt
```

Required packages are listed in `requirements.txt`.

## Quick Start

Launch the desktop application:

```powershell
python main.py
```

Minimal workflow:

1. Open the `Data Import` tab.
2. Select a `.csv`, `.txt`, or `.dat` curve file.
3. Confirm the q, intensity, and optional error/sigma columns.
4. Import the curve.
5. Inspect validation warnings, plot the curve, and run model-free analyses.
6. Use the `Settings` menu to view the active settings, settings file path, load status, and method/formula assumptions.

## User Manual

For a beginner-friendly Chinese walkthrough, see [`docs/user_manual_zh.md`](docs/user_manual_zh.md). It covers data preparation, each GUI tab, q-range selection, plotting, model-free analysis, batch comparison, exports, troubleshooting, terminology, and method limitations.

## Input Data Format

Example with an error column:

```csv
q,I,error
0.010,980.1987,19.6039
0.012,971.6108,19.4322
```

Example without an error column:

```csv
q_A_inv,intensity_cm_inv
0.010,980.1987
0.012,971.6108
```

Column names are matched case-insensitively for common q, intensity, and error/sigma aliases. If automatic recognition fails, the GUI allows manual column names.

## Analysis Methods

### Guinier Analysis

Fits `ln I(q)` against `q²` in a selected low-q interval and reports Rg, I(0), fit statistics, and residuals. It does not prove particle shape or monodispersity, and it warns when the fitted interval violates common Guinier assumptions such as high `qRg`.

### Power-Law Slope

Fits `ln I(q)` against `ln q` and reports the exponent `α`. The exponent can suggest Porod-like, fractal-like, or rough-interface behavior, but it is not a unique structural diagnosis.

### Local Slope

Computes `α(q) = -d ln I / d ln q` to help inspect whether a selected q interval behaves like a stable power law.

### Peak And Shoulder Detection

Reports peak position, intensity, width, area, and `d = 2π/q*`. This `d` value is a characteristic length or correlation distance, not an automatic particle diameter.

### Finite q-Range Invariant

Computes the measured-range integral `∫q²I(q)dq`. It does not extrapolate to q = 0 or q = infinity and does not automatically convert to volume fraction.

### Kratky Representation

Reports descriptive metrics from `q²I(q)`, including the maximum position when present. Interpretation depends on material class and scattering assumptions.

### Porod Representation

Reports descriptive `q⁴I(q)` plateau statistics. Without contrast, phase assumptions, and a stable high-q range, it does not calculate absolute specific surface area.

## Project Files And Outputs

A saved project folder contains:

- `project.json` with project metadata, groups, analyses, comparisons, history, and formal records.
- `curves/*.json` files with internal curve q, intensity, and optional error arrays.

Use the `项目` menu to create a new project, open an existing project folder, save the current project, or save it to another folder. Unsaved changes are marked with `*` in the window title and trigger a confirmation prompt before closing the visible main window.

User-facing exports include:

- Curve CSV files.
- Origin-ready batch curve exports:
  - `curves_long.csv`: one row per q-I point with in situ frame metadata.
  - `curves_long_guide.md`: beginner guide explaining long-table columns, plotting choices, interpretation checks, and analysis caveats.
  - `curves_matrix.csv`: q plus one intensity column per frame when q grids match.
- Analysis JSON/CSV files.
- Comparison CSV files.
- Feature tables.
- Figures.
- Markdown reports.
- Complete analysis bundle metadata:
  - `manifest.json`: software, inputs, analyses, outputs, warnings, settings snapshot link, and project counts.
  - `README_export.md`: exported-file guide and review notes.
  - `settings_snapshot.json`: export-time application settings.
  - `bundle_warnings.txt`: bundle-level warnings, including skipped optional outputs.

## Method Limitations

- Logarithmic plots and fits exclude invalid q or intensity points and report warnings.
- Slightly negative calibrated intensities are preserved and can be shown in linear or non-log transformed plots. They are classified separately from significant negative values; non-positive points are still excluded from logarithmic plots and log-based analyses.
- Slight-negative classification can be configured in Settings with an enable switch, a relative abs-ratio threshold, and a negative-point fraction threshold. Wider thresholds can hide data-quality problems, so they should be reported with the analysis.
- Plot axis limits are display-only controls and do not change imported curve data.
- Analysis `q_min/q_max` values are raw physical q ranges. Negative display coordinates such as `ln q < 0` can be converted back to positive raw q before analysis, but negative raw q is not accepted.
- Missing error columns are allowed; unweighted fitting is used where relevant.
- Finite invariant values are measured-range descriptors unless explicit extrapolation and contrast assumptions are supplied externally.
- Porod metrics are descriptive unless the user supplies the physical assumptions needed for absolute surface calculations.
- Normalization is for display and shape comparison by default; it is not an intensity correction.
- Experimental P(r), correlation-function, and extrapolation interfaces are not validated production analysis methods.

## Development And Testing

Run tests from the project root:

```powershell
python -m pytest
```

Optional compile check:

```powershell
python -m py_compile main.py app\core\*.py app\ui\*.py
```

The GUI code should call `app/core` modules for numerical work. New analysis behavior should be covered by focused tests.

## 简体中文

`sas_curve_analyzer` 是一个本地 Windows 桌面工具，用于导入、检查、绘制、比较和导出已经完成一维归约与校准的小角散射曲线。

### 主要功能

- 导入 `.csv`、`.txt`、`.dat` 中的 q-I(q) 曲线，可选误差列。
- 导入前可预览前几行并诊断列名、q/I 范围、NaN、重复 q、非正 q/强度和 error 异常。
- 检查 q 顺序、重复 q、NaN、零强度、轻微/显著负强度和误差列异常。
- 提供 linear、semi-log、log-log、Guinier、Kratky、Porod、invariant、local-slope、peak/d-spacing 等常用图。
- 支持手动坐标范围、低/中/高 q 快捷视图、独立成行的鼠标坐标读数和 `d = 2*pi/q` 辅助轴。
- 绘图页支持屏幕预览、组会汇报、论文初稿三种图像导出预设。
- 支持 Guinier、power-law、local slope、peak、finite invariant、Kratky、Porod 等无模型分析，并可在绘图页和分析页之间一键联动；绘图页 display x 范围会先裁剪到当前曲线有效数据范围，再换算为 raw q；分析前会进行 q 范围预检。
- 支持批量曲线比较、Origin 友好导出、Markdown 报告和项目记录。
- 批量页提供序列管理表和 `sequence_index.csv` 导出，便于复核原位/时间序列导入顺序、frame、q 范围和 warning。
- 支持通过 `项目` 菜单新建、打开、保存和另存为项目；未保存更改会在窗口标题中显示 `*`，关闭/新建/打开前可选择保存、不保存或取消。

### 快速开始

```powershell
python -m pip install -r requirements.txt
python main.py
```

基本流程：在 `Data Import` 中导入曲线，检查数据质量，在绘图页查看曲线，并按需要运行无模型分析或导出报告。

### 使用手册

完整中文新手手册见 [`docs/user_manual_zh.md`](docs/user_manual_zh.md)，内容包括数据准备、界面功能、q 范围选择、绘图、无模型分析、批量比较、导出、排错、术语表和方法边界。

### 注意事项

- 软件不做原始二维图像积分、背景扣除、透过率校正、厚度校正或绝对强度校准。
- 原始导入数据不会被直接修改，派生处理会生成新的曲线或输出文件。
- 轻微负强度可保留并单独标注，但 log 图和 log 分析仍会排除 `I(q) <= 0`。
- 分析页的 `q_min/q_max` 始终表示原始物理 q 范围；`ln q` 等图上负横坐标需要先换算回正的 raw q。
- `d = 2*pi/q` 或 `d = 2*pi/q*` 表示特征尺度/相关距离，不自动等于颗粒直径。
- P(r)、correlation 和 extrapolation 当前属于实验或预留接口，不应直接作为正式物理结论。

## License / Citation / Contact

License: MIT License. See LICENSE.

Citation guidance: to be added.

Contact: to be added.
