from __future__ import annotations

import numpy as np

from app.core.data_model import AnalysisResult, CurveData


def compute_pr(curve: CurveData, q_range: tuple[float, float], dmax: float, regularization: float | None = None) -> AnalysisResult:
    r = np.linspace(0.0, dmax, 50)
    warnings = [
        "Experimental placeholder: this is not a mature indirect Fourier transform implementation.",
        "P(r) is more appropriate for isolated scatterers or dilute solution systems.",
        "Dmax is highly dependent on q range and regularization.",
    ]
    results = {"r": r.tolist(), "P(r)": [0.0 for _ in r], "Dmax": dmax, "Rg_from_pr": None, "experimental": True}
    return AnalysisResult.create(
        curve=curve,
        analysis_type="pr_experimental_placeholder",
        q_range=q_range,
        parameters={"dmax": dmax, "regularization": regularization},
        results=results,
        warnings=warnings,
    )

