from __future__ import annotations

import numpy as np

from app.core.analysis_schema import RESULT_GROUP_FRACTAL, merge_standard_metadata
from app.core.data_model import AnalysisResult, CurveData
from app.core.model_free import local_slope, power_law_analysis
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


def fractal_analysis(curve: CurveData, q_range: tuple[float, float]) -> AnalysisResult:
    power = power_law_analysis(curve, q_range, min_points=5)
    alpha = power.results.get("alpha")
    local = local_slope(curve, q_range, window_length=5)
    alpha_std = local.results.get("alpha_std")
    mass_fractal_dimension = None
    surface_fractal_dimension = None
    interpretation = "not_fractal"
    if alpha is not None and 1.0 < alpha < 3.0:
        mass_fractal_dimension = float(alpha)
        interpretation = "mass_fractal_candidate"
    elif alpha is not None and 3.0 < alpha < 4.0:
        surface_fractal_dimension = float(6.0 - alpha)
        interpretation = "surface_fractal_candidate"
    checks = [
        validity_check("alpha_in_fractal_range", mass_fractal_dimension is not None or surface_fractal_dimension is not None, severity="warning", message="Power-law exponent is outside common SAS fractal ranges.", value=alpha),
        validity_check("local_slope_stable", alpha_std is not None and alpha_std <= 0.3, severity="warning", message="Local slope is not stable enough for a strong fractal assignment.", value=alpha_std, threshold=0.3),
        validity_check("fit_quality", power.results.get("R2") is not None and power.results.get("R2") >= 0.95, severity="warning", message="Power-law fit quality is below R2=0.95.", value=power.results.get("R2"), threshold=0.95),
    ]
    assumptions = ["single_power_law_interval_required", "fractal_interpretation_non_unique"]
    label, score = reliability_from_checks(checks, assumptions=assumptions)
    results = {
        "alpha": alpha,
        "R2": power.results.get("R2"),
        "alpha_std": alpha_std,
        "mass_fractal_dimension_candidate": mass_fractal_dimension,
        "surface_fractal_dimension_candidate": surface_fractal_dimension,
        "interpretation": interpretation,
        "plateau_candidate_ranges": local.results.get("plateau_candidate_ranges"),
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_FRACTAL,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Fractal dimensions from a SAS power law are candidate descriptors and are not unique structural proof.",
            "The chosen q interval must not cross peaks, shoulders, or mixed regimes.",
        ],
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="fractal",
        q_range=q_range,
        results=results,
        warnings=[*power.warnings, *warning_messages_from_checks(checks)],
    )

