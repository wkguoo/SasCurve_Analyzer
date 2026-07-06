from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.deep_scan import run_deep_scan, scan_guinier_candidates, scan_power_law_candidates


def test_deep_scan_ranks_guinier_candidate() -> None:
    q = np.linspace(0.005, 0.05, 80)
    rg_true = 20.0
    i0_true = 100.0
    curve = CurveData.create(name="guinier", q=q, intensity=i0_true * np.exp(-(rg_true**2) * q**2 / 3.0))
    candidates = scan_guinier_candidates(curve, (float(q.min()), float(q.max())))
    assert candidates
    assert np.isclose(candidates[0]["Rg"], rg_true, rtol=0.05)
    result = run_deep_scan(curve, (float(q.min()), float(q.max())))
    assert result.results["reliability_label"] in {"high", "medium"}
    assert result.results["export_tables"]["guinier_candidates"]


def test_deep_scan_sorts_q_before_candidate_windowing() -> None:
    q = np.linspace(0.005, 0.05, 80)
    rg_true = 20.0
    intensity = 100.0 * np.exp(-(rg_true**2) * q**2 / 3.0)
    sorted_curve = CurveData.create(name="sorted", q=q, intensity=intensity)
    reversed_curve = CurveData.create(name="reversed", q=q[::-1], intensity=intensity[::-1])

    sorted_result = run_deep_scan(sorted_curve, (float(q.min()), float(q.max())))
    reversed_result = run_deep_scan(reversed_curve, (float(q.min()), float(q.max())))

    assert reversed_result.results["best_guinier"] is not None
    assert np.isclose(reversed_result.results["best_guinier"]["Rg"], sorted_result.results["best_guinier"]["Rg"])


def test_power_law_candidates_report_fractal_like_interval() -> None:
    q = np.linspace(0.02, 0.5, 100)
    curve = CurveData.create(name="power", q=q, intensity=5.0 * q**-2.2)
    candidates = scan_power_law_candidates(curve, (float(q.min()), float(q.max())))
    assert candidates
    assert np.isclose(candidates[0]["alpha"], 2.2, rtol=0.02)
    assert candidates[0]["interpretation"] == "mass_fractal_candidate"
