from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from app.core.data_model import CurveData
from app.core.deep_scan import curve_quality_metrics, run_deep_scan, scan_guinier_candidates, scan_power_law_candidates


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


def test_deep_scan_keeps_legacy_scanner_import_paths_and_result_fields() -> None:
    q = np.geomspace(0.01, 0.5, 120)
    curve = CurveData.create(name="legacy", q=q, intensity=5.0 * q**-2.2)

    quality = curve_quality_metrics(curve, (float(q.min()), float(q.max())))
    result = run_deep_scan(curve, (float(q.min()), float(q.max())))

    assert quality["positive_log_points"] == q.size
    for key in [
        "quality",
        "best_guinier",
        "best_power_law",
        "peak_count",
        "peaks",
        "finite_invariant",
        "guinier_candidate_count",
        "power_law_candidate_count",
        "multiscale_candidate_count",
        "export_tables",
    ]:
        assert key in result.results


def test_deep_scan_does_not_define_duplicate_scanner_bodies() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "core" / "deep_scan.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function_names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]

    for name in [
        "_finite_positive_curve",
        "scan_guinier_candidates",
        "scan_power_law_candidates",
        "curve_quality_metrics",
        "_deep_peak_detection",
    ]:
        assert function_names.count(name) == 1
