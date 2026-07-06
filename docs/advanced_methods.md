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

## Reserved Correlation-Function Interface

The correlation-function entry point is reserved and raises a clear `NotImplementedError`.

Correlation-function analysis can be useful for lamellar, quasi-lamellar, or two-phase systems, but automatic extraction of long period, interface thickness, or domain parameters requires explicit structural assumptions and often low-q or high-q extrapolation.

## Reserved Extrapolation Interfaces

Low-q and high-q extrapolation interfaces exist but are disabled by default.

Reserved method names include:

- Low q: `Guinier`, `constant`, `disabled`
- High q: `Porod q^-4`, `power-law`, `disabled`

Measured-range invariant calculations do not use extrapolation by default. Any future extrapolation path must report method warnings and record parameters.

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
