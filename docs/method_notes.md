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

## Derived Data Tables

`app/core/derived_data.py` builds row-preserving derived tables from imported q and I(q). The table keeps every original point and writes `NaN` for values outside a mathematical domain or missing a required parameter. `NaN` in a derived column does not mean the original row was deleted.

Horizontal derived columns:

| Column | Formula | Domain / notes |
| --- | --- | --- |
| `q` | original q | finite q for most numerical use |
| `q2` | `q**2` | finite q |
| `ln_q` | `ln(q)` | `q > 0` |
| `log10_q` / `lg_q` | `log10(q)` | `q > 0` |
| `inv_q` | `1/q` | `q != 0` |
| `d_2pi_over_q` | `2π/q` | `q > 0`; unit is inverse of q unit |
| `qRg` | `q*Rg` | Rg must be supplied explicitly |
| `qD` / `qR` | `q*D`, `q*R` | D/R must be supplied explicitly |

Vertical derived columns:

| Column | Formula | Domain / notes |
| --- | --- | --- |
| `I` | original I(q) | finite I for most numerical use |
| `ln_I` | `ln(I)` | `I > 0`; used by Guinier and semilog views |
| `log10_I` / `lg_I` | `log10(I)` | `I > 0` |
| `qI` | `q*I` | finite q and I |
| `q2I` | `q**2*I` | Kratky and invariant integrand |
| `q3I` | `q**3*I` | log-q contribution diagnostics |
| `q4I` | `q**4*I` | Porod view |
| `q_alpha_I` | `q**alpha*I` | alpha must be supplied and recorded in metadata |
| `local_slope_dlnI_dlnq` | `np.gradient(np.log(I), np.log(q))` on q-sorted valid rows | requires at least 3 rows with `q > 0` and `I > 0`; duplicate valid q returns NaN |
| `I_over_ref` | `I/I_ref` | reference curve must have the same q grid and nonzero reference intensity |
| `I_minus_ref` | `I-I_ref` | reference curve must have the same q grid |

`ln(x)` means natural logarithm. `lg(x)` and `log10(x)` mean base-10 logarithm. Guinier calculations and plots use `q2` vs `ln_I`, not `log10_I`.

Reference ratio/difference columns do not interpolate. If q grids differ, the reference columns are `NaN` and a fact-only warning is recorded. This first implementation also records units as strings and does not automatically convert between `A^-1` and `nm^-1`.

## Plotting

Supported plot types include linear `I(q) vs q`, semi-log `ln I(q) vs q`, log-log/power-law `ln I(q) vs ln q`, Guinier `ln I(q) vs q²`, Kratky `q²I(q) vs q`, Porod `q⁴I(q) vs q`, invariant-integrand `q²I(q) vs q`, log-q contribution `q³I(q) vs ln q`, local slope `α(q) vs q`, and peak/d-spacing `I(q) vs q` with `d = 2π/q*` annotation.

Semilog, loglog, and Guinier plots filter `I(q) <= 0` before applying logarithms. Loglog, Guinier, and q³I invariant-contribution plots filter `q <= 0` where the transform requires positive q. Filtering returns warnings rather than raising numerical runtime warnings.

When error bars are shown on log-intensity plots, the propagated error is `sigma_lnI = sigma_I / I`. Invalid propagated errors are hidden and reported as warnings.

Manual X/Y axis limits and quick full/low/mid/high q buttons only change the displayed axes. They do not modify `CurveData`, saved data, or analysis ranges. For transformed views, the X range is in display coordinates: q² for Guinier and ln q for log-log or log-q contribution plots. Cursor readout reports display coordinates and, where useful, approximate back-transformed q/I values.

The plotting tab and model-free analysis tab are linked through a shared plot/analysis mapping. The link is user-triggered: selecting a plot type does not automatically change tabs, but the user can send supported plot views to the matching analysis or show the matching plot for a selected analysis.

Plotting data for transformed views comes from the same derived-table formulas used by export. For example, Guinier uses `q2` and `ln_I`, log-log uses `ln_q` and `ln_I`, Kratky/invariant use `q2I`, Porod uses `q4I`, and local slope uses `local_slope_dlnI_dlnq`.

Analysis `q_min/q_max` values remain raw physical q ranges. Physical q must be positive for analysis-range conversion. Display coordinates can be negative when they are transformed values, for example `ln q < 0` when `0 < q < 1`. The GUI can read the current plot x-limits and convert them back to raw q before analysis:

- raw-q plots: `q = x`;
- log-log and log-q contribution plots: `q = exp(x)`;
- Guinier plots: `q = sqrt(x)` because the display x-axis is q².

If a transformed range cannot be converted to a positive increasing raw q range, the analysis tab reports the conversion error and does not change the raw q fields.

When the source range comes from Matplotlib axis limits, the GUI first intersects the requested display x range with the current curve's valid display x range. This prevents automatic plot padding, such as a slightly negative raw-q or Guinier q² left edge, from invalidating an otherwise valid analysis interval. Negative `ln q` remains valid display x and is converted with `q = exp(x)`.

The optional top axis `d = 2π/q` is available only when the plot X-axis is raw q. This d value is an approximate characteristic scale or correlation distance, not a particle diameter.

## Analysis Preflight

Before standard model-free analysis, the GUI can run a raw q-range preflight check. The preflight checks whether a curve is selected, `q_min < q_max`, raw q values are non-negative, the selected range contains enough finite points, and log-based methods have enough points with `q > 0` and `I(q) > 0`.

Preflight severity is:

- `ok`: the selected range passes minimum numerical checks.
- `warning`: the analysis can run, but warnings such as filtered points, few peak points, finite-range invariant limits, or descriptive-only Kratky/Porod interpretation should be reviewed.
- `error`: the analysis should not run until the q range or data issue is corrected.

Preflight does not choose the best scientific interval and does not prove method validity. It only reports objective input facts, filtering counts, data-safety status, and method-boundary warnings.

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

## 2026-07-08 Eight Main Plot Analyses

Main plotting is restricted to eight analysis-linked views. All formulas use the imported `q` and `I(q)` arrays through the shared derived table; invalid mathematical domains are represented as `NaN` plus warnings, not by modifying data.

| Plot key | View | Main outputs |
| --- | --- | --- |
| `linear` | `I(q)` vs `q` | finite/negative/zero/non-finite counts and intensity range |
| `semilog` | `ln I(q)` vs `q` | valid `ln_I` count and filtered non-positive intensity count |
| `loglog` | `ln I(q)` vs `ln q` | `fit_slope_m`, `α = -m`, `A = exp(b)`, `R2`, residuals |
| `guinier` | `ln I(q)` vs `q²` | `Rg`, `I0`, slope/intercept, qRg range, `R2`, residuals |
| `kratky` | `q²I(q)` vs `q` | peak position/intensity, FWHM, selected-range area, trend slope |
| `porod` | `q⁴I(q)` vs `q` | loglog slope/α, q⁴I mean/std/CV, stability score, relative Porod constant |
| `invariant` | `q²I(q)` vs `q` | finite measured integral `Q_measured = ∫ q²I(q) dq` |
| `local_slope` | `α(q)` vs `q` | selected-range average α and standard deviation |

Guinier results require a negative fitted slope to calculate a real `Rg`. If the slope is non-negative, the result records a warning instead of forcing a radius. The qRg check is empirical and does not prove physical validity.

Kratky and Porod outputs are descriptive shape or relative plateau metrics for systems such as Ti-SiC composites. They must not be interpreted as protein-folding states or absolute specific surface area unless the user supplies the needed physical assumptions and calibration.

Invariant output is finite-range `Q_measured` only. It is not a full scattering invariant without justified low-q and high-q extrapolation.

Local slope uses `α(q) = -d ln I / d ln q`. The exported raw derivative `local_slope_dlnI_dlnq` is retained for audit. Automatic plateau detection is not implemented in this version because local slope is noise-sensitive.
