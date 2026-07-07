# Method Notes

This document describes the numerical methods and interpretation boundaries used by `sas_curve_analyzer`.

## Input Assumptions

The software operates on one-dimensional small-angle scattering curves that have already been reduced and calibrated outside this application. It does not perform intensity correction, background subtraction, transmission correction, thickness correction, exposure-time normalization, absolute calibration, or 2D detector integration.

Each input curve should contain q and I(q). Error or sigma columns are optional. Missing error data are accepted; analysis functions that can use uncertainty fall back to ordinary least squares when no valid error column is available.

## Data Validation

Validation checks:

- Monotonic q ordering.
- Duplicate q values.
- NaN q or intensity values.
- Slight negative, significant negative, or zero intensity values.
- NaN, negative, or zero error values.

Validation reports warnings only. The software does not edit imported experimental files.

Slightly negative calibrated intensities are allowed and preserved. They can occur after background subtraction, blank correction, or absolute-scale calibration. The validator separates slight negative values from significant negative values using relative magnitude and fraction thresholds. Linear plots and non-log transformed plots can display them, but logarithmic plots and log-based analyses exclude all non-positive intensities and report warnings.

The slight-negative behavior is configurable through `AppSettings`: `allow_slight_negative_intensity`, `slight_negative_abs_ratio_threshold`, and `slight_negative_fraction_threshold`. These settings change validation classification only. They do not modify intensity values and do not allow `I(q) <= 0` into logarithmic analysis.

## q Unit Conversion

Supported q unit conversion:

- `A^-1` to `nm^-1`: q is multiplied by 10.
- `nm^-1` to `A^-1`: q is multiplied by 0.1.

Intensity units are not converted or scaled by q unit conversion. Conversion creates a new `CurveData` object and records curve-level processing history plus project-level operation history in the GUI.

## Plotting

Supported plot types include linear `I(q) vs q`, semi-log `ln I(q) vs q`, log-log/power-law `ln I(q) vs ln q`, Guinier `ln I(q) vs q²`, Kratky `q²I(q) vs q`, Porod `q⁴I(q) vs q`, invariant-integrand `q²I(q) vs q`, log-q contribution `q³I(q) vs ln q`, local slope `α(q) vs q`, and peak/d-spacing `I(q) vs q` with `d = 2π/q*` annotation.

Semilog, loglog, and Guinier plots filter `I(q) <= 0` before applying logarithms. Loglog, Guinier, and q³I invariant-contribution plots filter `q <= 0` where the transform requires positive q. Filtering returns warnings rather than raising numerical runtime warnings.

When error bars are shown on log-intensity plots, the propagated error is `sigma_lnI = sigma_I / I`. Invalid propagated errors are hidden and reported as warnings.

Manual X/Y axis limits and quick full/low/mid/high q buttons only change the displayed axes. They do not modify `CurveData`, saved data, or analysis ranges. For transformed views, the X range is in display coordinates: q² for Guinier and ln q for log-log or log-q contribution plots. Cursor readout reports display coordinates and, where useful, approximate back-transformed q/I values.

The optional top axis `d = 2π/q` is available only when the plot X-axis is raw q. This d value is an approximate characteristic scale or correlation distance, not a particle diameter.

## Guinier Analysis

Guinier analysis fits:

```text
ln I(q) = ln I(0) - Rg² q² / 3
```

Outputs include Rg, I(0), slope, intercept, R2, adjusted R2, reduced chi-square, residuals, standardized residuals when available, fit point count, and qRg range.

Important limits:

- The selected q interval must be physically appropriate.
- A non-negative slope does not give a valid Rg.
- High `qRg_max` indicates the interval may be outside the usual Guinier limit.
- Good R2 alone does not prove the chosen interval is physically valid.

## Power-Law Slope

Power-law analysis fits:

```text
ln I(q) = ln prefactor - alpha ln q
```

The output exponent `alpha` is descriptive. It can suggest Porod-like, mass-fractal-like, or surface-fractal-like behavior, but it does not uniquely determine structure without material context and q-range justification.

## Local Slope

Local slope is computed as:

```text
α(q) = -d ln I / d ln q
```

It is useful for checking whether a power-law interval is stable. Plateau candidates are hints for inspection, not automatic model selection.

## Peak Detection

Peak detection uses the 1D intensity curve and reports peak q, peak intensity, FWHM, area, and:

```text
d = 2π/q*
```

This d value is a characteristic length or correlation distance. It is not automatically a particle diameter.

## Finite q-Range Invariant

The measured invariant is:

```text
Q_measured = ∫q²I(q)dq
```

It is a finite measured q-range integral. The software does not apply low-q or high-q extrapolation and does not convert the value to volume fraction.

For scale contribution, the information-budget analysis uses:

```text
Q_measured = ∫q³I(q)d ln q
```

It reports q³I versus ln q, cumulative Q, Q10/Q50/Q90 q positions, `d_Q50 = 2π/q_Q50`, dominant q/d scale, normalized contribution entropy, low/mid/high contribution fractions, and selected-range observable d limits. These outputs describe where measured invariant signal sits inside the selected finite q range; they are not a substitute for extrapolated total invariant analysis.

## Kratky And Porod Metrics

Kratky metrics are descriptive values from `q²I(q)`. Porod metrics are descriptive statistics from `q⁴I(q)`.

Porod plateau metrics should not be interpreted as absolute specific surface area without contrast, phase, and high-q plateau assumptions.

## Method Warnings

Analysis results include both legacy text warnings and `structured_warnings`. Structured warnings contain:

- `warning_code`
- `severity`
- `message`
- `suggested_action`
- `related_analysis_id`

The GUI and exported reports can display warning codes alongside the human-readable messages. Warnings are part of the analysis result and are saved with the project and JSON exports.

## Model Catalog Coverage

The model/formula catalog is a transparency aid, not a proof that a model applies. It covers common plotting views, model-free analyses, shape/form-factor models, empirical or model-dependent descriptions, the experimental P(r) interface, the reserved correlation-function interface, and low-q/high-q extrapolation interfaces. Each entry should state formula, inputs, outputs, assumptions, limitations, and status.

## Records And Traceability

The application distinguishes:

- `CurveData.processing_history`: provenance of derived curve objects.
- `ProjectState.history_records`: project-level operation log for import, unit conversion, analysis, group creation, averaging, comparison, export, project save, and formal-record actions.

Formal records can point to curves, analysis results, comparison results, or reserved figure entries.
