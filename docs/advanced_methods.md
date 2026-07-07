# Advanced Methods And Reserved Interfaces

Advanced interfaces in `sas_curve_analyzer` are designed to be optional, explicit, traceable, and conservative. They are not automatic structure-identification tools.

## Structured Method Warnings

Method warnings are represented as structured objects with:

- `warning_code`
- `severity`
- `message`
- `suggested_action`
- `related_analysis_id`

These warnings are attached to `AnalysisResult.structured_warnings` and exported with JSON reports. They are intended to make method limitations visible in the GUI, project history, and exported reports.

## Experimental P(r) Interface

The current P(r) interface is experimental. It is not a validated indirect Fourier transform implementation.

The interface exists so future validated algorithms can share the same analysis-result structure. Current output should not be used for formal size-distribution or pair-distance conclusions.

Typical P(r) interpretation requires careful q-range coverage, background quality, Dmax selection, regularization control, and physical assumptions about the scattering system.

The model catalog marks this path as experimental. Any future production P(r) implementation must report the transform formula, Dmax, regularization, q range, residual or stability checks, and interpretation limits.

## Reserved Correlation-Function Interface

The correlation-function entry point is reserved and raises a clear `NotImplementedError`.

Correlation-function analysis can be useful for lamellar, quasi-lamellar, or two-phase systems, but automatic extraction of long period, interface thickness, or domain parameters requires explicit structural assumptions and often low-q or high-q extrapolation.

## Reserved Extrapolation Interfaces

Low-q and high-q extrapolation interfaces exist but are disabled by default.

Reserved method names include:

- Low q: `Guinier`, `constant`, `disabled`
- High q: `Porod q^-4`, `power-law`, `disabled`

Measured-range invariant calculations do not use extrapolation by default. Any future extrapolation path must report method warnings and record parameters.

## Shape And Empirical Model Boundaries

The model catalog includes shape/form-factor entries such as sphere, core-shell sphere, ellipsoid, cylinder, and disk models. These are model-dependent fits. Their parameters depend on q range, contrast, background, polydispersity, initial values, and whether the assumed morphology is defensible.

Empirical or semi-empirical entries such as Gaussian chain, Debye-Anderson-Brumberger, mass fractal, surface fractal, and lamellar peak-stack descriptions are transparency records for possible future or external analysis. A visually good fit or stable slope is not unique structural proof. Reports should preserve the selected q range, assumptions, warnings, and model status.

## Porod And Invariant Boundaries

Porod plateau metrics and finite q-range invariant values are descriptive unless the user supplies the external physical assumptions needed for quantitative interpretation.

The software does not automatically calculate:

- Absolute specific surface area.
- Phase volume fraction.
- Scattering contrast.
- q = 0 or q = infinity extrapolated invariant.

## Plugin Interface

The plugin base classes support analysis extensions that return `AnalysisResult`. Plugin implementations should:

- Keep numerical logic in `app/core`.
- Return text and structured warnings where method assumptions matter.
- Avoid silently modifying input curves.
- Add tests that cover expected outputs and failure modes.
