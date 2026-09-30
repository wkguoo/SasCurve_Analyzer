"""Headless, traceable publication-data bundle export for an auto-batch run."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.core.auto_batch_schema import AnalysisStatus, AutoBatchRun
from app.core.data_model import CurveData
from app.core.derived_data import DerivedDataOptions, build_curve_derived_table
from app.core.export import export_origin_long_csv, export_origin_matrix_csv
from app.core.result_package import export_result_package
from app.core.unit_checks import validate_compatible_curve_units
from app.core.publication_bundle_plots import export_bundle_figures
from app.core.batch_import import parse_sequence_metadata


_USABLE_STATUSES = {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}
_RELIABLE_STATUSES = {"reliable", "tentative"}

def _safe_json(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _safe_json(asdict(value))
    if isinstance(value, dict):
        return {str(key): _safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return _safe_json(value.tolist())
    if isinstance(value, np.generic):
        return _safe_json(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is pd.NA or value is pd.NaT:
        return None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _status(value: Any) -> str:
    return str(value.value if isinstance(value, Enum) else value)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_safe_json(payload), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(list(rows), columns=columns).to_csv(
        path, index=False, encoding="utf-8-sig", na_rep="", float_format="%.17g"
    )


def _token(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._-")
    return text[:48] or "unnamed"


def _stable_suffix(*parts: Any) -> str:
    identity = "|".join(str(part) for part in parts)
    return sha256(identity.encode("utf-8")).hexdigest()[:12]


def _curve_meta(curve: CurveData, input_order: int, run: AutoBatchRun) -> dict[str, Any]:
    metadata = curve.metadata or {}
    return {
        "sample_id": str(metadata.get("sample_id") or metadata.get("sample") or metadata.get("series_id") or run.batch_id),
        "series_id": metadata.get("series_id"),
        "curve_id": str(curve.curve_id),
        "curve_name": str(curve.name),
        "source_file": curve.source_file,
        "frame_index": metadata.get("frame_index"),
        "frame_label": metadata.get("frame_label"),
        "sequence_order": metadata.get("sequence_order"),
        "input_order": int(input_order),
        "q_unit": str(curve.q_unit),
        "intensity_unit": str(curve.intensity_unit),
        "error_unit": str(curve.intensity_unit),
    }


def _sort_number(value: Any) -> float | None:
    return _finite_number(value)


def _frame_order(row: dict[str, Any]) -> float:
    sequence_order = _finite_number(row.get("sequence_order"))
    return float(row.get("input_order", 0)) if sequence_order is None else sequence_order


def _ordered_curves(run: AutoBatchRun) -> list[tuple[CurveData, dict[str, Any], float | None, str]]:
    indexed = [
        (curve, _curve_meta(curve, index, run))
        for index, curve in enumerate(run.curves)
        if isinstance(curve, CurveData)
    ]
    sequence = run.sequence_results if isinstance(run.sequence_results, dict) else {}
    configured_axis = run.config_snapshot.get("sequence_axis")
    axis_name = sequence.get("sequence_axis") or configured_axis
    axis_valid = sequence.get("sequence_axis_valid")
    selected_values = [
        _sort_number((item[0].metadata or {}).get(axis_name)) if axis_name else None
        for item in indexed
    ]
    custom_axis = axis_name not in (None, "frame_index", "sequence_order")
    declared_invalid = axis_valid is False or (
        configured_axis is not None
        and (any(value is None for value in selected_values) or len(set(selected_values)) != len(selected_values))
    )
    if declared_invalid:
        axis_values = [None] * len(indexed)
        axis_source = str(axis_name)
        can_sort = False
    elif axis_name and all(value is not None for value in selected_values) and len(set(selected_values)) == len(selected_values):
        axis_values = selected_values
        axis_source = str(axis_name)
        can_sort = True
    elif custom_axis:
        # A configured physical axis is authoritative. Do not silently replace
        # it with frame order when one frame lacks or duplicates its value.
        axis_values = [None] * len(indexed)
        axis_source = str(axis_name)
        can_sort = False
    else:
        frame_values = [_sort_number(item[1].get("frame_index")) for item in indexed]
        if all(value is not None for value in frame_values) and len(set(frame_values)) == len(indexed):
            axis_values, axis_source, can_sort = frame_values, "frame_index", True
        else:
            sequence_values = [_sort_number(item[1].get("sequence_order")) for item in indexed]
            if all(value is not None for value in sequence_values) and len(set(sequence_values)) == len(indexed):
                axis_values, axis_source, can_sort = sequence_values, "sequence_order", True
            else:
                axis_values = [float(i) for i in range(len(indexed))]
                axis_source, can_sort = "input_order", True
    if can_sort:
        indexed = [item for _, item in sorted(zip(axis_values, indexed), key=lambda pair: (pair[0], pair[1][1]["input_order"]))]
        axis_values = sorted(axis_values)
    result = []
    axis_by_curve = {str(item[0].curve_id): value for item, value in zip(indexed, axis_values)}
    for curve, meta in indexed:
        result.append((curve, meta, axis_by_curve[str(curve.curve_id)], axis_source))
    return result


def _envelope_model(envelope: Any) -> str:
    if str(getattr(envelope, "analysis_type", "")) != "shape_models":
        return ""
    parts = str(getattr(envelope, "analysis_id", "")).split(":")
    return parts[-1] if len(parts) > 2 else "unspecified"


def _is_reliable_reportable(envelope: Any, parameter_status: Any) -> tuple[bool, str]:
    envelope_status = _status(getattr(envelope, "status", ""))
    if envelope_status not in _USABLE_STATUSES:
        return False, f"envelope_status:{envelope_status}"
    if _status(parameter_status) not in _USABLE_STATUSES:
        return False, f"parameter_status:{_status(parameter_status)}"
    reliability_status = str(getattr(envelope, "reliability_status", ""))
    reliability_label = str(getattr(envelope, "reliability_label", ""))
    score = _finite_number(getattr(envelope, "reliability_score", None))
    if reliability_status not in _RELIABLE_STATUSES or reliability_label in {"invalid", "low"} or score is None or score < 0.5:
        return False, "reliability_gate_not_met"
    if str(getattr(envelope, "reporting_status", "")) != "reportable":
        return False, f"reporting_status:{getattr(envelope, 'reporting_status', '')}"
    return True, ""


def _length_units_match(q_unit: str, rg_unit: str) -> bool:
    q_key = str(q_unit).strip().lower().replace("å", "a").replace("angstrom", "a")
    rg_key = str(rg_unit).strip().lower().replace("å", "a").replace("angstrom", "a")
    expected = {"a^-1": "a", "a-1": "a", "nm^-1": "nm", "nm-1": "nm"}.get(q_key)
    return expected is not None and rg_key == expected


def _dimensionless_parameters(run: AutoBatchRun, ordered: list[tuple[CurveData, dict[str, Any], float, str]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    by_curve: dict[str, list[Any]] = {}
    curve_by_id = {str(curve.curve_id): curve for curve, _, _, _ in ordered}
    for envelope in run.analyses:
        if str(getattr(envelope, "analysis_type", "")) == "guinier":
            by_curve.setdefault(str(getattr(envelope, "curve_id", "")), []).append(envelope)

    result: dict[str, dict[str, Any]] = {}
    audit: list[dict[str, Any]] = []
    for curve, meta, _, _ in ordered:
        candidates = []
        reasons: list[str] = []
        for envelope in by_curve.get(str(curve.curve_id), []):
            params = {str(getattr(item, "name", "")).lower(): item for item in getattr(envelope, "parameters", [])}
            rg = params.get("rg")
            i0 = params.get("i0")
            if rg is None or i0 is None:
                reasons.append("missing_Rg_or_I0_parameter")
                continue
            rg_value = _finite_number(getattr(rg, "value", None))
            i0_value = _finite_number(getattr(i0, "value", None))
            if rg_value is None or rg_value <= 0 or i0_value is None or i0_value <= 0:
                reasons.append("Rg_and_I0_must_be_finite_and_positive")
                continue
            rg_ok, rg_reason = _is_reliable_reportable(envelope, getattr(rg, "status", None))
            i0_ok, i0_reason = _is_reliable_reportable(envelope, getattr(i0, "status", None))
            if not rg_ok or not i0_ok:
                reasons.append(rg_reason if not rg_ok else i0_reason)
                continue
            rg_unit = str(getattr(rg, "unit", ""))
            i0_unit = str(getattr(i0, "unit", ""))
            if not _length_units_match(curve.q_unit, rg_unit):
                reasons.append("Rg_unit_incompatible_or_unknown_for_q_unit")
                continue
            if i0_unit.strip().casefold() != str(curve.intensity_unit).strip().casefold():
                reasons.append("I0_unit_mismatch_or_unknown")
                continue
            candidates.append((envelope, rg, i0, rg_value, i0_value))
        if len(candidates) == 1:
            envelope, rg, i0, rg_value, i0_value = candidates[0]
            result[str(curve.curve_id)] = {
                "Rg": rg_value,
                "Rg_unit": str(rg.unit),
                "I0": i0_value,
                "I0_unit": str(i0.unit),
                "analysis_id": str(envelope.analysis_id),
                "status": "available",
                "analysis_status": _status(envelope.status),
                "reliability_status": str(envelope.reliability_status),
                "reporting_status": str(envelope.reporting_status),
            }
            reason = ""
        elif len(candidates) > 1:
            reason = "multiple_qualifying_Guinier_envelopes"
        else:
            reason = ";".join(dict.fromkeys(reasons)) or "no_Guinier_envelope_for_frame"
        audit.append({**meta, "status": "available" if not reason else "missing_prerequisite", "reason": reason})
    return result, audit


def _planned_failed_frames(
    run: AutoBatchRun,
    ordered: list[tuple[CurveData, dict[str, Any], float | None, str]],
) -> list[dict[str, Any]]:
    imported_paths = {
        str((curve.metadata or {}).get("source_relative_path"))
        for curve, _, _, _ in ordered
        if (curve.metadata or {}).get("source_relative_path")
    }
    imported_absolute = {
        str(Path(curve.source_file).resolve())
        for curve, _, _, _ in ordered
        if curve.source_file
    }
    snapshot = run.config_snapshot or {}
    identity_overrides = snapshot.get("input_identity_overrides", {})
    planned = snapshot.get("planned_frames")
    manifest = [row for row in (run.input_manifest or []) if isinstance(row, dict)]
    if not isinstance(planned, list):
        planned = []
        for index, entry in enumerate(manifest):
            relative = str(entry.get("source_relative_path") or entry.get("source_file") or "")
            if relative in imported_paths or str(Path(str(entry.get("source_path") or "")).resolve()) in imported_absolute:
                continue
            parsed = parse_sequence_metadata(relative)
            override = identity_overrides.get(relative, {}) if isinstance(identity_overrides, dict) else {}
            row = {
                **parsed,
                "source_relative_path": relative,
                "source_file": entry.get("source_file") or Path(relative).name,
                "sequence_order": index,
            }
            if isinstance(override, dict):
                row.update(override)
            planned.append(row)

    failure_rows = [row for row in (run.failed_inputs or []) if isinstance(row, dict)]
    axis = (
        (run.sequence_results or {}).get("sequence_axis")
        if isinstance(run.sequence_results, dict)
        else None
    ) or snapshot.get("sequence_axis")
    sequence = run.sequence_results if isinstance(run.sequence_results, dict) else {}
    axis_invalid = sequence.get("sequence_axis_valid") is False
    manifest_by_relative = {
        str(row.get("source_relative_path")): row for row in manifest if row.get("source_relative_path")
    }
    output: list[dict[str, Any]] = []
    for index, item in enumerate(planned):
        if not isinstance(item, dict):
            continue
        relative = str(item.get("source_relative_path") or item.get("source_file") or "")
        if relative in imported_paths:
            continue
        source_name = str(item.get("source_file") or Path(relative).name)
        source_entry = manifest_by_relative.get(relative, {})
        source_path = source_entry.get("source_path")
        if source_path and str(Path(str(source_path)).resolve()) in imported_absolute:
            continue
        failure = next(
            (
                row for row in failure_rows
                if str(row.get("source_relative_path") or row.get("file") or "") in {relative, source_name}
                or Path(str(row.get("file") or "")).name == source_name
            ),
            {},
        )
        frame_index = item.get("frame_index")
        sequence_order = item.get("sequence_order")
        if axis_invalid:
            frame_x = None
        elif axis and axis not in {"frame_index", "sequence_order"}:
            frame_x = _finite_number(item.get(str(axis)))
        elif axis == "sequence_order":
            frame_x = _finite_number(sequence_order)
        elif axis == "frame_index":
            frame_x = _finite_number(frame_index)
        else:
            frame_x = _finite_number(frame_index)
            if frame_x is None:
                frame_x = _finite_number(sequence_order)
        if axis:
            frame_x_source = str(axis)
        else:
            frame_x_source = "frame_index" if _finite_number(frame_index) is not None else "sequence_order"
        parsed = parse_sequence_metadata(relative)
        output.append({
            "sample_id": str(item.get("sample_id") or run.batch_id),
            "series_id": item.get("series_id") or item.get("sample_id") or parsed.get("series_id"),
            "curve_id": "",
            "curve_name": Path(source_name).stem,
            "source_file": source_path or relative,
            "source_relative_path": relative,
            "frame_index": frame_index if frame_index is not None else parsed.get("frame_index"),
            "frame_label": item.get("frame_label") or parsed.get("frame_label"),
            "sequence_order": sequence_order if sequence_order is not None else index,
            "input_order": _finite_number(sequence_order) if _finite_number(sequence_order) is not None else float(len(ordered) + index),
            "q_unit": "",
            "intensity_unit": "",
            "frame_x": frame_x,
            "frame_x_source": frame_x_source,
            "status": "import_failed",
            "reason": str(failure.get("error") or source_entry.get("manifest_error") or "Input was planned but did not produce an imported curve."),
            "failure_type": failure.get("failure_type", "import_failed"),
        })
    return output


def _frame_envelope_rows(
    run: AutoBatchRun,
    ordered: list[tuple[CurveData, dict[str, Any], float | None, str]],
    failed_frames: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    curve_meta = {str(curve.curve_id): (curve, meta, x, x_source) for curve, meta, x, x_source in ordered}
    envelopes_by_key: dict[tuple[str, str, str], list[Any]] = {}
    tracks: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    shape_rows: list[dict[str, Any]] = []
    for envelope in run.analyses:
        analysis_type = str(getattr(envelope, "analysis_type", ""))
        curve_id = str(getattr(envelope, "curve_id", ""))
        model = _envelope_model(envelope)
        envelopes_by_key.setdefault((curve_id, analysis_type, model), []).append(envelope)
        if analysis_type == "shape_models":
            param_rows = envelope.tables.get("parameter_records", []) if isinstance(envelope.tables, dict) else []
            if isinstance(param_rows, list):
                for record in param_rows:
                    if not isinstance(record, dict):
                        continue
                    shape_rows.append({
                        "curve_id": curve_id,
                        "curve_name": str(envelope.curve_name),
                        "analysis_id": str(envelope.analysis_id),
                        "analysis_type": analysis_type,
                        "model_name": model,
                        "envelope_status": _status(envelope.status),
                        "reliability_status": str(envelope.reliability_status),
                        "reporting_status": str(envelope.reporting_status),
                        "reliability_label": str(envelope.reliability_label),
                        "reliability_score": _finite_number(envelope.reliability_score),
                        **_safe_json(record),
                    })
        if analysis_type == "shape_models":
            records = envelope.tables.get("parameter_records", []) if isinstance(envelope.tables, dict) else []
            if isinstance(records, list) and records:
                for record in records:
                    if isinstance(record, dict) and record.get("name") is not None:
                        key = (analysis_type, model, str(record.get("name")), str(record.get("unit", "")))
                        tracks[key] = {"name": key[2], "unit": key[3]}
            continue
        for parameter in getattr(envelope, "parameters", []):
            name = str(getattr(parameter, "name", ""))
            unit = str(getattr(parameter, "unit", ""))
            if name:
                key = (analysis_type, model, name, unit)
                tracks[key] = {"name": name, "unit": unit}

    evolution_rows: list[dict[str, Any]] = []
    for curve, meta, frame_x, frame_x_source in ordered:
        for (analysis_type, model, parameter_name, unit), _track in sorted(tracks.items()):
            matching = envelopes_by_key.get((str(curve.curve_id), analysis_type, model), [])
            if not matching:
                evolution_rows.append({
                    **meta, "frame_x": frame_x, "frame_x_source": frame_x_source,
                    "analysis_id": "", "analysis_type": analysis_type, "model_name": model,
                    "parameter_name": parameter_name, "value": None, "value_json": "null", "unit": unit,
                    "parameter_status": "missing_analysis_envelope", "invalid_reason": "No envelope for this curve/method/model.",
                    "envelope_status": "missing_analysis_envelope", "execution_status": "not_run",
                    "candidate_status": "not_evaluated", "consensus_status": "not_required",
                    "detection_status": "not_evaluated", "reliability_status": "not_evaluated",
                    "reporting_status": "not_evaluated", "reporting_reason_codes": "",
                    "reliability_label": "invalid", "reliability_score": 0.0,
                    "q_start": None, "q_end": None, "reliable_reportable": False,
                    "reliability_gate_reason": "missing_analysis_envelope",
                    "stderr": None, "ci95_low": None, "ci95_high": None,
                    "initial": None, "lower_bound": None, "upper_bound": None, "bound_hit": None,
                })
                continue
            for envelope in matching:
                if analysis_type == "shape_models":
                    source_params = [row for row in envelope.tables.get("parameter_records", []) if isinstance(row, dict) and str(row.get("name")) == parameter_name] if isinstance(envelope.tables, dict) else []
                    if not source_params:
                        source_params = [{"name": parameter_name, "value": None, "unit": unit, "reason": "parameter_record_missing"}]
                    params = [
                        (row.get("value"), row.get("unit", unit), _status(envelope.status), row.get("reason"), row)
                        for row in source_params
                    ]
                else:
                    matching_params = [p for p in getattr(envelope, "parameters", []) if str(getattr(p, "name", "")) == parameter_name and str(getattr(p, "unit", "")) == unit]
                    if not matching_params:
                        params = [(None, unit, "missing_parameter", "Parameter record missing.", None)]
                    else:
                        params = [
                            (getattr(p, "value", None), str(getattr(p, "unit", unit)), _status(getattr(p, "status", "")), getattr(p, "invalid_reason", None), p)
                            for p in matching_params
                        ]
                for raw_value, raw_unit, parameter_status, invalid_reason, raw_record in params:
                    safe_value = _safe_json(raw_value)
                    numeric_value = _finite_number(raw_value)
                    eligible, gate_reason = _is_reliable_reportable(envelope, parameter_status)
                    bound_hit = raw_record.get("bound_hit") if isinstance(raw_record, dict) else getattr(raw_record, "bound_hit", None)
                    if eligible and bound_hit is True:
                        eligible, gate_reason = False, "parameter_bound_hit"
                    if numeric_value is None and eligible:
                        eligible, gate_reason = False, "parameter_value_not_finite_numeric"
                    q_range = getattr(envelope, "q_range", None)
                    def parameter_field(name: str) -> Any:
                        return raw_record.get(name) if isinstance(raw_record, dict) else getattr(raw_record, name, None)
                    evolution_rows.append({
                        **meta, "frame_x": frame_x, "frame_x_source": frame_x_source,
                        "analysis_id": str(envelope.analysis_id), "analysis_type": analysis_type, "model_name": model,
                        "parameter_name": parameter_name, "value": numeric_value,
                        "value_json": json.dumps(safe_value, ensure_ascii=False, allow_nan=False), "unit": str(raw_unit),
                        "parameter_status": parameter_status, "invalid_reason": _safe_json(invalid_reason),
                        "envelope_status": _status(envelope.status), "execution_status": str(envelope.execution_status),
                        "candidate_status": str(envelope.candidate_status), "consensus_status": str(envelope.consensus_status),
                        "detection_status": str(envelope.detection_status), "reliability_status": str(envelope.reliability_status),
                        "reporting_status": str(envelope.reporting_status),
                        "reporting_reason_codes": " | ".join(str(item) for item in envelope.reporting_reason_codes),
                        "reliability_label": str(envelope.reliability_label), "reliability_score": _finite_number(envelope.reliability_score),
                        "q_start": None if q_range is None else _finite_number(q_range[0]),
                        "q_end": None if q_range is None else _finite_number(q_range[1]),
                        "reliable_reportable": eligible, "reliability_gate_reason": gate_reason,
                        "stderr": _finite_number(parameter_field("stderr")),
                        "ci95_low": _finite_number(parameter_field("ci95_low")),
                        "ci95_high": _finite_number(parameter_field("ci95_high")),
                        "initial": _finite_number(parameter_field("initial")),
                        "lower_bound": _finite_number(parameter_field("lower_bound")),
                        "upper_bound": _finite_number(parameter_field("upper_bound")),
                        "bound_hit": _safe_json(bound_hit),
                    })
    for frame in failed_frames or []:
        for analysis_type, model, parameter_name, unit in sorted(tracks):
            evolution_rows.append({
                **frame,
                "analysis_id": "",
                "analysis_type": analysis_type,
                "model_name": model,
                "parameter_name": parameter_name,
                "value": None,
                "value_json": "null",
                "unit": unit,
                "parameter_status": "import_failed",
                "invalid_reason": frame["reason"],
                "envelope_status": "import_failed",
                "execution_status": "not_run",
                "candidate_status": "not_evaluated",
                "consensus_status": "not_run",
                "detection_status": "not_run",
                "reliability_status": "not_evaluated",
                "reporting_status": "not_evaluated",
                "reporting_reason_codes": "input_import_failed",
                "reliability_label": "invalid",
                "reliability_score": 0.0,
                "q_start": None,
                "q_end": None,
                "reliable_reportable": False,
                "reliability_gate_reason": "input_import_failed",
                "stderr": None,
                "ci95_low": None,
                "ci95_high": None,
                "initial": None,
                "lower_bound": None,
                "upper_bound": None,
                "bound_hit": None,
            })
    return evolution_rows, shape_rows


def _zip_paths(path: Path, members: list[tuple[Path, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, archive_name in members:
            archive.write(source, archive_name)


def _tree_files(root: Path) -> list[Path]:
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix())


def _hash_manifest_files(stage: Path) -> list[dict[str, Any]]:
    result = []
    for path in _tree_files(stage):
        if path.name == "package_manifest.json":
            continue
        digest = sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result.append({
            "path": path.relative_to(stage).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        })
    return result


def _copy_source_inputs(run: AutoBatchRun, data_dir: Path) -> list[dict[str, Any]]:
    source_dir = data_dir / "source_inputs"
    copied: list[dict[str, Any]] = []
    manifest_rows = list(run.input_manifest or [])
    failures = list(run.failed_inputs or [])
    for position, entry in enumerate(manifest_rows):
        if not isinstance(entry, dict):
            copied.append({"manifest_index": position, "copy_status": "invalid_manifest_entry", "manifest_entry": _safe_json(entry)})
            continue
        source_path_value = entry.get("source_path")
        relative_path = str(entry.get("source_relative_path") or entry.get("source_file") or f"input_{position}")
        expected_hash = str(entry.get("sha256") or "").strip().lower()
        row = {"manifest_index": position, **_safe_json(entry), "archive_path": None, "copy_sha256": None, "copy_status": "not_copied"}
        if not source_path_value:
            row["copy_status"] = "missing_source_path"
            copied.append(row)
            continue
        source = Path(str(source_path_value))
        if not source.is_file():
            row["copy_status"] = "source_unavailable"
            copied.append(row)
            continue
        relative_hash = sha256(relative_path.encode("utf-8")).hexdigest()[:12]
        destination_name = f"{relative_hash}_{_token(Path(relative_path).name)}"
        destination = source_dir / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        digest = sha256()
        with destination.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        copied_hash = digest.hexdigest()
        if expected_hash and copied_hash != expected_hash:
            raise ValueError(
                f"Source input hash mismatch for '{relative_path}': manifest={expected_hash}, copied={copied_hash}."
            )
        row.update({
            "archive_path": destination.relative_to(data_dir).as_posix(),
            "copy_sha256": copied_hash,
            "copy_status": "verified" if expected_hash else "copied_manifest_hash_missing",
        })
        copied.append(row)
    _write_json(source_dir / "raw_input_manifest.json", {
        "input_manifest": manifest_rows,
        "failed_inputs": failures,
        "copied_inputs": copied,
    })
    _write_csv(source_dir / "source_input_index.csv", copied)
    return copied


def _validate_options(formats: tuple[str, ...], dpi: int, max_overlay_curves: int) -> tuple[str, ...]:
    allowed = {"png", "svg", "pdf"}
    normalized = tuple(str(item).lower().lstrip(".") for item in formats)
    if not normalized or any(item not in allowed for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("formats must contain unique values from png, svg, and pdf")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 1:
        raise ValueError("dpi must be a positive integer")
    if isinstance(max_overlay_curves, bool) or not isinstance(max_overlay_curves, int) or max_overlay_curves < 1:
        raise ValueError("max_overlay_curves must be a positive integer")
    return normalized


def export_publication_bundle(
    run: AutoBatchRun,
    output_dir: str | Path,
    *,
    formats: tuple[str, ...] = ("png", "svg", "pdf"),
    dpi: int = 200,
    max_overlay_curves: int = 24,
) -> Path:
    """Export one sample's data, analyses, numeric evolution, and figures atomically.

    The destination must not exist. All artifacts are written to a sibling staging
    directory and become visible together only after the complete manifest is written.
    """

    selected_formats = _validate_options(formats, dpi, max_overlay_curves)
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(f"Publication bundle target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent))
    try:
        data_dir = staging / "data"
        figures_dir = staging / "figures"
        data_dir.mkdir()
        figures_dir.mkdir()
        ordered = _ordered_curves(run)
        curves = [item[0] for item in ordered]
        validate_compatible_curve_units(curves, operation="publication bundle overview")

        analysis_path = export_result_package(run, staging / "analysis", detail_level="all")
        source_copies = _copy_source_inputs(run, data_dir)
        export_origin_long_csv(curves, data_dir / "curves_long.csv")
        matrix_compatible = bool(curves)
        matrix_reason = ""
        if curves:
            q_reference = np.sort(np.asarray(curves[0].q, dtype=float))
            for curve in curves[1:]:
                if curve.q_unit != curves[0].q_unit or curve.intensity_unit != curves[0].intensity_unit:
                    matrix_compatible = False
                    matrix_reason = "Curve units differ; a shared matrix would hide unit differences."
                    break
                if curve.q.shape != q_reference.shape or not np.array_equal(np.sort(np.asarray(curve.q, dtype=float)), q_reference):
                    matrix_compatible = False
                    matrix_reason = "Q grids are not exactly equal; no interpolation was performed."
                    break
        if matrix_compatible:
            matrix_path, matrix_warnings = export_origin_matrix_csv(curves, data_dir / "curves_matrix.csv")
            matrix_reason = " | ".join(matrix_warnings)
            if matrix_path is None:
                matrix_compatible = False
        _write_json(data_dir / "matrix_status.json", {
            "included": matrix_compatible,
            "file": "curves_matrix.csv" if matrix_compatible else None,
            "reason": matrix_reason,
            "compatibility_rule": "exact sorted q equality and identical q/intensity unit labels; no interpolation",
        })

        transformed_dir = data_dir / "transformed"
        transformed_dir.mkdir(parents=True)
        curve_metadata = []
        for curve, meta, _, _ in ordered:
            derived = build_curve_derived_table(
                curve,
                options=DerivedDataOptions(include_optional_parameter_warnings=False),
                preserve_input_order=True,
            )
            table = derived.table.copy()
            table.insert(0, "sample_id", meta["sample_id"])
            table.insert(1, "series_id", meta["series_id"])
            table.insert(2, "source_file", meta["source_file"])
            table.insert(3, "frame_index", meta["frame_index"])
            table.insert(4, "frame_label", meta["frame_label"])
            table.insert(5, "sequence_order", meta["sequence_order"])
            transformed_path = transformed_dir / f"{_token(curve.name)}_{_stable_suffix(curve.curve_id)}.csv"
            table.to_csv(transformed_path, index=False, encoding="utf-8-sig", na_rep="", float_format="%.17g")
            curve_metadata.append({
                **meta,
                "file": transformed_path.relative_to(staging).as_posix(),
                "rows": len(table),
                "column_units": derived.units,
                "formulas": derived.formulas,
                "warnings": derived.warnings,
                "metadata": derived.metadata,
            })
        _write_json(data_dir / "transformed_metadata.json", {
            "description": "Per-frame, input-order derived coordinates. Original q, I, errors, and invalid-value flags are retained.",
            "columns_by_curve": curve_metadata,
            "no_interpolation": True,
            "no_smoothing": True,
            "no_background_subtraction": True,
            "no_unit_conversion": True,
        })
        _write_json(data_dir / "curve_source_coverage.json", {
            "description": "curves_long and transformed tables use the in-run curves. For auto-batch runs these may be restricted to the configured common q interval.",
            "source_files_copied": len([row for row in source_copies if row.get("copy_status") in {"verified", "copied_manifest_hash_missing"}]),
            "source_files_unavailable": [row for row in source_copies if row.get("copy_status") not in {"verified", "copied_manifest_hash_missing"}],
            "curves": [
                {
                    "curve_id": meta["curve_id"],
                    "source_file": curve.source_file,
                    "source_relative_path": (curve.metadata or {}).get("source_relative_path"),
                    "source_sha256": (curve.metadata or {}).get("source_sha256"),
                    "source_q_unit": (curve.metadata or {}).get("source_q_unit"),
                    "q_unit": curve.q_unit,
                    "q_unit_conversion_factor": (curve.metadata or {}).get("q_unit_conversion_factor"),
                    "import_q_range_filter": (curve.metadata or {}).get("import_q_range_filter"),
                    "points_in_run_curve": int(np.asarray(curve.q).size),
                }
                for curve, meta, _, _ in ordered
            ],
        })

        dimensionless, prerequisites = _dimensionless_parameters(run, ordered)
        _write_csv(data_dir / "dimensionless_kratky_prerequisites.csv", prerequisites)
        failed_frames = _planned_failed_frames(run, ordered)
        _write_csv(data_dir / "failed_frame_index.csv", failed_frames)
        evolution_rows, model_parameter_rows = _frame_envelope_rows(run, ordered, failed_frames)
        _write_csv(data_dir / "analysis_evolution.csv", evolution_rows)
        _write_csv(data_dir / "model_parameter_records.csv", model_parameter_rows)
        figure_rows, overview_warnings, dimensionless_plot_rows = export_bundle_figures(
            run, ordered, dimensionless, evolution_rows, stage=staging, formats=selected_formats,
            dpi=dpi, max_overlay_curves=max_overlay_curves,
        )
        _write_csv(data_dir / "dimensionless_kratky.csv", dimensionless_plot_rows)
        _write_csv(figures_dir / "figure_index.csv", figure_rows)
        _write_csv(data_dir / "plot_warnings.csv", overview_warnings)

        _write_json(staging / "analysis_envelopes.json", {
            "batch_id": run.batch_id,
            "run_id": run.run_id,
            "run_status": run.status,
            "analyses": run.analyses,
            "sequence_results": run.sequence_results,
            "rankings": run.rankings,
            "transition_flags": run.transition_flags,
            "range_audit": run.range_audit,
            "consensus_regions": run.consensus_regions,
            "consensus_region_details": run.consensus_region_details,
        })
        (staging / "README.md").write_text(
            "# SAS sample analysis bundle\n\n"
            f"- Sample/batch: `{run.batch_id}`\n- Run ID: `{run.run_id}`\n- Run status: `{run.status}`\n"
            f"- Curves/frames: {len(curves)}\n- Analysis envelopes: {len(run.analyses)}\n"
            f"- Figure formats: {', '.join(selected_formats)}\n\n"
            "## Contents\n\n"
            "- `data/curves_long.csv`: imported points with curve and frame identity.\n"
            "- `data/curves_matrix.csv`: included only for exact common q grids and matching units.\n"
            "- `data/source_inputs/`: exact input copies verified against the run manifest where hashes are available; see `raw_input_manifest.json`.\n"
            "- `data/transformed/`: per-frame derived values, source errors, and validity flags.\n"
            "- `data/analysis_evolution.csv`: every recorded metric, including failed/null values and reporting gates.\n"
            "- `data/failed_frame_index.csv`: planned inputs that failed import, retained as null-valued trajectory rows.\n"
            "- `data/model_parameter_records.csv`: shape-model parameter records kept separate by model.\n"
            "- `data/plot_sources/`: exact coordinates supplied to each exported figure.\n"
            "- `figures/figure_index.csv`: one row per image format, linked to its source CSV and warnings.\n"
            f"- `{analysis_path.name}/`: existing full result package (`detail_level=all`).\n"
            "- `analysis_envelopes.json`: full analysis envelopes and sequence/audit context.\n"
            "- `data_bundle.zip` and `figures_bundle.zip`: portable data/analysis and figure collections.\n\n"
            "`curves_long.csv` and transformed CSV files contain the in-run curves and may be limited to the configured common q interval; `source_inputs/` carries the complete copied measurement files. "
            "Dimensionless Kratky views require a unique, positive, reliable and reportable Guinier Rg/I0 pair with compatible unit labels. "
            "P(r) and correlation views are drawn only from tables supplied by the completed analyses; this exporter does not infer a particle-size distribution or synthesize missing 2D data. "
            "Plots show screened coordinates only. Failed or gated metrics remain in the numeric tables, and a plotted NaN preserves a gap in reliable-only trajectories. "
            "Exploratory parameter plots use hollow markers and explicit candidate labels without upgrading reporting status; repeated local features are shown as unconnected points.\n",
            encoding="utf-8",
        )

        data_members = []
        data_members.extend((path, path.relative_to(staging).as_posix()) for path in _tree_files(data_dir))
        data_members.extend((path, path.relative_to(staging).as_posix()) for path in _tree_files(analysis_path))
        data_members.append((staging / "analysis_envelopes.json", "analysis_envelopes.json"))
        _zip_paths(staging / "data_bundle.zip", data_members)
        figure_members = [
            (path, path.relative_to(staging).as_posix())
            for path in _tree_files(figures_dir)
            if path.name != "figure_index.csv"
        ]
        figure_members.extend(
            (path, path.relative_to(staging).as_posix())
            for path in _tree_files(data_dir / "plot_sources")
        )
        figure_members.append((figures_dir / "figure_index.csv", "figures/figure_index.csv"))
        _zip_paths(staging / "figures_bundle.zip", figure_members)

        manifest = {
            "schema": "sascurve.publication_bundle.v1",
            "status": "complete",
            "package_scope": "export_complete; scientific interpretation remains subject to each analysis gate",
            "batch_id": run.batch_id,
            "run_id": run.run_id,
            "run_status": run.status,
            "curve_count": len(curves),
            "analysis_envelope_count": len(run.analyses),
            "figure_count": len(figure_rows),
            "formats": list(selected_formats),
            "matrix_included": matrix_compatible,
            "dimensionless_kratky_frames": len(dimensionless),
            "manifest_self_hash": "omitted because a file cannot contain its own stable hash",
            "files": _hash_manifest_files(staging),
        }
        _write_json(staging / "package_manifest.json", manifest)
        if target.exists():
            raise FileExistsError(f"Publication bundle target appeared during export: {target}")
        os.rename(staging, target)
        return target
    except Exception as exc:
        if staging.exists():
            try:
                _write_json(staging / "export_failure.json", {
                    "status": "incomplete", "target": str(target),
                    "error": str(exc) or type(exc).__name__, "batch_id": run.batch_id,
                })
            except OSError:
                pass
        raise


__all__ = ["export_publication_bundle"]
