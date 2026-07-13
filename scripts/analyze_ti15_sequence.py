"""Run the Ti15 SAXS model-free sequence workflow without changing raw CSV files.

The selected source files are hashed, copied into a temporary working folder,
and analyzed through the existing batch API.  Persistent files are written only
to a new timestamped directory below ``results``.  A room-temperature curve
whose filename contains ``-rt_`` is always retained as an independent reference
and is not counted as an in-situ frame.

Examples (PowerShell, from the ``sas_curve_analyzer`` directory)::

    python scripts\analyze_ti15_sequence.py --limit 10
    python scripts\analyze_ti15_sequence.py --limit 0

``--limit 10`` is the safe trial run.  ``--limit 0`` selects all 117 in-situ
frames plus the room-temperature reference while preserving missing frame
numbers 105, 109, and 115.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AutoBatchConfig, ProgressEvent
from app.core.io import load_curve
from app.core.result_package import export_result_package


DEFAULT_INPUT_DIR = Path(
    r"D:\桌面\PostFile\6_sys\SAXS-学习2\17_Ti15_300_2_iso\17_Ti15_300_2_iso\spectra_csv"
)
DEFAULT_RESULTS_ROOT = WORKSPACE_DIR / "results"
HARD_Q_RANGE = (0.01, 0.5)
BOUNDARY_AUDIT_PEAK_Q = 0.00925
EXPECTED_SERIES_COUNT = 117
EXPECTED_REFERENCE_COUNT = 1
EXPECTED_FRAME_RANGE = (1, 120)
EXPECTED_MISSING_FRAMES = [105, 109, 115]

SERIES_PATTERN = re.compile(r"^ti15_(\d{5})_abs2d_cm-1\.csv$", re.IGNORECASE)
REFERENCE_PATTERN = re.compile(r"^ti15-rt_(\d{5})_abs2d_cm-1\.csv$", re.IGNORECASE)


@dataclass(frozen=True)
class Ti15Selection:
    """Auditable source selection for one run."""

    selected_series: tuple[tuple[int, Path], ...]
    references: tuple[Path, ...]
    all_series_frames: tuple[int, ...]
    missing_frames: tuple[int, ...]
    limit: int

    @property
    def selected_paths(self) -> list[Path]:
        return [path for _, path in self.selected_series] + list(self.references)

    @property
    def selected_frame_numbers(self) -> list[int]:
        return [frame for frame, _ in self.selected_series]


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a source hash without loading the whole file into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def discover_ti15_inputs(input_dir: Path, limit: int) -> Ti15Selection:
    """Find Ti15 frames and the independent RT reference by strict filenames."""

    if limit < 0:
        raise ValueError("--limit must be 0 (all frames) or a positive integer")
    root = input_dir.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {root}")

    series: dict[int, Path] = {}
    references: list[Path] = []
    for path in root.iterdir():
        if not path.is_file() or path.suffix.lower() != ".csv":
            continue
        series_match = SERIES_PATTERN.match(path.name)
        if series_match:
            frame = int(series_match.group(1))
            if frame in series:
                raise ValueError(f"Duplicate Ti15 frame {frame}: {series[frame].name}, {path.name}")
            series[frame] = path.resolve()
            continue
        if REFERENCE_PATTERN.match(path.name):
            references.append(path.resolve())

    if not series:
        raise FileNotFoundError(f"No Ti15 in-situ CSV files were found in: {root}")
    if not references:
        raise FileNotFoundError(f"No room-temperature reference matching 'TI15-rt_*.csv' was found in: {root}")

    sorted_series = sorted(series.items())
    selected_series = sorted_series if limit == 0 else sorted_series[:limit]
    if limit > 0 and len(selected_series) < limit:
        raise ValueError(f"Requested {limit} frames, but only {len(sorted_series)} were found")

    all_frames = tuple(frame for frame, _ in sorted_series)
    missing = tuple(sorted(set(range(all_frames[0], all_frames[-1] + 1)) - set(all_frames)))
    return Ti15Selection(
        selected_series=tuple(selected_series),
        references=tuple(sorted(references, key=lambda path: path.name.lower())),
        all_series_frames=all_frames,
        missing_frames=missing,
        limit=limit,
    )


def validate_standard_layout(selection: Ti15Selection) -> None:
    """Fail early if the default Ti15 directory does not match the agreed layout."""

    problems: list[str] = []
    if len(selection.all_series_frames) != EXPECTED_SERIES_COUNT:
        problems.append(
            f"expected {EXPECTED_SERIES_COUNT} in-situ frames, found {len(selection.all_series_frames)}"
        )
    if len(selection.references) != EXPECTED_REFERENCE_COUNT:
        problems.append(
            f"expected {EXPECTED_REFERENCE_COUNT} RT reference, found {len(selection.references)}"
        )
    actual_range = (selection.all_series_frames[0], selection.all_series_frames[-1])
    if actual_range != EXPECTED_FRAME_RANGE:
        problems.append(f"expected frame range {EXPECTED_FRAME_RANGE}, found {actual_range}")
    if list(selection.missing_frames) != EXPECTED_MISSING_FRAMES:
        problems.append(
            f"expected missing frames {EXPECTED_MISSING_FRAMES}, found {list(selection.missing_frames)}"
        )
    if problems:
        raise ValueError("Non-standard Ti15 input layout: " + "; ".join(problems))


def build_config(*, limit: int) -> AutoBatchConfig:
    """Return the fixed model-free configuration required by the Ti15 plan."""

    run_scope = "full" if limit == 0 else f"trial_first_{limit}"
    return AutoBatchConfig(
        batch_id=f"17_Ti15_300_2_iso_{run_scope}",
        sample_type="unknown",
        enable_shape_models=False,
        allowed_models=[],
        effective_q_range=HARD_Q_RANGE,
        q_unit_override="A^-1",
        intensity_unit_override="cm^-1",
        consensus_min_coverage=0.70,
        allow_per_frame_range_fallback=False,
        range_mode="dual",
        absolute_intensity=True,
        contrast=None,
        volume_fraction=None,
        enable_pr=False,
        enable_correlation=False,
        enable_bootstrap=True,
        bootstrap_samples=200,
        bootstrap_seed=12345,
        bootstrap_mode="moving_block_residual",
        bootstrap_block_length=0,
        enable_range_sensitivity=True,
        sensitivity_boundary_fraction=0.05,
        enable_sequence_analysis=False,
        sequence_axis=None,
        reference_mode="first",
        enable_kinetics=False,
        enable_exploratory_statistics=False,
        reference_filename_pattern="-rt_",
        create_archives=False,
    )


def source_snapshot(selection: Ti15Selection) -> list[dict[str, Any]]:
    """Record size, timestamp, and SHA-256 for every selected raw input."""

    frame_by_path = {path: frame for frame, path in selection.selected_series}
    rows: list[dict[str, Any]] = []
    for path in selection.selected_paths:
        stat = path.stat()
        is_reference = path in selection.references
        rows.append(
            {
                "sequence_role": "reference" if is_reference else "series",
                "frame_index": None if is_reference else frame_by_path[path],
                "source_file": path.name,
                "source_path": str(path),
                "size_bytes": int(stat.st_size),
                "modified_time_ns": int(stat.st_mtime_ns),
                "sha256": sha256_file(path),
            }
        )
    return rows


def _snapshot_index(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["source_file"]).lower(): row for row in rows}


def _remap_run_sources(run: Any, before: list[dict[str, Any]]) -> None:
    """Replace temporary paths in the in-memory audit with original read-only paths."""

    original = _snapshot_index(before)
    for curve in run.curves:
        filename = Path(curve.source_file or "").name
        row = original[filename.lower()]
        curve.source_file = str(row["source_path"])
        curve.metadata["sequence_role"] = row["sequence_role"]
        curve.metadata["is_reference"] = row["sequence_role"] == "reference"
        curve.metadata["frame_index"] = row["frame_index"]
        curve.metadata["source_sha256"] = row["sha256"]

    run.input_manifest = [
        {
            **row,
            "modified_time": row["modified_time_ns"] / 1_000_000_000,
            "manifest_status": "success",
            "manifest_error": None,
        }
        for row in before
    ]


def source_integrity_rows(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare the two immutable-source snapshots."""

    old_by_name = _snapshot_index(before)
    output: list[dict[str, Any]] = []
    for row in after:
        old = old_by_name[row["source_file"].lower()]
        unchanged = all(
            old[key] == row[key]
            for key in ("size_bytes", "modified_time_ns", "sha256")
        )
        output.append({**row, "unchanged_after_analysis": unchanged})
    return output


def data_quality_rows(run: Any) -> list[dict[str, Any]]:
    """Build the compact quality table consumed by the summary workbook."""

    q_low, q_high = HARD_Q_RANGE
    rows: list[dict[str, Any]] = []
    for curve in run.curves:
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        finite = np.isfinite(q) & np.isfinite(intensity) & (q >= q_low) & (q <= q_high)
        selected_q = q[finite]
        selected_i = intensity[finite]
        metadata = curve.metadata or {}
        import_filter = metadata.get("import_q_range_filter", {})
        raw_count = import_filter.get("raw_point_count", q.size)
        filtered_count = import_filter.get("filtered_out_point_count", 0)
        rows.append(
            {
                "frame_index": metadata.get("frame_index"),
                "sequence_role": metadata.get("sequence_role", "series"),
                "curve_name": curve.name,
                "source_file": Path(curve.source_file or "").name,
                "q_unit": curve.q_unit,
                "point_count": int(finite.sum()),
                "finite_pair_count": int(finite.sum()),
                "nan_or_inf_pair_count": int(q.size - np.isfinite(q).sum()),
                "negative_intensity_count": int(np.sum(selected_i < 0)),
                "zero_intensity_count": int(np.sum(selected_i == 0)),
                "duplicate_q_count": int(pd.Series(selected_q).duplicated().sum()),
                "strictly_increasing_q": bool(
                    selected_q.size >= 2 and np.all(np.diff(selected_q) > 0)
                ),
                "log_usable_count": int(np.sum((selected_q > 0) & (selected_i > 0))),
                "q_min_A^-1": float(np.min(selected_q)) if selected_q.size else None,
                "q_max_A^-1": float(np.max(selected_q)) if selected_q.size else None,
                "I_min_cm^-1": float(np.min(selected_i)) if selected_i.size else None,
                "I_max_cm^-1": float(np.max(selected_i)) if selected_i.size else None,
                "hard_q_low_A^-1": q_low,
                "hard_q_high_A^-1": q_high,
                "raw_source_point_count": int(raw_count),
                "filtered_out_point_count": int(filtered_count),
                "has_measurement_error_column": curve.error is not None,
            }
        )
    return rows


def write_sequence_audit_tables(
    output_dir: Path,
    run: Any,
    selection: Ti15Selection,
    before: list[dict[str, Any]],
    integrity: list[dict[str, Any]],
) -> None:
    """Write source, frame-gap, reference, and finite-range quality audits."""

    summary_dir = output_dir / "summary"
    audit_dir = output_dir / "audit"
    summary_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(before).to_csv(
        audit_dir / "input_manifest_original.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(integrity).to_csv(
        audit_dir / "source_integrity_after_analysis.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(data_quality_rows(run)).to_csv(
        summary_dir / "data_quality.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(
        [{"missing_frame_index": frame, "reason": "source CSV absent"} for frame in selection.missing_frames]
    ).to_csv(summary_dir / "missing_frames.csv", index=False, encoding="utf-8-sig")

    reference_rows = []
    for path in selection.references:
        reference_rows.append(
            {
                "source_file": path.name,
                "source_path": str(path),
                "sequence_role": "independent_room_temperature_reference",
                "participates_in_common_range_consensus": False,
                "included_in_batch_analysis": True,
            }
        )
    pd.DataFrame(reference_rows).to_csv(
        summary_dir / "room_temperature_reference.csv", index=False, encoding="utf-8-sig"
    )

    frame_by_curve = {
        curve.name: curve.metadata.get("frame_index")
        for curve in run.curves
    }
    role_by_curve = {
        curve.name: curve.metadata.get("sequence_role", "series")
        for curve in run.curves
    }

    def enriched_parameters(source: Path) -> pd.DataFrame:
        if not source.is_file() or source.stat().st_size <= 3:
            return pd.DataFrame(
                columns=[
                    "frame",
                    "sequence_role",
                    "curve_name",
                    "analysis_type",
                    "range_track",
                    "reporting_status",
                    "reporting_reason_codes",
                    "parameter",
                    "value",
                    "unit_role",
                    "q_start_A^-1",
                    "q_end_A^-1",
                    "reliability_label",
                    "reliability_score",
                ]
            )
        table = pd.read_csv(source)
        table.insert(0, "frame", table.get("curve_name", pd.Series(dtype=str)).map(frame_by_curve))
        table.insert(
            1,
            "sequence_role",
            table.get("curve_name", pd.Series(dtype=str)).map(role_by_curve),
        )
        table["parameter"] = table.get("name")
        table["unit_role"] = table.get("unit", "")
        table["q_start_A^-1"] = table.get("q_start")
        table["q_end_A^-1"] = table.get("q_end")
        return table

    audit_parameters = enriched_parameters(audit_dir / "parameters.csv")
    audit_parameters.to_csv(
        audit_dir / "all_parameters_audit.csv", index=False, encoding="utf-8-sig"
    )
    accepted_mask = (
        audit_parameters.get("analysis_status", pd.Series(index=audit_parameters.index, dtype=str))
        .isin(["success", "assumption_dependent"])
        & audit_parameters.get("status", pd.Series(index=audit_parameters.index, dtype=str))
        .isin(["success", "assumption_dependent"])
        & audit_parameters.get(
            "reporting_status", pd.Series(index=audit_parameters.index, dtype=str)
        ).eq("reportable")
    )
    audit_parameters.loc[accepted_mask].to_csv(
        summary_dir / "accepted_parameters.csv", index=False, encoding="utf-8-sig"
    )

    reliable_parameters = enriched_parameters(summary_dir / "reliable_parameters.csv")
    reliable_parameters.to_csv(
        output_dir / "final_results.csv", index=False, encoding="utf-8-sig"
    )

    for track in ("adaptive", "common"):
        track_mask = audit_parameters.get(
            "range_track", pd.Series(index=audit_parameters.index, dtype=str)
        ).eq(track)
        audit_parameters.loc[track_mask].to_csv(
            summary_dir / f"{track}_parameters.csv", index=False, encoding="utf-8-sig"
        )

    dual_columns = [
        "curve_id",
        "curve_name",
        "analysis_type",
        "name",
        "unit",
        "range_track",
        "value",
        "q_start",
        "q_end",
        "reporting_status",
    ]
    if all(column in audit_parameters.columns for column in dual_columns):
        dual = audit_parameters.loc[
            audit_parameters["range_track"].isin(["adaptive", "common"]), dual_columns
        ].copy()
        dual["numeric_value"] = pd.to_numeric(dual["value"], errors="coerce")
        adaptive = dual[dual["range_track"] == "adaptive"].drop(columns="range_track")
        common = dual[dual["range_track"] == "common"].drop(columns="range_track")
        keys = ["curve_id", "curve_name", "analysis_type", "name", "unit"]
        differences = adaptive.merge(common, on=keys, how="outer", suffixes=("_adaptive", "_common"))
        differences["common_minus_adaptive"] = (
            differences["numeric_value_common"] - differences["numeric_value_adaptive"]
        )
        denominator = differences["numeric_value_adaptive"].abs().replace(0.0, np.nan)
        differences["relative_difference"] = differences["common_minus_adaptive"] / denominator
    else:
        differences = pd.DataFrame(
            columns=[
                "curve_id",
                "curve_name",
                "analysis_type",
                "name",
                "unit",
                "numeric_value_adaptive",
                "numeric_value_common",
                "common_minus_adaptive",
                "relative_difference",
            ]
        )
    differences.to_csv(
        summary_dir / "dual_track_differences.csv", index=False, encoding="utf-8-sig"
    )

    robustness_rows: list[dict[str, Any]] = []
    for envelope in run.analyses:
        for row in envelope.tables.get("robustness_summary", []):
            if not isinstance(row, dict):
                continue
            robustness_rows.append(
                {
                    "frame": frame_by_curve.get(envelope.curve_name),
                    "sequence_role": role_by_curve.get(envelope.curve_name),
                    "curve_id": envelope.curve_id,
                    "curve_name": envelope.curve_name,
                    "analysis_id": envelope.analysis_id,
                    "analysis_type": envelope.analysis_type,
                    "range_track": envelope.range_track,
                    "q_start_A^-1": None if envelope.q_range is None else envelope.q_range[0],
                    "q_end_A^-1": None if envelope.q_range is None else envelope.q_range[1],
                    **{
                        key: json.dumps(value, ensure_ascii=False)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in row.items()
                    },
                }
            )

    fit_quality_path = audit_dir / "fit_quality.csv"
    if fit_quality_path.is_file() and fit_quality_path.stat().st_size > 3:
        fit_quality = pd.read_csv(fit_quality_path)
        robustness_columns = [
            column
            for column in fit_quality.columns
            if column
            in {
                "curve_id",
                "curve_name",
                "analysis_id",
                "analysis_type",
                "range_track",
                "status",
                "reporting_status",
                "robustness_status",
                "uncertainty_interpretation",
                "q_start",
                "q_end",
            }
            or column.startswith(("bootstrap", "range_sensitivity", "sensitivity"))
        ]
        fit_robustness = fit_quality.loc[:, robustness_columns]
    else:
        fit_robustness = pd.DataFrame(
            columns=[
                "curve_id",
                "curve_name",
                "analysis_type",
                "range_track",
                "robustness_status",
                "uncertainty_interpretation",
            ]
        )
    robustness = pd.DataFrame(robustness_rows)
    if robustness.empty:
        robustness = fit_robustness
    robustness.to_csv(summary_dir / "robustness.csv", index=False, encoding="utf-8-sig")


def write_workbook_compact_tables(output_dir: Path) -> None:
    """Create memory-bounded workbook sources while retaining full CSV audits."""

    audit_dir = output_dir / "audit"
    workbook_sources_dir = audit_dir / "workbook_sources"
    workbook_sources_dir.mkdir(parents=True, exist_ok=True)
    parameters = _read_export_table(audit_dir / "all_parameters_audit.csv")
    fit_quality = _read_export_table(audit_dir / "fit_quality.csv")
    candidates = _read_export_table(audit_dir / "candidate_windows.csv")

    inventory_columns = [
        "curve_id",
        "curve_name",
        "analysis_id",
        "analysis_type",
        "range_track",
        "status",
        "execution_status",
        "candidate_status",
        "consensus_status",
        "reporting_status",
        "reporting_reason_codes",
        "range_source",
        "q_start",
        "q_end",
        "reliability_label",
        "reliability_score",
        "robustness_status",
        "uncertainty_interpretation",
        "R2",
        "execution_fit_points",
        "execution_log_q_span_decades",
        "residual_lag1_correlation",
        "residual_quadratic_score",
        "residual_randomness_passed",
        "local_alpha_std",
        "local_alpha_stability_passed",
        "high_q_position_fraction",
        "noise_score",
        "invalid_reason",
        "warnings",
    ]
    fit_quality.loc[:, [column for column in inventory_columns if column in fit_quality]].to_csv(
        workbook_sources_dir / "analysis_inventory_workbook.csv",
        index=False,
        encoding="utf-8-sig",
    )

    index_columns = [
        column
        for column in ("frame", "sequence_role", "curve_id", "curve_name")
        if column in parameters
    ]
    for track in ("adaptive", "common"):
        subset = parameters[
            parameters.get("range_track", pd.Series(index=parameters.index, dtype=str)).eq(track)
        ].copy()
        if subset.empty or not index_columns:
            wide = pd.DataFrame(columns=index_columns)
        else:
            for column in index_columns:
                subset[column] = subset[column].fillna("RT" if column == "frame" else "")
            subset["parameter_key"] = (
                subset["analysis_type"].astype(str)
                + "__"
                + subset["name"].astype(str)
                + " ["
                + subset.get("unit", pd.Series(index=subset.index, dtype=str)).fillna("").astype(str)
                + "]"
            )
            subset["numeric_value"] = pd.to_numeric(subset["value"], errors="coerce")
            wide = subset.pivot_table(
                index=index_columns,
                columns="parameter_key",
                values="numeric_value",
                aggfunc="first",
            ).reset_index()
            wide.columns.name = None
        wide.to_csv(
            workbook_sources_dir / f"{track}_parameters_workbook.csv",
            index=False,
            encoding="utf-8-sig",
        )

    compact_candidate_columns = [
        "curve_id",
        "curve_name",
        "sequence_role",
        "region_type",
        "q_start",
        "q_end",
        "n_points",
        "score",
        "confidence_label",
        "fit_ready",
        "recommended_analysis",
        "detection_method",
    ]
    candidates.loc[
        :, [column for column in compact_candidate_columns if column in candidates]
    ].to_csv(
        workbook_sources_dir / "candidate_windows_workbook.csv",
        index=False,
        encoding="utf-8-sig",
    )


def _read_export_table(path: Path) -> pd.DataFrame:
    if not path.is_file() or path.stat().st_size <= 3:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "value"):
        return value.value
    return str(value)


def write_run_config(output_dir: Path, run: Any, selection: Ti15Selection) -> None:
    payload = dict(run.config_snapshot)
    payload["input_selection"] = {
        "limit": selection.limit,
        "selected_series_count": len(selection.selected_series),
        "reference_count": len(selection.references),
        "selected_frame_numbers": selection.selected_frame_numbers,
        "all_series_count": len(selection.all_series_frames),
        "all_series_frame_numbers": list(selection.all_series_frames),
        "missing_series_frames": list(selection.missing_frames),
    }
    payload["scientific_scope"] = {
        "sequence_axis": "true frame_index only; gaps are retained",
        "room_temperature_curve": "independent reference; excluded from common-range consensus",
        "hard_q_boundary_A^-1": list(HARD_Q_RANGE),
        "boundary_audit_main_peak_q_A^-1": BOUNDARY_AUDIT_PEAK_Q,
        "boundary_audit_peak_included_in_fits": False,
        "shape_models_enabled": False,
        "measurement_uncertainty": "not available; robustness intervals are not instrument confidence intervals",
        "finite_invariant_only": True,
        "create_archives": False,
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _save_research_figure(fig: Any, figures_dir: Path, stem: str) -> None:
    """Export one publication-ready figure in raster and vector formats."""

    figures_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(
            figures_dir / f"{stem}.{suffix}",
            dpi=300 if suffix == "png" else None,
            bbox_inches="tight",
            facecolor="white",
        )
    plt.close(fig)


def generate_research_figures(output_dir: Path, run: Any, selection: Ti15Selection) -> None:
    """Create the fixed set of scientific QA figures required by the workflow."""

    figures_dir = output_dir / "figures"
    frame_by_curve = {curve.name: curve.metadata.get("frame_index") for curve in run.curves}
    role_by_curve = {curve.name: curve.metadata.get("sequence_role", "series") for curve in run.curves}

    range_table = pd.DataFrame(run.range_audit)
    methods = ("guinier", "power_law", "porod")
    fig, axes = plt.subplots(1, 3, figsize=(12.2, 5.4), sharey=True)
    track_style = {"adaptive": ("#1f77b4", 1.0), "common": ("#d62728", 1.8)}
    for axis, method in zip(axes, methods):
        subset = range_table[
            range_table.get("method_id", pd.Series(dtype=str)).eq(method)
            & range_table.get("q_start", pd.Series(dtype=float)).notna()
            & range_table.get("q_end", pd.Series(dtype=float)).notna()
        ].copy()
        subset["frame"] = subset.get("curve_name", pd.Series(dtype=str)).map(frame_by_curve)
        subset = subset[subset["frame"].notna()]
        for _, row in subset.sort_values(["frame", "range_track"]).iterrows():
            color, width = track_style.get(str(row.get("range_track")), ("#7f7f7f", 0.8))
            axis.plot(
                [row["q_start"], row["q_end"]],
                [row["frame"], row["frame"]],
                color=color,
                lw=width,
                alpha=0.75,
                solid_capstyle="butt",
            )
        axis.set_xscale("log")
        axis.set_xlim(HARD_Q_RANGE)
        axis.set_title(method.replace("_", " ").title())
        axis.set_xlabel(r"$q$ ($\AA^{-1}$)")
        axis.grid(True, which="both", alpha=0.18)
    axes[0].set_ylabel("True frame index")
    axes[0].plot([], [], color=track_style["adaptive"][0], lw=2, label="adaptive")
    axes[0].plot([], [], color=track_style["common"][0], lw=2, label="common")
    axes[0].legend(frameon=False, loc="best")
    fig.suptitle("Method-specific q-range tracks (hard boundary 0.01–0.5 Å⁻¹)")
    _save_research_figure(fig, figures_dir, "q_selection_heatmap")

    parameters_path = output_dir / "audit" / "all_parameters_audit.csv"
    parameters = pd.read_csv(parameters_path) if parameters_path.is_file() else pd.DataFrame()
    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.2), sharex=True)
    requested = (("guinier", "Rg", r"$R_g$ ($\AA$)"), ("power_law", "alpha", r"$\alpha$"))
    for axis, (analysis_type, parameter_name, ylabel) in zip(axes, requested):
        plotted = False
        if not parameters.empty:
            subset = parameters[
                parameters.get("analysis_type", pd.Series(dtype=str)).eq(analysis_type)
                & parameters.get("name", pd.Series(dtype=str)).eq(parameter_name)
                & parameters.get("sequence_role", pd.Series(dtype=str)).eq("series")
            ].copy()
            subset["frame"] = pd.to_numeric(subset.get("frame"), errors="coerce")
            subset["numeric_value"] = pd.to_numeric(subset.get("value"), errors="coerce")
            for track, (color, _) in track_style.items():
                track_rows = subset[subset.get("range_track", pd.Series(dtype=str)).eq(track)].sort_values("frame")
                formal = track_rows[track_rows.get("reporting_status", pd.Series(dtype=str)).eq("reportable")]
                exploratory = track_rows[~track_rows.index.isin(formal.index)]
                if formal["numeric_value"].notna().any():
                    axis.plot(formal["frame"], formal["numeric_value"], "o-", ms=3, lw=1.0, color=color, label=f"{track} formal")
                    plotted = True
                if exploratory["numeric_value"].notna().any():
                    axis.scatter(exploratory["frame"], exploratory["numeric_value"], marker="x", s=18, color=color, alpha=0.45, label=f"{track} exploratory")
                    plotted = True
        axis.set_ylabel(ylabel)
        axis.grid(True, alpha=0.2)
        if plotted:
            axis.legend(frameon=False, ncol=2, fontsize=8)
        else:
            axis.text(
                0.5,
                0.5,
                f"No reportable or exploratory {analysis_type} parameter",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
    axes[-1].set_xlabel("True frame index (gaps retained)")
    fig.suptitle("Adaptive/common parameter trajectories")
    _save_research_figure(fig, figures_dir, "dual_track_parameter_trends")

    representative_frames = []
    selected_frames = selection.selected_frame_numbers
    if selected_frames:
        representative_frames = sorted({selected_frames[0], selected_frames[len(selected_frames) // 2], selected_frames[-1]})
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.8), sharex=False, sharey=False)
    for axis, method, track in zip(
        axes.ravel(),
        ("guinier", "guinier", "power_law", "power_law"),
        ("adaptive", "common", "adaptive", "common"),
    ):
        plotted = False
        for envelope in run.analyses:
            if envelope.analysis_type != method or envelope.range_track != track:
                continue
            frame = frame_by_curve.get(envelope.curve_name)
            if frame not in representative_frames:
                continue
            rows = envelope.tables.get("residual_rows", [])
            q_values = pd.to_numeric(pd.Series([row.get("q") for row in rows]), errors="coerce")
            residuals = pd.to_numeric(pd.Series([row.get("residual") for row in rows]), errors="coerce")
            valid = q_values.notna() & residuals.notna()
            if valid.any():
                axis.plot(q_values[valid], residuals[valid], lw=0.9, label=f"frame {frame}")
                plotted = True
        axis.axhline(0.0, color="black", lw=0.7, alpha=0.6)
        axis.set_xscale("log")
        axis.set_xlabel(r"$q$ ($\AA^{-1}$)")
        axis.set_ylabel("Transformed residual")
        axis.set_title(f"{method} · {track}")
        axis.grid(True, which="both", alpha=0.18)
        if plotted:
            axis.legend(frameon=False, fontsize=8)
        else:
            axis.text(0.5, 0.5, "No executable fit", ha="center", va="center", transform=axis.transAxes)
    fig.suptitle("Residual diagnostics for representative true frames")
    _save_research_figure(fig, figures_dir, "residual_diagnostics")

    fig, axis = plt.subplots(figsize=(9.0, 4.8))
    if not parameters.empty:
        invariant = parameters[
            parameters.get("analysis_type", pd.Series(dtype=str)).eq("invariant")
            & parameters.get("name", pd.Series(dtype=str)).eq("Q_measured")
            & parameters.get("sequence_role", pd.Series(dtype=str)).eq("series")
        ].copy()
        invariant["frame"] = pd.to_numeric(invariant.get("frame"), errors="coerce")
        invariant["numeric_value"] = pd.to_numeric(invariant.get("value"), errors="coerce")
        invariant = invariant.sort_values("frame")
        axis.plot(invariant["frame"], invariant["numeric_value"], "o-", color="#2ca02c", ms=3, lw=1.0)
    axis.set_xlabel("True frame index (gaps retained)")
    axis.set_ylabel(r"Finite $Q_{0.01\leq q\leq0.5}$")
    axis.set_title("Finite-range invariant trend (not a 0–∞ invariant)")
    axis.grid(True, alpha=0.2)
    _save_research_figure(fig, figures_dir, "finite_invariant_trend")

    selected_sources = [path for _, path in selection.selected_series]
    if selected_sources:
        chosen_indices = sorted({0, len(selected_sources) // 2, len(selected_sources) - 1})
        boundary_sources = [selected_sources[index] for index in chosen_indices] + list(selection.references[:1])
    else:
        boundary_sources = list(selection.references[:1])
    fig, axis = plt.subplots(figsize=(9.2, 5.4))
    for path in boundary_sources:
        full_curve = load_curve(path, q_column=0, intensity_column=1, limit_q_range=False)
        order = np.argsort(full_curve.q)
        axis.plot(full_curve.q[order], full_curve.intensity[order], lw=0.8, label=path.stem)
    axis.axvspan(HARD_Q_RANGE[0], HARD_Q_RANGE[1], color="#4c78a8", alpha=0.12, label="analysis boundary")
    axis.axvline(HARD_Q_RANGE[0], color="#4c78a8", ls="--", lw=1.0)
    axis.axvline(HARD_Q_RANGE[1], color="#4c78a8", ls="--", lw=1.0)
    axis.axvline(
        BOUNDARY_AUDIT_PEAK_Q,
        color="#9467bd",
        ls=":",
        lw=1.2,
        label=r"boundary-audit peak $q\approx0.00925$ Å$^{-1}$",
    )
    axis.set_xscale("log")
    axis.set_yscale("symlog", linthresh=1e-6)
    axis.set_xlabel(r"$q$ ($\AA^{-1}$)")
    axis.set_ylabel(r"$I(q)$ (cm$^{-1}$)")
    axis.set_title("Full measured range and immutable analysis boundary")
    axis.grid(True, which="both", alpha=0.18)
    axis.legend(frameon=False, fontsize=7, ncol=2, loc="upper right")
    _save_research_figure(fig, figures_dir, "full_range_boundary_overview")


def write_report(
    output_dir: Path,
    run: Any,
    selection: Ti15Selection,
    integrity_ok: bool,
    workbook_status: str,
) -> None:
    scope = "完整序列" if selection.limit == 0 else f"前 {selection.limit} 帧试运行"
    fit_quality = _read_export_table(output_dir / "audit" / "fit_quality.csv")
    parameters = _read_export_table(output_dir / "audit" / "all_parameters_audit.csv")
    consensus = _read_export_table(output_dir / "audit" / "consensus_regions.csv")
    quality = _read_export_table(output_dir / "summary" / "data_quality.csv")

    gate_lines: list[str] = []
    for method in ("guinier", "power_law", "porod"):
        subset = fit_quality[
            fit_quality.get("analysis_type", pd.Series(index=fit_quality.index, dtype=str)).eq(method)
        ]
        counts = subset.get("reporting_status", pd.Series(index=subset.index, dtype=str)).value_counts()
        gate_lines.append(
            f"- {method}：正式 {int(counts.get('reportable', 0))}，探索 {int(counts.get('exploratory', 0))}，"
            f"不可报告 {int(counts.get('not_reportable', 0))}。"
        )
    power_consensus = consensus[
        consensus.get("region_type", pd.Series(index=consensus.index, dtype=str)).eq("power_law")
        & consensus.get("q_start", pd.Series(index=consensus.index)).notna()
        & consensus.get("q_end", pd.Series(index=consensus.index)).notna()
    ]
    if not power_consensus.empty:
        row = power_consensus.iloc[0]
        q_start = float(row["q_start"])
        q_end = float(row["q_end"])
        coverage = float(row["coverage"])
        gate_lines.append(
            f"- 幂律公共区间：`{q_start:.6g}–{q_end:.6g} Å⁻¹`，跨度 "
            f"`{math.log10(q_end / q_start):.3f} decade`，主序列支持率 `{coverage:.1%}`。"
        )
    gate_lines.append(
        "- 正式表不收录探索值；高 R²、拟合收敛或单独的 q⁴I 平台指标均不自动升级为结构结论。"
    )
    peak_rows = fit_quality[
        fit_quality.get("analysis_type", pd.Series(index=fit_quality.index, dtype=str)).eq("peaks")
    ]
    if not peak_rows.empty:
        not_detected = int(
            peak_rows.get("detection_status", pd.Series(index=peak_rows.index, dtype=str))
            .eq("not_detected")
            .sum()
        )
        gate_lines.append(
            f"- 峰检测：在选定区间内 {not_detected}/{len(peak_rows)} 条曲线未检出经确认峰；"
            "该表述不外推到 q<0.01 Å⁻¹。"
        )

    trend_lines: list[str] = []
    invariant = parameters[
        parameters.get("analysis_type", pd.Series(index=parameters.index, dtype=str)).eq("invariant")
        & parameters.get("name", pd.Series(index=parameters.index, dtype=str)).eq("Q_measured")
        & parameters.get("sequence_role", pd.Series(index=parameters.index, dtype=str)).eq("series")
    ].copy()
    if not invariant.empty:
        invariant["frame_numeric"] = pd.to_numeric(invariant.get("frame"), errors="coerce")
        invariant["value_numeric"] = pd.to_numeric(invariant.get("value"), errors="coerce")
        invariant = invariant.dropna(subset=["frame_numeric", "value_numeric"]).sort_values("frame_numeric")
        if not invariant.empty:
            first = invariant.iloc[0]
            last = invariant.iloc[-1]
            minimum = invariant.loc[invariant["value_numeric"].idxmin()]
            maximum = invariant.loc[invariant["value_numeric"].idxmax()]
            relative_last = (last["value_numeric"] / first["value_numeric"] - 1.0) * 100.0
            trend_lines.extend(
                [
                    f"- 有限不变量：首帧 `{first['value_numeric']:.6g}`，末帧 `{last['value_numeric']:.6g}`，"
                    f"末帧相对首帧 `{relative_last:+.2f}%`。",
                    f"- 序列最小值 `{minimum['value_numeric']:.6g}`（帧 {int(minimum['frame_numeric'])}），"
                    f"最大值 `{maximum['value_numeric']:.6g}`（帧 {int(maximum['frame_numeric'])}）。",
                    "- 上述仅为固定有限 q 区间随真实帧号的相对变化；不据此声称动力学速率、温度效应或相变机制。",
                ]
            )
    if not quality.empty:
        trend_lines.append(
            f"- 每条曲线有效点数 `{int(pd.to_numeric(quality['point_count']).min())}`；"
            f"有效区间负强度点总数 `{int(pd.to_numeric(quality['negative_intensity_count']).sum())}`。"
        )
    lines = [
        "# Ti15 SAXS 模型免费双轨分析报告",
        "",
        "## 运行范围",
        "",
        f"- 执行范围：{scope}。",
        f"- 原位主序列：本次分析 {len(selection.selected_series)} 帧；源目录共 {len(selection.all_series_frames)} 帧。",
        f"- 独立室温参考：{len(selection.references)} 条，不参与公共 q 区间共识。",
        f"- 真实帧号缺口：{', '.join(map(str, selection.missing_frames)) or '无'}。",
        f"- 硬 q 边界：`{HARD_Q_RANGE[0]:.2f}–{HARD_Q_RANGE[1]:.2f} Å⁻¹`；边界外特征不参与拟合。",
        f"- 边界审计：已知主峰约位于 `q={BOUNDARY_AUDIT_PEAK_Q:.5f} Å⁻¹`，低于下限，仅记录、不参与任何拟合。",
        "- 形状模型、P(r)、相关函数、序列动力学和 PCA 均关闭。",
        "- Guinier、幂律和 Porod 使用 adaptive/common 双轨区间；不能通过门控时保留空值和原因码。",
        "",
        "## 不确定度与解释边界",
        "",
        "- 原始 CSV 没有测量误差列，因此拟合采用 OLS，χ²不作为有测量误差支持的统计量。",
        "- 成功拟合的区间扰动与 200 次移动区块残差 bootstrap 仅称为稳健性区间，不代表仪器测量置信区间。",
        "- 只报告 `0.01–0.5 Å⁻¹` 的有限区间积分及相对变化；不称为零到无穷总不变量。",
        "- 未提供散射对比度和相分数，因此绝对比表面积与体积分数不得解释为已测得结果。",
        "- 未提供时间或温度映射，只能按真实帧号描述变化，不能解释为动力学速率或温度响应。",
        "- 主峰若位于下边界之外，只能表述为“选定区间内未检出峰”，不能表述为“样品不存在峰”。",
        "",
        "## 方法门控结果",
        "",
        *gate_lines,
        "",
        "## 有限区间序列描述",
        "",
        *(trend_lines or ["- 当前结果中没有可用的主序列有限不变量行。"]),
        "",
        "## 审计状态",
        "",
        f"- 批处理状态：`{run.status}`。",
        f"- 原始 CSV 大小、时间戳和 SHA-256 前后不变：`{'PASS' if integrity_ok else 'FAIL'}`。",
        f"- Excel 生成状态：`{workbook_status}`。",
        "- 本次不生成 ZIP，也不重新打包项目。",
        "",
        "## 主要输出",
        "",
        "- `final_results.csv`：仅用于正式汇总的可靠参数；为空并不等于分析失败。",
        "- `summary_tables.xlsx`：由 artifact-tool 导出并执行公式错误扫描。",
        "- `summary/`：自适应/公共轨参数、稳健性、数据质量、帧缺口和室温参考等汇总表。",
        "- `audit/`：全部参数、拟合质量、候选/共识区间、原因码和失败记录。",
        "- `details/`：逐曲线方法明细，所有 q 明细受硬边界约束。",
        "- `figures/`：q 选区、双轨趋势、残差、有限不变量和全测量范围边界图（PNG/SVG/PDF）。",
        "- `summary/missing_frames.csv` 与 `summary/room_temperature_reference.csv`：帧缺口和独立参考审计。",
        "- `audit/source_integrity_after_analysis.csv`：原始输入不变性核验。",
    ]
    (output_dir / "final_report_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary_workbook(
    result_dir: Path,
    *,
    node_executable: str = "node",
) -> subprocess.CompletedProcess[str]:
    """Run the artifact-tool workbook builder without compacting the result package."""

    builder = PROJECT_DIR / "scripts" / "build_summary_workbook.mjs"
    command = [node_executable, str(builder), str(result_dir)]
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Node.js was not found. Use --node-executable to provide node.exe, or use --skip-workbook."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"summary workbook generation failed: {detail}") from exc
    if not (result_dir / "summary_tables.xlsx").is_file():
        raise RuntimeError("workbook builder finished but summary_tables.xlsx was not created")
    return completed


def _next_output_dir(results_root: Path) -> Path:
    results_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = results_root / f"17_Ti15_300_2_iso_model_free_{stamp}"
    if not base.exists():
        return base
    for suffix in range(1, 100):
        candidate = base.with_name(f"{base.name}_{suffix:02d}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not allocate a new result directory below: {results_root}")


def _progress_printer(event: ProgressEvent) -> None:
    if event.total_units <= 0:
        return
    if event.completed_units == 1 or event.completed_units == event.total_units or event.completed_units % 100 == 0:
        print(
            f"PROGRESS={event.completed_units}/{event.total_units} "
            f"CURVE={event.curve_name or '-'} METHOD={event.operation}"
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run reproducible model-free dual-range analysis for the Ti15 SAXS sequence."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of earliest in-situ frames; use 0 for the complete 117-frame sequence.",
    )
    parser.add_argument(
        "--detail-level",
        choices=("slim", "usable", "all", "none"),
        default="all",
        help="Core result-package detail level. 'all' retains the complete method audit.",
    )
    parser.add_argument(
        "--allow-nonstandard-layout",
        action="store_true",
        help="Allow a dataset that is not exactly 117 frames + one RT reference + gaps 105/109/115.",
    )
    parser.add_argument(
        "--skip-workbook",
        action="store_true",
        help="Skip summary_tables.xlsx only when Node/artifact-tool is unavailable.",
    )
    parser.add_argument(
        "--node-executable",
        default="node",
        help="Node.js executable used by scripts/build_summary_workbook.mjs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    selection = discover_ti15_inputs(args.input_dir, args.limit)
    if not args.allow_nonstandard_layout:
        validate_standard_layout(selection)

    config = build_config(limit=args.limit)
    before = source_snapshot(selection)
    output_dir = _next_output_dir(args.results_root.resolve())

    print(f"INPUT_DIR={args.input_dir.resolve()}")
    print(f"SELECTED_SERIES={len(selection.selected_series)}")
    print(f"REFERENCE_CURVES={len(selection.references)}")
    print(f"MISSING_FRAMES={','.join(map(str, selection.missing_frames))}")
    print(f"HARD_Q_RANGE={HARD_Q_RANGE[0]:.12g},{HARD_Q_RANGE[1]:.12g}")

    with tempfile.TemporaryDirectory(prefix="sas_ti15_sequence_") as temp_name:
        staging = Path(temp_name)
        for source in selection.selected_paths:
            shutil.copy2(source, staging / source.name)
        run = run_auto_batch(staging, config, progress_callback=_progress_printer)

    _remap_run_sources(run, before)
    run.config_snapshot["selected_frame_numbers"] = selection.selected_frame_numbers
    run.config_snapshot["missing_series_frames"] = list(selection.missing_frames)
    run.config_snapshot["room_temperature_reference_files"] = [path.name for path in selection.references]
    run.config_snapshot["create_archives"] = False

    exported = export_result_package(run, output_dir, detail_level=args.detail_level)
    after = source_snapshot(selection)
    integrity = source_integrity_rows(before, after)
    integrity_ok = all(bool(row["unchanged_after_analysis"]) for row in integrity)
    write_sequence_audit_tables(exported, run, selection, before, integrity)
    write_workbook_compact_tables(exported)
    write_run_config(exported, run, selection)
    generate_research_figures(exported, run, selection)

    workbook_status = "SKIPPED_BY_USER" if args.skip_workbook else "PENDING"
    write_report(exported, run, selection, integrity_ok, workbook_status)
    if not args.skip_workbook:
        try:
            completed = build_summary_workbook(exported, node_executable=args.node_executable)
        except Exception as exc:
            write_report(
                exported,
                run,
                selection,
                integrity_ok,
                f"FAIL: {type(exc).__name__}: {exc}",
            )
            raise
        workbook_status = "PASS"
        if completed.stdout.strip():
            console_encoding = sys.stdout.encoding or "utf-8"
            safe_output = completed.stdout.strip().encode(
                console_encoding, "backslashreplace"
            ).decode(console_encoding)
            print(safe_output)
        write_report(exported, run, selection, integrity_ok, workbook_status)

    expected_curve_count = len(selection.selected_series) + len(selection.references)
    curve_count_ok = len(run.curves) == expected_curve_count
    print(f"RESULT_DIR={exported}")
    print(f"RUN_STATUS={run.status}")
    print(f"CURVES={len(run.curves)}")
    print(f"ANALYSES={len(run.analyses)}")
    print(f"WORKBOOK={workbook_status}")
    print(f"SOURCE_INTEGRITY={'PASS' if integrity_ok else 'FAIL'}")
    return 0 if integrity_ok and curve_count_ok and run.status != "cancelled" else 2


if __name__ == "__main__":
    raise SystemExit(main())
