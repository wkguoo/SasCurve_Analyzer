"""Per-job and full-run compute cache for automated SAS batches.

The cache is write-only for analysis isolation: it never modifies source curves.
It enables resume after a mid-batch interruption and re-export after a completed
compute phase when package export fails.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, fields
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from app import __version__ as SOFTWARE_VERSION
from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig, AutoBatchRun, ParameterValue
from app.core.data_model import CurveData


CACHE_SCHEMA_VERSION = "2"
# The executable q-range routing and envelope audit contract changed. A new
# algorithm version prevents old shared-range job results from being restored.
ANALYSIS_ALGORITHM_VERSION = "5"


def _json_default(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _safe_token(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")
    return text[:80] or "item"


def config_fingerprint(config: AutoBatchConfig) -> str:
    """Stable hash of analysis-affecting config fields."""

    payload = asdict(config)
    # Paths are normalized to strings for portability.
    encoded = json.dumps(payload, sort_keys=True, default=_json_default, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _array_fingerprint(digest: Any, name: str, values: Any | None) -> None:
    """Add a deterministic numeric-array representation to ``digest``."""

    digest.update(name.encode("utf-8"))
    if values is None:
        digest.update(b"<none>")
        return
    array = np.ascontiguousarray(np.asarray(values, dtype="<f8"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())


def curve_content_fingerprint(curve: CurveData) -> str:
    """Hash numerical content, units, and metadata that can affect analysis/export."""

    digest = hashlib.sha256()
    digest.update(CACHE_SCHEMA_VERSION.encode("ascii"))
    digest.update(str(SOFTWARE_VERSION).encode("utf-8"))
    digest.update(str(ANALYSIS_ALGORITHM_VERSION).encode("utf-8"))
    digest.update(str(curve.q_unit).encode("utf-8"))
    digest.update(str(curve.intensity_unit).encode("utf-8"))
    metadata_json = json.dumps(
        curve.metadata,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )
    digest.update(metadata_json.encode("utf-8"))
    _array_fingerprint(digest, "q", curve.q)
    _array_fingerprint(digest, "intensity", curve.intensity)
    _array_fingerprint(digest, "error", curve.error)
    return digest.hexdigest()


def job_cache_key(
    curve: CurveData,
    method_id: str,
    config: AutoBatchConfig,
    q_range: tuple[float, float] | None = None,
) -> str:
    source = Path(curve.source_file or curve.name).name
    normalized_q_range = None if q_range is None else [float(q_range[0]), float(q_range[1])]
    identity = json.dumps(
        {
            "cache_schema_version": CACHE_SCHEMA_VERSION,
            "software_version": SOFTWARE_VERSION,
            "analysis_algorithm_version": ANALYSIS_ALGORITHM_VERSION,
            "source": source,
            "curve_content": curve_content_fingerprint(curve),
            "method_id": method_id,
            "config": config_fingerprint(config),
            "q_range": normalized_q_range,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:20]
    return f"{_safe_token(source)}__{_safe_token(method_id)}__{digest}"


def _parameter_from_dict(payload: dict[str, Any]) -> ParameterValue:
    data = dict(payload)
    status = data.get("status", AnalysisStatus.SUCCESS)
    if isinstance(status, str):
        data["status"] = AnalysisStatus(status)
    allowed = {item.name for item in fields(ParameterValue)}
    return ParameterValue(**{key: value for key, value in data.items() if key in allowed})


def envelope_to_dict(envelope: AnalysisEnvelope) -> dict[str, Any]:
    payload = asdict(envelope)
    payload["status"] = envelope.status.value if isinstance(envelope.status, AnalysisStatus) else str(envelope.status)
    for parameter in payload.get("parameters", []):
        if isinstance(parameter, dict) and isinstance(parameter.get("status"), AnalysisStatus):
            parameter["status"] = parameter["status"].value
        elif isinstance(parameter, dict) and hasattr(parameter.get("status"), "value"):
            parameter["status"] = parameter["status"].value
    return payload


def envelope_from_dict(payload: dict[str, Any]) -> AnalysisEnvelope:
    data = dict(payload)
    status = data.get("status", AnalysisStatus.INVALID)
    if isinstance(status, str):
        data["status"] = AnalysisStatus(status)
    q_range = data.get("q_range")
    if isinstance(q_range, list) and len(q_range) == 2:
        data["q_range"] = (float(q_range[0]), float(q_range[1]))
    parameters = data.get("parameters") or []
    data["parameters"] = [
        _parameter_from_dict(item) if isinstance(item, dict) else item for item in parameters
    ]
    allowed = {item.name for item in fields(AnalysisEnvelope)}
    return AnalysisEnvelope(**{key: value for key, value in data.items() if key in allowed})


def save_job_envelopes(cache_dir: str | Path, key: str, envelopes: list[AnalysisEnvelope]) -> Path:
    root = Path(cache_dir)
    jobs = root / "jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    path = jobs / f"{key}.json"
    path.write_text(
        json.dumps([envelope_to_dict(item) for item in envelopes], ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return path


def load_job_envelopes(cache_dir: str | Path, key: str) -> list[AnalysisEnvelope] | None:
    path = Path(cache_dir) / "jobs" / f"{key}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not payload:
        return None
    try:
        return [envelope_from_dict(item) for item in payload if isinstance(item, dict)]
    except (TypeError, ValueError, KeyError):
        return None


def _curve_checkpoint(curve: Any) -> dict[str, Any]:
    if isinstance(curve, CurveData):
        return {
            "curve_id": curve.curve_id,
            "name": curve.name,
            "q_unit": curve.q_unit,
            "intensity_unit": curve.intensity_unit,
            "source_file": curve.source_file,
            "parent_id": curve.parent_id,
            "created_at": curve.created_at,
            "n_points": int(len(curve.q)),
            "has_error": curve.error is not None,
        }
    if isinstance(curve, dict):
        return {
            key: curve.get(key)
            for key in (
                "curve_id",
                "name",
                "q_unit",
                "intensity_unit",
                "source_file",
                "parent_id",
                "created_at",
                "n_points",
                "has_error",
            )
            if key in curve or key in {"n_points", "has_error"}
        }
    return {"repr": str(curve)}


def save_run_checkpoint(cache_dir: str | Path, run: AutoBatchRun) -> Path:
    """Persist a compute checkpoint for re-export without re-running analyses."""

    root = Path(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": run.batch_id,
        "run_id": run.run_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "curves": [_curve_checkpoint(curve) for curve in run.curves],
        "analyses": [envelope_to_dict(item) for item in run.analyses],
        "consensus_regions": {
            str(name): list(bounds) if isinstance(bounds, tuple) else bounds
            for name, bounds in (run.consensus_regions or {}).items()
        },
        "consensus_region_details": dict(run.consensus_region_details or {}),
        "candidate_windows": list(run.candidate_windows or []),
        "range_audit": list(run.range_audit or []),
        "input_manifest": list(run.input_manifest),
        "failed_inputs": list(run.failed_inputs),
        "warnings": list(run.warnings),
        "config_snapshot": dict(run.config_snapshot),
        "rankings": list(run.rankings),
        "main_model": run.main_model,
        "transition_flags": list(run.transition_flags),
        "sequence_results": dict(run.sequence_results or {}),
    }
    path = root / "run_checkpoint.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    (root / "CHECKPOINT_README.md").write_text(
        "# Batch compute checkpoint\n\n"
        "This directory stores intermediate analysis results.\n\n"
        "- `jobs/*.json`: per curve-method envelopes (resume mid-batch).\n"
        "- `run_checkpoint.json`: finished compute snapshot for re-export without recomputing.\n\n"
        "Source experimental files are never modified.\n",
        encoding="utf-8",
    )
    return path


def load_run_checkpoint(cache_dir: str | Path) -> AutoBatchRun:
    """Load a previously saved compute checkpoint for package export."""

    path = Path(cache_dir) / "run_checkpoint.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    run = AutoBatchRun(batch_id=str(payload.get("batch_id") or "restored"))
    run.run_id = str(payload.get("run_id") or run.run_id)
    run.started_at = str(payload.get("started_at") or run.started_at)
    run.finished_at = payload.get("finished_at")
    run.status = str(payload.get("status") or "pending")
    run.curves = list(payload.get("curves") or [])
    run.analyses = [
        envelope_from_dict(item) for item in payload.get("analyses") or [] if isinstance(item, dict)
    ]
    consensus = payload.get("consensus_regions") or {}
    restored_consensus: dict[str, tuple[float, float]] = {}
    if isinstance(consensus, dict):
        for name, bounds in consensus.items():
            if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
                restored_consensus[str(name)] = (float(bounds[0]), float(bounds[1]))
    run.consensus_regions = restored_consensus
    run.consensus_region_details = dict(payload.get("consensus_region_details") or {})
    run.candidate_windows = list(payload.get("candidate_windows") or [])
    run.range_audit = list(payload.get("range_audit") or [])
    run.input_manifest = list(payload.get("input_manifest") or [])
    run.failed_inputs = list(payload.get("failed_inputs") or [])
    run.warnings = list(payload.get("warnings") or [])
    run.config_snapshot = dict(payload.get("config_snapshot") or {})
    run.rankings = list(payload.get("rankings") or [])
    run.main_model = payload.get("main_model")
    run.transition_flags = list(payload.get("transition_flags") or [])
    run.sequence_results = dict(payload.get("sequence_results") or {})
    return run


__all__ = [
    "ANALYSIS_ALGORITHM_VERSION",
    "CACHE_SCHEMA_VERSION",
    "SOFTWARE_VERSION",
    "curve_content_fingerprint",
    "config_fingerprint",
    "job_cache_key",
    "load_job_envelopes",
    "load_run_checkpoint",
    "save_job_envelopes",
    "save_run_checkpoint",
]
