from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.correlation import compute_correlation_function
from app.core.data_model import AnalysisResult, CurveData
from app.core.deep_scan import run_deep_scan
from app.core.fractal_analysis import fractal_analysis
from app.core.invariant_analysis import invariant_with_extrapolation
from app.core.lamellar_analysis import lamellar_analysis
from app.core.model_free import information_budget
from app.core.model_fitting import fit_shape_model
from app.core.porod_analysis import porod_deep_analysis
from app.core.pr_analysis import compute_pr
from app.core.shape_models import MODEL_SPECS


SAMPLE_TYPES = ["unknown", "particle", "polymer", "two_phase", "lamellar", "fractal"]
SHAPE_MODELS = ["none", *MODEL_SPECS.keys()]


@dataclass
class DeepAnalysisOptions:
    sample_type: str = "unknown"
    shape_model: str = "none"
    q_range: tuple[float, float] | None = None
    dmax: float | None = None
    regularization: float = 1e-2
    contrast: float | None = None
    volume_fraction: float | None = None
    absolute_intensity: bool = False
    fit_background: bool = True
    low_q_method: str = "disabled"
    high_q_method: str = "disabled"
    run_pr: bool = True
    run_correlation: bool = True
    run_lamellar: bool = True
    run_fractal: bool = True
    run_porod: bool = True
    run_invariant: bool = True
    run_information_budget: bool = True
    max_candidates: int = 8


def default_dmax(curve: CurveData, q_range: tuple[float, float]) -> float:
    q_min = max(float(q_range[0]), 1e-12)
    q_max = max(float(q_range[1]), q_min)
    return float(max(2.0 * np.pi / q_min, 4.0 * np.pi / q_max))


def run_deep_analysis(curve: CurveData, options: DeepAnalysisOptions | dict | None = None) -> list[AnalysisResult]:
    if options is None:
        opts = DeepAnalysisOptions()
    elif isinstance(options, dict):
        opts = DeepAnalysisOptions(**options)
    else:
        opts = options
    if opts.sample_type not in SAMPLE_TYPES:
        raise ValueError(f"Unsupported sample_type: {opts.sample_type}")
    if opts.shape_model not in SHAPE_MODELS:
        raise ValueError(f"Unsupported shape_model: {opts.shape_model}")

    q_range = opts.q_range
    if q_range is None:
        q_range = (float(np.nanmin(curve.q)), float(np.nanmax(curve.q)))
    results: list[AnalysisResult] = [run_deep_scan(curve, q_range, max_candidates=opts.max_candidates)]

    if opts.run_fractal and opts.sample_type in {"unknown", "fractal", "two_phase", "particle", "polymer"}:
        results.append(fractal_analysis(curve, q_range))
    if opts.run_invariant:
        results.append(
            invariant_with_extrapolation(
                curve,
                q_range,
                low_q_method=opts.low_q_method,
                high_q_method=opts.high_q_method,
                contrast=opts.contrast,
                absolute_intensity=opts.absolute_intensity,
            )
        )
    if opts.run_information_budget:
        results.append(information_budget(curve, q_range))
    if opts.run_porod:
        results.append(
            porod_deep_analysis(
                curve,
                q_range,
                contrast=opts.contrast,
                volume_fraction=opts.volume_fraction,
                absolute_intensity=opts.absolute_intensity,
            )
        )
    if opts.run_pr and opts.sample_type in {"unknown", "particle", "polymer"}:
        dmax = opts.dmax if opts.dmax is not None else default_dmax(curve, q_range)
        results.append(compute_pr(curve, q_range, dmax=dmax, regularization=opts.regularization))
    if opts.run_lamellar and (opts.sample_type == "lamellar" or opts.shape_model == "lamellar_peak_stack"):
        results.append(lamellar_analysis(curve, q_range))
    if opts.run_correlation and opts.sample_type in {"two_phase", "lamellar"}:
        results.append(compute_correlation_function(curve, q_range, {"r_max": opts.dmax or default_dmax(curve, q_range)}))
    if opts.shape_model != "none":
        results.append(fit_shape_model(curve, q_range, opts.shape_model, fit_background=opts.fit_background))
    return results
