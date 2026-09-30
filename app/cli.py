"""Machine-readable CLI for unattended calibrated SAS studies: python -m app.cli."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from pathlib import Path

from app.core.metric_registry import METHOD_REGISTRY
from app.core.shape_models import MODEL_SPECS
from app.core.study import discover_study, run_study, validate_study_config


def _load_config(path: str | None) -> dict:
    if path is None:
        return {}
    source = Path(path).resolve(strict=True)
    settings = json.loads(source.read_text(encoding="utf-8-sig"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON constant: {value}")))
    if not isinstance(settings, dict):
        raise ValueError("Study config must be a JSON object")
    for values in [settings.get("analysis", {}), *settings.get("samples", {}).values()]:
        if values.get("metadata_path"):
            metadata = Path(values["metadata_path"])
            values["metadata_path"] = str((source.parent / metadata).resolve()) if not metadata.is_absolute() else str(metadata.resolve())
    return validate_study_config(settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("methods", help="List method/model IDs and applicability")
    for name in ("discover", "run"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True, help="Read-only calibrated 1D curve folder")
        command.add_argument("--config", help="JSON study config; metadata paths relative to this file")
        if name == "run":
            command.add_argument("--output", required=True, help="New output directory outside input tree")
            command.add_argument("--resume", action="store_true", help="Verify and reuse completed sample packages")
            command.add_argument("--retry-failed", action="store_true", help="Retry failed/partial samples into new package directories")
            command.add_argument("--quiet", action="store_true", help="Suppress JSONL progress on stderr")
    args = parser.parse_args(argv)
    cancelled = False
    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True
    old_handler = signal.signal(signal.SIGINT, cancel)
    try:
        if args.command == "methods":
            result = {"schema_version": 1, "methods": [{"method_id": spec.method_id, "sample_types": spec.sample_types, "config_flag": spec.config_flag, "range_strategy": spec.range_strategy, "metrics": [metric.name for metric in spec.metrics]} for spec in METHOD_REGISTRY.values()], "models": list(MODEL_SPECS), "prerequisites": {"pr": {"required": ["enable_pr", "pr_dmax"], "pr_dmax_unit": "A for canonical headless q", "experimental": True}}, "input_scope": "calibrated reduced 1D q-I-error curves", "unsupported": ["2D detector reduction", "azimuthal integration", "particle-size distribution inversion"]}
        else:
            config = _load_config(args.config)
            if args.command == "discover":
                samples = discover_study(args.input, config)
                root = Path(args.input).resolve()
                result = {"schema_version": 1, "status": "ready", "input_root": str(root), "samples": [{"sample_id": sample.sample_id, "identity_source": sample.identity_source, "files": [path.relative_to(root).as_posix() for path in sample.files]} for sample in samples]}
            else:
                if args.retry_failed and not args.resume:
                    raise ValueError("--retry-failed requires --resume")
                def progress(event):
                    if not args.quiet:
                        print(json.dumps(event, ensure_ascii=True, allow_nan=False), file=sys.stderr, flush=True)
                result = run_study(args.input, args.output, config=config, resume=args.resume, retry_failed=args.retry_failed, progress_callback=progress, cancel_requested=lambda: cancelled)
                # The full checkpoint holds input and output inventories. stdout
                # remains compact enough for an Agent to act on after each run.
                result = {"schema_version": 1, "status": result["status"], "output": str(Path(args.output).resolve()), "checkpoint": str(Path(args.output).resolve() / "study.json"), "samples": [{key: row.get(key) for key in ("sample_id", "status", "package", "curve_count", "failed_inputs", "error")} for row in result["samples"].values()]}
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        status = result.get("status")
        return 130 if status == "cancelled" else 2 if status in {"partial_success", "failed"} else 0
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}, ensure_ascii=True), file=sys.stdout)
        return 3
    finally:
        signal.signal(signal.SIGINT, old_handler)


if __name__ == "__main__":
    raise SystemExit(main())
