"""Headless, sample-isolated studies over read-only calibrated 1D SAS files."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, fields, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import numpy as np
import pandas as pd

from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AutoBatchConfig, ProgressEvent
from app.core.batch_import import natural_sort_key, parse_sequence_metadata
from app.core.batch_inputs import SUPPORTED_CURVE_EXTENSIONS, collect_batch_inputs, sha256_file
from app.core.batch_cache import ANALYSIS_ALGORITHM_VERSION, CACHE_SCHEMA_VERSION, SOFTWARE_VERSION
from app.core.analysis_preflight import check_analysis_preflight
from app.core.data_model import utc_now_iso
from app.core.shape_models import MODEL_SPECS
from app.core.transforms import normalize_q_unit
from app.core.unit_checks import validate_compatible_curve_units
from app.core.io import TableReadCache


@dataclass(frozen=True)
class SampleInput:
    sample_id: str
    files: tuple[Path, ...]
    identity_source: str


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json_atomic(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex[:8]}.tmp")
    temporary.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _analysis_config(values: dict[str, Any], sample_id: str) -> AutoBatchConfig:
    allowed = {field.name for field in fields(AutoBatchConfig)} - {"batch_id"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Unknown analysis settings: {sorted(unknown)}")
    defaults = AutoBatchConfig(batch_id=sample_id)
    for name, value in values.items():
        default = getattr(defaults, name)
        if isinstance(default, bool) and not isinstance(value, bool):
            raise ValueError(f"{name} must be boolean")
        if isinstance(default, int) and not isinstance(default, bool) and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{name} must be an integer")
        if isinstance(default, float) and (isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value)):
            raise ValueError(f"{name} must be a finite number")
        if isinstance(default, str) and not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
    for name in ("contrast", "volume_fraction", "q_ref", "pr_dmax"):
        value = values.get(name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value)):
            raise ValueError(f"{name} must be finite or null")
    for name in ("metadata_path", "q_unit_override", "intensity_unit_override", "sequence_axis", "reference_curve_id"):
        if values.get(name) is not None and not isinstance(values[name], str):
            raise ValueError(f"{name} must be a string or null")
    models = values.get("allowed_models", [])
    if not isinstance(models, list) or any(not isinstance(model, str) or model not in MODEL_SPECS for model in models):
        raise ValueError("allowed_models must list registered model names")
    if values.get("sample_type", "unknown") not in {"unknown", "particle", "polymer", "two_phase", "lamellar"}:
        raise ValueError("Unknown sample_type")
    if values.get("q_unit_override"):
        normalize_q_unit(values["q_unit_override"])
    if values.get("contrast") is not None and values["contrast"] <= 0:
        raise ValueError("contrast must be positive")
    if values.get("volume_fraction") is not None and not 0 < values["volume_fraction"] < 1:
        raise ValueError("volume_fraction must be in (0, 1)")
    if values.get("q_ref") is not None and values["q_ref"] <= 0:
        raise ValueError("q_ref must be positive")
    if values.get("reference_mode") == "selected":
        raise ValueError("Headless studies use reference_mode first or previous; curve UUIDs change on import")
    return AutoBatchConfig(batch_id=sample_id, **values)


def validate_study_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if config is not None and not isinstance(config, dict):
        raise ValueError("Study config must be an object")
    config = dict(config or {})
    unknown = set(config) - {"schema_version", "grouping", "sample_regex", "analysis", "samples", "figures"}
    if unknown:
        raise ValueError(f"Unknown study settings: {sorted(unknown)}")
    if isinstance(config.get("schema_version"), bool) or config.get("schema_version", 1) != 1:
        raise ValueError("Unsupported study schema_version")
    if config.get("grouping", "auto") not in {"auto", "directory", "filename", "metadata"}:
        raise ValueError("grouping must be auto, directory, filename, or metadata")
    pattern = config.get("sample_regex")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise ValueError("sample_regex must be a string")
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid sample_regex: {exc}") from exc
        if not {"sample", "frame"} <= set(compiled.groupindex):
            raise ValueError("sample_regex must contain named sample and frame groups")
    analysis = config.get("analysis", {})
    samples = config.get("samples", {})
    figures = config.get("figures", {})
    if not all(isinstance(value, dict) for value in (analysis, samples, figures)):
        raise ValueError("analysis, samples and figures must be objects")
    _analysis_config(analysis, "validation")
    for sample_id, overrides in samples.items():
        if not isinstance(overrides, dict):
            raise ValueError(f"samples.{sample_id} must contain analysis overrides")
        _analysis_config({**analysis, **overrides}, str(sample_id))
    if set(figures) - {"formats", "dpi", "max_overlay_curves"}:
        raise ValueError("Unknown figure setting")
    formats = figures.get("formats", ["png", "svg", "pdf"])
    if not isinstance(formats, list) or not formats or any(f not in {"png", "svg", "pdf"} for f in formats) or len(set(formats)) != len(formats):
        raise ValueError("Figure formats must be unique png, svg, or pdf values")
    for name, default, low, high in (("dpi", 200, 72, 1200), ("max_overlay_curves", 24, 1, 100)):
        value = figures.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return config


def _metadata_assignments(root: Path, files: list[Path], config: dict[str, Any]) -> dict[Path, str]:
    analysis = config.get("analysis", {})
    metadata_path = analysis.get("metadata_path")
    if not metadata_path:
        return {}
    match_column = analysis.get("metadata_match_column", "source_file")
    metadata = pd.read_csv(metadata_path, dtype={"sample_id": str, match_column: str}, keep_default_na=False)
    has_sample_id = "sample_id" in metadata
    if match_column not in metadata:
        raise ValueError(f"Metadata match column not found: {match_column}")
    by_relative = {path.relative_to(root).as_posix(): path for path in files}
    by_basename: dict[str, list[Path]] = {}
    for path in files:
        by_basename.setdefault(path.name, []).append(path)
    assigned: dict[Path, str] = {}
    matched_paths: set[Path] = set()
    for _, row in metadata.iterrows():
        if pd.isna(row[match_column]):
            continue
        key = str(row[match_column]).strip().replace("\\", "/")
        path = by_relative.get(key)
        if path is None:
            matches = by_basename.get(key, [])
            if len(matches) > 1:
                raise ValueError(f"Ambiguous metadata basename: {key}; use paths relative to input root")
            path = matches[0] if matches else None
        if path is None:
            continue
        if path in matched_paths:
            raise ValueError(f"Duplicate metadata identity: {key}")
        matched_paths.add(path)
        if not has_sample_id:
            continue
        if pd.isna(row["sample_id"]) or not str(row["sample_id"]).strip():
            raise ValueError(f"Missing sample_id for {key}")
        assigned[path] = str(row["sample_id"]).strip()
    if has_sample_id and not assigned:
        raise ValueError("Configured sample_id metadata did not match any discovered curve")
    return assigned


def discover_study(input_dir: str | Path, config: dict[str, Any] | None = None) -> list[SampleInput]:
    config = validate_study_config(config)
    root = Path(input_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("input_dir must be a directory")
    sidecars = {Path(values["metadata_path"]).resolve() for values in [config.get("analysis", {}), *config.get("samples", {}).values()] if values.get("metadata_path")}
    files = [p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_CURVE_EXTENSIONS and p.resolve() not in sidecars]
    if not files:
        raise ValueError("No calibrated .csv/.txt/.dat curve files found")
    if any(not path.is_relative_to(root) for path in files) or len(set(files)) != len(files):
        raise ValueError("Curve links must stay within input root and must not duplicate a source")
    files.sort(key=lambda path: natural_sort_key(path.relative_to(root).as_posix()))
    assignments = _metadata_assignments(root, files, config)
    grouping = config.get("grouping", "auto")
    pattern = re.compile(config["sample_regex"]) if config.get("sample_regex") else None
    groups: dict[tuple[str, str], list[Path]] = {}
    for path in files:
        if grouping == "metadata" or grouping == "auto" and assignments:
            if path not in assignments:
                raise ValueError(f"Missing metadata sample identity: {path.relative_to(root)}")
            identity, source = assignments[path], "metadata.sample_id"
        elif pattern:
            match = pattern.fullmatch(path.stem)
            if match is None or not match["sample"].strip() or not match["frame"].isdigit():
                raise ValueError(f"Filename does not match sample_regex: {path.name}")
            identity, source = match["sample"], "sample_regex"
        elif grouping == "directory" or grouping == "auto" and path.parent != root:
            identity = path.parent.relative_to(root).as_posix() if path.parent != root else root.name
            source = "relative_directory"
        else:
            parsed = parse_sequence_metadata(path)
            if parsed["frame_index"] is None:
                raise ValueError(f"Ambiguous sample/frame identity: {path.name}; use sample_regex, metadata or directory grouping")
            identity, source = str(parsed["series_id"]), "filename_sequence"
        if not identity.strip():
            raise ValueError(f"Ambiguous sample identity: {path.name}; use directory grouping or explicit metadata")
        groups.setdefault((identity, source), []).append(path)
    if len({key[0] for key in groups}) != len(groups):
        raise ValueError("Sample identity collides across grouping sources; use explicit metadata")
    unused = set(config.get("samples", {})) - {key[0] for key in groups}
    if unused:
        raise ValueError(f"Configuration references unknown samples: {sorted(unused)}")
    return [SampleInput(identity, tuple(groups[(identity, source)]), source) for identity, source in sorted(groups, key=lambda key: natural_sort_key(key[0]))]


def _sample_directory(sample_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", sample_id).strip("._")[:48] or "sample"
    return f"{name}-{sha256(sample_id.encode()).hexdigest()[:8]}"


def _snapshot(samples: list[SampleInput], root: Path, config: dict[str, Any]) -> dict[str, Any]:
    inputs = [{"sample_id": sample.sample_id, "source_file": path.relative_to(root).as_posix(), "sha256": sha256_file(path), "size_bytes": path.stat().st_size} for sample in samples for path in sample.files]
    sidecars = sorted({str(Path(values["metadata_path"]).resolve()) for values in [config.get("analysis", {}), *config.get("samples", {}).values()] if values.get("metadata_path")})
    metadata = [{"path": path, "sha256": sha256_file(path)} for path in sidecars]
    return {"input_root": str(root), "config": config, "inputs": inputs, "metadata": metadata,
            "software_version": SOFTWARE_VERSION, "algorithm_version": ANALYSIS_ALGORITHM_VERSION,
            "cache_schema_version": CACHE_SCHEMA_VERSION, "study_algorithm_version": 1}


def _output_inventory(root: Path) -> list[dict[str, Any]]:
    return [{"file": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in sorted(root.rglob("*")) if path.is_file()]


def _verify_inventory(root: Path, inventory: list[dict[str, Any]]) -> bool:
    if not inventory or not root.is_dir():
        return False
    if {row["file"] for row in inventory} != {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}:
        return False
    for row in inventory:
        path = (root / row["file"]).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            return False
    return True


def _resolve_sample_config(
    sample: SampleInput, root: Path, settings: dict[str, Any],
    table_cache: TableReadCache | None = None,
) -> AutoBatchConfig:
    values = {**settings.get("analysis", {}), **settings.get("samples", {}).get(sample.sample_id, {})}
    config = _analysis_config(values, sample.sample_id)
    # Preview full measured data once to choose a shared domain, not an arbitrary
    # fixed window. Every per-sample integral then has the same q limits.
    preview = collect_batch_inputs(
        root, replace(config, effective_q_range=(0.0, float(np.finfo(float).max)), metadata_path=None),
        input_paths=sample.files,
        **({"table_cache": table_cache} if table_cache is not None else {}),
    )
    if not preview.curves:
        return config  # runner exports all import failures in an auditable package
    validate_compatible_curve_units(preview.curves, operation="sample study")
    if "effective_q_range" not in values:
        bounds = []
        for curve in preview.curves:
            valid = np.isfinite(curve.q) & np.isfinite(curve.intensity) & (curve.q > 0)
            if np.count_nonzero(valid) >= 2:
                bounds.append((float(np.min(curve.q[valid])), float(np.max(curve.q[valid]))))
        if bounds:
            low, high = max(row[0] for row in bounds), min(row[1] for row in bounds)
            if low >= high:
                raise ValueError("No shared measured q range; specify separate samples or an effective_q_range")
            config = replace(config, effective_q_range=(low, high))
    return config


def _input_metadata(sample: SampleInput, root: Path, settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output = {}
    for path in sample.files:
        row = {"sample_id": sample.sample_id, "series_id": sample.sample_id, "identity_source": sample.identity_source}
        if sample.identity_source == "sample_regex":
            match = re.fullmatch(settings["sample_regex"], path.stem)
            assert match is not None
            row.update(frame_index=int(match["frame"]), frame_label=match["frame"])
        output[path.relative_to(root).as_posix()] = row
    return output


def _planned_frames(sample: SampleInput, root: Path, settings: dict[str, Any], config: AutoBatchConfig) -> list[dict[str, Any]]:
    """Keep frames that fail import visible in evolution exports."""
    sidecar = pd.read_csv(config.metadata_path, dtype={"sample_id": str, config.metadata_match_column: str}, keep_default_na=False) if config.metadata_path else None
    overrides = _input_metadata(sample, root, settings)
    rows = []
    for order, path in enumerate(sample.files):
        relative = path.relative_to(root).as_posix()
        parsed = parse_sequence_metadata(path)
        row = {"source_relative_path": relative, "source_file": path.name, "sample_id": sample.sample_id,
               "frame_index": parsed.get("frame_index"), "sequence_order": order}
        if sidecar is not None:
            keys = sidecar[config.metadata_match_column].astype(str).str.replace("\\", "/", regex=False)
            matches = sidecar[keys == relative]
            if matches.empty and sum(p.name == path.name for p in sample.files) == 1:
                matches = sidecar[keys == path.name]
            if len(matches) == 1:
                values = matches.iloc[0].to_dict()
                for name in ("frame_index", config.sequence_axis):
                    if name and name in values:
                        row[name] = _json_safe(values[name])
        row.update(overrides[relative])
        rows.append(row)
    return rows


def _preflight_rows(run) -> list[dict[str, Any]]:
    curves = {curve.curve_id: curve for curve in run.curves}
    rows = []
    for envelope in run.analyses:
        row = {"curve_id": envelope.curve_id, "analysis_id": envelope.analysis_id,
               "method_id": envelope.analysis_type, "status": envelope.status.value,
               "execution_status": envelope.execution_status, "reporting_status": envelope.reporting_status,
               "q_range": envelope.q_range, "range_source": envelope.range_source}
        if envelope.q_range is not None and envelope.curve_id in curves:
            method = {"peaks": "peak_detection"}.get(envelope.analysis_type, envelope.analysis_type)
            check = check_analysis_preflight(curves[envelope.curve_id], method, envelope.q_range, range_source=envelope.range_source)
            row["generic_preflight"] = asdict(check)
        else:
            row["generic_preflight"] = {"severity": "not_run", "messages": ["No valid method-specific q range"]}
        rows.append(row)
    return rows


def run_study(
    input_dir: str | Path, output_dir: str | Path, *, config: dict[str, Any] | None = None,
    resume: bool = False, retry_failed: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Run isolated samples and publish verifiable packages without GUI imports."""
    from app.core.publication_bundle import export_publication_bundle

    settings = validate_study_config(config)
    root, target = Path(input_dir).resolve(strict=True), Path(output_dir).resolve()
    if target.is_relative_to(root) or root.is_relative_to(target):
        raise ValueError("Output must be disjoint from the input tree")
    samples = discover_study(root, settings)
    snapshot = _snapshot(samples, root, settings)
    fingerprint = sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    checkpoint = target / "study.json"
    if target.exists():
        if not resume or not checkpoint.is_file():
            raise FileExistsError("Output exists; use --resume for an owned study or choose a new destination")
        state = json.loads(checkpoint.read_text(encoding="utf-8"))
        if state.get("schema_version") != 1 or state.get("fingerprint") != fingerprint:
            raise ValueError("Resume input/config/metadata fingerprint differs; use a new output directory")
    else:
        if resume:
            raise FileNotFoundError("No study checkpoint to resume")
        target.mkdir(parents=True)
        state = {"schema_version": 1, "study_id": str(uuid4()), "started_at": utc_now_iso(), "fingerprint": fingerprint, "snapshot": snapshot, "samples": {}, "status": "running"}
    for child in (target / ".cache", target / "samples"):
        if not child.resolve().is_relative_to(target):
            raise ValueError("Study output directories must not link outside their root")
    for previous in state["samples"].values():
        if previous.get("package"):
            package = (target / previous["package"]).resolve()
            if not package.is_relative_to(target) or not _verify_inventory(package, previous.get("output_inventory", [])):
                raise ValueError(f"Completed sample artifacts changed: {previous.get('sample_id')}; use a new destination")
    state["status"] = "running"
    state["finished_at"] = None
    write_json_atomic(checkpoint, state)
    for sample in samples:
        previous = state["samples"].get(sample.sample_id, {})
        if previous.get("package") and previous.get("status") != "cancelled" and not (retry_failed and previous.get("status") in {"failed", "partial_success"}):
            # All previous packages were content-verified above, before writes.
            if progress_callback:
                progress_callback({"sample_id": sample.sample_id, "operation": "resume_verified", "status": previous["status"]})
            continue
        if cancel_requested and cancel_requested():
            state["status"] = "cancelled"
            break
        sample_target = target / "samples" / _sample_directory(sample.sample_id)
        if sample_target.exists():
            sample_target = sample_target.with_name(f"{sample_target.name}-retry-{uuid4().hex[:8]}")
        record: dict[str, Any] = {"sample_id": sample.sample_id, "identity_source": sample.identity_source, "source_files": [p.relative_to(root).as_posix() for p in sample.files], "status": "running"}
        if previous:
            record["attempt_history"] = [*previous.get("attempt_history", []),
                                         {key: value for key, value in previous.items() if key != "attempt_history"}]
        state["samples"][sample.sample_id] = record
        write_json_atomic(checkpoint, state)
        try:
            table_cache = TableReadCache(max_entries=len(sample.files))
            def progress(event: ProgressEvent) -> None:
                if progress_callback:
                    progress_callback({"sample_id": sample.sample_id, **asdict(event)})
            try:
                sample_config = _resolve_sample_config(sample, root, settings, table_cache)
                run = run_auto_batch(root, sample_config, input_paths=sample.files, input_metadata=_input_metadata(sample, root, settings), cache_dir=target / ".cache" / _sample_directory(sample.sample_id), cancel_requested=cancel_requested, progress_callback=progress, table_cache=table_cache)
            finally:
                table_cache.clear()
            run.config_snapshot["study_identity_source"] = sample.identity_source
            run.config_snapshot["planned_frames"] = _planned_frames(sample, root, settings, sample_config)
            run.config_snapshot["batch_preflight_audit"] = _preflight_rows(run)
            expected = {row["source_file"]: row["sha256"] for row in snapshot["inputs"] if row["sample_id"] == sample.sample_id}
            if any(sha256_file(path) != expected[path.relative_to(root).as_posix()] for path in sample.files):
                raise ValueError("Source data changed during analysis; result not published")
            for row in run.input_manifest:
                path = Path(row["source_path"]).resolve()
                if row.get("sha256") and row["sha256"] != expected.get(path.relative_to(root).as_posix()):
                    raise ValueError("Manifest hash differs from initial source snapshot; result not published")
            if any(sha256_file(row["path"]) != row["sha256"] for row in snapshot["metadata"]):
                raise ValueError("Metadata changed during analysis; result not published")
            figures = settings.get("figures", {})
            exported = export_publication_bundle(run, sample_target, formats=tuple(figures.get("formats", ["png", "svg", "pdf"])), dpi=figures.get("dpi", 200), max_overlay_curves=figures.get("max_overlay_curves", 24))
            record.update(status=run.status, package=exported.relative_to(target).as_posix(), output_inventory=_output_inventory(exported), curve_count=len(run.curves), failed_inputs=len(run.failed_inputs), warnings=run.warnings, effective_q_range=list(sample_config.effective_q_range), run_id=run.run_id)
            if run.status == "cancelled":
                state["status"] = "cancelled"
        except Exception as exc:
            record.update(status="failed", error=str(exc) or type(exc).__name__)
        write_json_atomic(checkpoint, state)
        if progress_callback:
            progress_callback({"sample_id": sample.sample_id, "operation": "sample_finished", "status": record["status"], "package": record.get("package"), "error": record.get("error")})
        if state["status"] == "cancelled":
            break
    if state["status"] != "cancelled":
        statuses = [record["status"] for record in state["samples"].values()]
        good = any(status in {"completed", "completed_with_limitations", "partial_success"} for status in statuses)
        bad = any(status in {"failed", "partial_success", "cancelled", "running"} for status in statuses)
        state["status"] = "partial_success" if good and bad else "failed" if not good else "completed_with_limitations" if "completed_with_limitations" in statuses else "completed"
    state["finished_at"] = utc_now_iso()
    state["software"] = {"python": __import__("sys").version.split()[0], "numpy": np.__version__, "pandas": pd.__version__}
    write_json_atomic(checkpoint, state)
    rows = [{key: record.get(key) for key in ("sample_id", "status", "package", "curve_count", "failed_inputs", "error")} for record in state["samples"].values()]
    pd.DataFrame(rows).to_csv(target / "sample_index.csv", index=False, encoding="utf-8-sig")
    (target / "README.md").write_text("# Agent SAS study\n\nOpen `sample_index.csv` and `study.json` first, then each sample package.\nEach sample has independent q consensus, fits, reference comparisons and evolution.\nOriginal inputs are read only. Failed imports and unavailable metrics remain auditable.\nCompletion describes software execution, not scientific acceptance.\n", encoding="utf-8")
    return state
