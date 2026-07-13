"""Validate a Ti15 model-free result directory and write a JSON QA record.

This checker never opens or modifies raw experiment CSV files.  It validates
the exported package: hard q boundaries, dual-track inventory, formal-report
gates, source-integrity flags, figures, workbook QA, and absence of ZIP files.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


HARD_Q_RANGE = (0.01, 0.5)
CANDIDATE_METHODS = {"guinier", "power_law", "porod"}
ROOT_ENTRY_FILES = {
    "README.md",
    "final_report_zh.md",
    "final_results.csv",
    "run_config.json",
    "summary_tables.xlsx",
    "validation_summary.json",
}
ROOT_ENTRY_DIRECTORIES = {"audit", "details", "figures", "summary"}


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.is_file() and path.stat().st_size > 3 else pd.DataFrame()


def _first_existing(root: Path, *relative_paths: str) -> Path:
    for relative_path in relative_paths:
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return root / relative_paths[0]


def _is_q_coordinate_column(name: str) -> bool:
    token = name.strip().lower()
    if token in {
        "q",
        "q_start",
        "q_end",
        "q_min",
        "q_max",
        "q_mid",
        "q_peak",
        "q_star",
        "q0",
        "q10",
        "q50",
        "q90",
        "shoulder_q",
        "crossover_q",
        "peak_q",
    }:
        return True
    if re.fullmatch(r"q_(?:start|end|min|max|mid|peak|star)_a\^-1", token):
        return True
    if token.endswith(("_q_start", "_q_end", "_q_min", "_q_max", "_peak_q")):
        return True
    return token.startswith(("plateau_candidate_q_", "q4i_plateau_q_"))


def _q_boundary_violations(result_dir: Path) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    excluded_names = {"input_manifest_original.csv", "source_integrity_after_analysis.csv"}
    for path in sorted(result_dir.rglob("*.csv")):
        if path.name in excluded_names:
            continue
        try:
            table = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        except Exception as exc:
            violations.append({"file": str(path), "column": None, "reason": f"csv_read_failed:{type(exc).__name__}"})
            continue
        for column in table.columns:
            if not _is_q_coordinate_column(str(column)):
                continue
            numeric = pd.to_numeric(table[column], errors="coerce").dropna()
            bad = numeric[(numeric < HARD_Q_RANGE[0] - 1e-12) | (numeric > HARD_Q_RANGE[1] + 1e-12)]
            if not bad.empty:
                violations.append(
                    {
                        "file": str(path.relative_to(result_dir)),
                        "column": str(column),
                        "count": int(bad.size),
                        "minimum": float(bad.min()),
                        "maximum": float(bad.max()),
                    }
                )
    return violations


def validate_result_directory(result_dir: Path) -> dict[str, Any]:
    root = result_dir.resolve()
    config = json.loads((root / "run_config.json").read_text(encoding="utf-8"))
    fit_quality = _read_csv(root / "audit" / "fit_quality.csv")
    final_results = _read_csv(root / "final_results.csv")
    integrity = _read_csv(
        _first_existing(root, "audit/source_integrity_after_analysis.csv", "source_integrity_after_analysis.csv")
    )
    missing = _read_csv(_first_existing(root, "summary/missing_frames.csv", "missing_frames.csv"))
    references = _read_csv(
        _first_existing(root, "summary/room_temperature_reference.csv", "room_temperature_reference.csv")
    )
    consensus = _read_csv(_first_existing(root, "audit/consensus_regions.csv", "consensus_regions.csv"))

    expected_tracks: dict[str, set[str]] = {}
    if not fit_quality.empty:
        for method in fit_quality["analysis_type"].dropna().astype(str).unique():
            expected_tracks[method] = {"adaptive", "common"} if method in CANDIDATE_METHODS else {"effective"}
    inventory_failures: list[dict[str, Any]] = []
    for curve_name, curve_rows in fit_quality.groupby("curve_name", dropna=False):
        for method, tracks in expected_tracks.items():
            actual = set(curve_rows.loc[curve_rows["analysis_type"].eq(method), "range_track"].dropna().astype(str))
            if actual != tracks:
                inventory_failures.append(
                    {"curve_name": curve_name, "analysis_type": method, "expected": sorted(tracks), "actual": sorted(actual)}
                )

    formal_leak_count = 0
    if not final_results.empty and "reporting_status" in final_results:
        formal_leak_count = int((final_results["reporting_status"] != "reportable").sum())
    shape_row_count = int((fit_quality.get("analysis_type", pd.Series(dtype=str)) == "shape_models").sum())

    consensus_span_failures: list[dict[str, Any]] = []
    for _, row in consensus.iterrows():
        q_start = pd.to_numeric(pd.Series([row.get("q_start")]), errors="coerce").iloc[0]
        q_end = pd.to_numeric(pd.Series([row.get("q_end")]), errors="coerce").iloc[0]
        if pd.isna(q_start) or pd.isna(q_end):
            continue
        span = math.log10(float(q_end) / float(q_start))
        minimum = 0.30 if row.get("region_type") == "power_law" else 0.20 if row.get("region_type") == "porod" else 0.10
        if span + 1e-12 < minimum:
            consensus_span_failures.append(
                {"region_type": row.get("region_type"), "span_decades": span, "minimum": minimum}
            )

    workbook_qa_path = _first_existing(root, "audit/workbook_validation.json", "workbook_validation.json")
    workbook_qa = json.loads(workbook_qa_path.read_text(encoding="utf-8")) if workbook_qa_path.is_file() else {}
    formula_scan = str(workbook_qa.get("formula_error_scan", ""))
    formula_scan_passed = "matched 0 entries" in formula_scan.lower()
    figure_stems = {
        "q_selection_heatmap",
        "dual_track_parameter_trends",
        "residual_diagnostics",
        "finite_invariant_trend",
        "full_range_boundary_overview",
    }
    missing_figures = [
        f"{stem}.{suffix}"
        for stem in sorted(figure_stems)
        for suffix in ("png", "svg", "pdf")
        if not (root / "figures" / f"{stem}.{suffix}").is_file()
    ]
    q_violations = _q_boundary_violations(root)
    missing_values = sorted(pd.to_numeric(missing.get("missing_frame_index"), errors="coerce").dropna().astype(int).tolist())
    source_integrity_passed = bool(
        not integrity.empty
        and integrity["unchanged_after_analysis"].astype(str).str.lower().eq("true").all()
    )
    unexpected_root_entries = sorted(
        path.name
        for path in root.iterdir()
        if (path.is_file() and path.name not in ROOT_ENTRY_FILES)
        or (path.is_dir() and path.name not in ROOT_ENTRY_DIRECTORIES)
    )
    checks = {
        "configured_hard_q_range": list(config.get("effective_q_range", [])) == list(HARD_Q_RANGE),
        "q_coordinates_within_hard_boundary": not q_violations,
        "dual_track_inventory_complete": not inventory_failures,
        "shape_model_task_count_zero": shape_row_count == 0,
        "formal_table_contains_only_reportable_rows": formal_leak_count == 0,
        "common_ranges_meet_method_span_gates": not consensus_span_failures,
        "source_integrity_passed": source_integrity_passed,
        "missing_frames_recorded": missing_values == [105, 109, 115],
        "room_temperature_reference_recorded": len(references) == 1,
        "workbook_exists": (root / "summary_tables.xlsx").is_file(),
        "workbook_formula_scan_passed": formula_scan_passed,
        "research_figures_complete": not missing_figures,
        "zip_archives_absent": not list(root.rglob("*.zip")),
        "root_contains_only_entry_files_and_standard_directories": not unexpected_root_entries,
    }
    payload = {
        "result_directory": str(root),
        "hard_q_range_A^-1": list(HARD_Q_RANGE),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": {
            "curves": int(fit_quality["curve_id"].nunique()) if not fit_quality.empty else 0,
            "analysis_envelopes": int(len(fit_quality)),
            "formal_parameter_rows": int(len(final_results)),
            "shape_model_rows": shape_row_count,
            "source_files_checked": int(len(integrity)),
        },
        "q_boundary_violations": q_violations,
        "inventory_failures": inventory_failures,
        "formal_table_leak_count": formal_leak_count,
        "consensus_span_failures": consensus_span_failures,
        "missing_figure_files": missing_figures,
        "unexpected_root_entries": unexpected_root_entries,
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Ti15 model-free result package.")
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    payload = validate_result_directory(args.result_dir)
    output = args.result_dir / "validation_summary.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
