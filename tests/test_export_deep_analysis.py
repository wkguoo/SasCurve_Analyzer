from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.data_model import CurveData
from app.core.deep_analysis import DeepAnalysisOptions, run_deep_analysis
from app.core.export import export_analysis_bundle


def test_export_analysis_bundle_writes_all_expected_files(tmp_path) -> None:
    q = np.linspace(0.01, 0.2, 80)
    curve = CurveData.create(name="curve", q=q, intensity=100.0 * np.exp(-(20.0**2) * q**2 / 3.0))
    analyses = run_deep_analysis(curve, DeepAnalysisOptions(q_range=(float(q.min()), float(q.max())), run_pr=True, dmax=100.0))
    outputs = export_analysis_bundle([curve], analyses, tmp_path)
    expected = {
        "analysis_full",
        "analysis_summary",
        "feature_table",
        "fit_curves",
        "peaks",
        "guinier_candidates",
        "power_law_candidates",
        "pr_distribution",
        "correlation_function",
        "report",
    }
    assert expected.issubset(outputs)
    for path in outputs.values():
        assert path.exists()
    summary = pd.read_csv(outputs["analysis_summary"])
    assert "reliability_label" in summary.columns

