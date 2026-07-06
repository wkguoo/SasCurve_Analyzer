# sas_curve_analyzer

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
- Check q ordering, duplicate q values, NaN values, non-positive intensity values, and invalid error values.

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

- Linear, semilog, loglog, Guinier, Kratky, Porod, invariant, and local-slope plots.
- Error bars when an error column is available.
- Safe filtering for logarithmic plots, including `I(q) <= 0` and `q <= 0` where required.

### Model-Free Analysis

- Guinier analysis.
- Power-law slope analysis.
- Local slope calculation.
- Peak and shoulder detection.
- Finite q-range invariant.
- Kratky representation metrics.
- Porod representation metrics.

Each analysis returns an `AnalysisResult` with the q range, parameters, numerical results, text warnings, structured method warnings, timestamp, and input curve version.

### Batch Comparison

- Create curve groups from selected curves.
- Average selected replicate curves.
- Compare selected curve A and curve B with difference, ratio, or relative difference.
- Use interpolation on a common q grid when curves do not share the same q grid.
- Display normalization is for shape comparison only and does not alter original intensity data.

### Records And Reporting

- Project-level history records for import, q unit conversion, analysis, group creation, averaging, comparison, export, project save, and formal-record actions.
- Formal records for selected curves, analysis results, and comparison results.
- Export curve CSV files, analysis JSON/CSV files, feature tables, figures, Markdown reports, and project folders.
- Project-internal curve data are saved as JSON files.

### Advanced And Experimental Interfaces

- Experimental P(r) interface reserved for future validated indirect Fourier transform support.
- Reserved correlation-function interface.
- Reserved low-q and high-q extrapolation interfaces, disabled by default.
- Plugin base classes for adding analysis extensions.

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

Fits `ln I(q)` against `q^2` in a selected low-q interval and reports Rg, I(0), fit statistics, and residuals. It does not prove particle shape or monodispersity, and it warns when the fitted interval violates common Guinier assumptions such as high `qRg`.

### Power-Law Slope

Fits `ln I(q)` against `ln q` and reports the exponent `alpha`. The exponent can suggest Porod-like, fractal-like, or rough-interface behavior, but it is not a unique structural diagnosis.

### Local Slope

Computes `alpha(q) = -d ln I / d ln q` to help inspect whether a selected q interval behaves like a stable power law.

### Peak And Shoulder Detection

Reports peak position, intensity, width, area, and `d = 2*pi/q*`. This `d` value is a characteristic length or correlation distance, not an automatic particle diameter.

### Finite q-Range Invariant

Computes the measured-range integral `integral(q^2 I(q) dq)`. It does not extrapolate to q = 0 or q = infinity and does not automatically convert to volume fraction.

### Kratky Representation

Reports descriptive metrics from `q^2 I(q)`, including the maximum position when present. Interpretation depends on material class and scattering assumptions.

### Porod Representation

Reports descriptive `q^4 I(q)` plateau statistics. Without contrast, phase assumptions, and a stable high-q range, it does not calculate absolute specific surface area.

## Project Files And Outputs

A saved project folder contains:

- `project.json` with project metadata, groups, analyses, comparisons, history, and formal records.
- `curves/*.json` files with internal curve q, intensity, and optional error arrays.

User-facing exports include:

- Curve CSV files.
- Analysis JSON/CSV files.
- Comparison CSV files.
- Feature tables.
- Figures.
- Markdown reports.

## Method Limitations

- Logarithmic plots and fits exclude invalid q or intensity points and report warnings.
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

## License / Citation / Contact

License: to be added.

Citation guidance: to be added.

Contact: to be added.
