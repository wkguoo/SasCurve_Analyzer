from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app.core.study as study
from app.core.auto_batch_schema import AutoBatchRun
from app.core.study import discover_study, run_study, validate_study_config


def _curve(path: Path, scale: float = 1.0, unit: str = "A") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    q = np.geomspace(0.005, 0.2, 32)
    pd.DataFrame({f"q_{unit}_inv": q if unit == "A" else q * 10,
                  "intensity_cm_inv": scale * np.exp(-(q * 15) ** 2 / 3)}).to_csv(path, index=False)


def _fake_package(monkeypatch):
    import app.core.publication_bundle as publication_bundle
    def export(run, destination, **kwargs):
        path = Path(destination)
        path.mkdir(parents=True)
        (path / "payload.json").write_text(json.dumps({"batch_id": run.batch_id, "status": run.status}))
        return path
    monkeypatch.setattr(publication_bundle, "export_publication_bundle", export)


def test_recursive_discovery_keeps_samples_and_natural_frame_order(tmp_path):
    root = tmp_path / "input"
    for name in ("Ti15_LD/frame_10.csv", "Ti15_LD/frame_2.csv", "Ti15_TD/frame_1.csv"):
        _curve(root / name)
    samples = discover_study(root)
    assert [sample.sample_id for sample in samples] == ["Ti15_LD", "Ti15_TD"]
    assert [path.name for path in samples[0].files] == ["frame_2.csv", "frame_10.csv"]


def test_flat_discovery_preserves_numeric_sample_identity(tmp_path):
    for name in ("Ti15_LD_0001_abs2d.csv", "Ti15_LD_0002_abs2d.csv", "Ti15_TD_0001_abs2d.csv"):
        _curve(tmp_path / name)
    assert [sample.sample_id for sample in discover_study(tmp_path)] == ["Ti15_LD", "Ti15_TD"]
    _curve(tmp_path / "unidentified.csv")
    with pytest.raises(ValueError, match="Ambiguous"):
        discover_study(tmp_path)


def test_frame_only_filename_requires_explicit_sample_identity(tmp_path):
    _curve(tmp_path / "0001.csv")
    with pytest.raises(ValueError, match="Ambiguous sample identity"):
        discover_study(tmp_path)
    assert discover_study(tmp_path, {"grouping": "directory"})[0].sample_id == tmp_path.name


def test_metadata_is_authoritative_and_basename_ambiguity_is_rejected(tmp_path):
    for folder in ("a", "b"):
        _curve(tmp_path / folder / "same.csv")
    sidecar = tmp_path / "metadata.csv"
    pd.DataFrame([{"source_file": "a/same.csv", "sample_id": "A", "time_s": 0},
                  {"source_file": "b/same.csv", "sample_id": "B", "time_s": 0}]).to_csv(sidecar, index=False)
    config = {"analysis": {"metadata_path": str(sidecar)}}
    assert [sample.sample_id for sample in discover_study(tmp_path, config)] == ["A", "B"]
    pd.DataFrame([{"source_file": "same.csv", "sample_id": "A"}]).to_csv(sidecar, index=False)
    with pytest.raises(ValueError, match="Ambiguous metadata"):
        discover_study(tmp_path, config)


def test_numeric_metadata_sample_ids_keep_leading_zero_identity(tmp_path):
    for name in ("one.csv", "two.csv"):
        _curve(tmp_path / name)
    sidecar = tmp_path / "metadata.csv"
    sidecar.write_text("source_file,sample_id\none.csv,001\ntwo.csv,1\n", encoding="utf-8")
    samples = discover_study(tmp_path, {"grouping": "metadata", "analysis": {"metadata_path": str(sidecar)}})
    assert {sample.sample_id for sample in samples} == {"001", "1"}


def test_metadata_without_sample_ids_still_rejects_global_basename_ambiguity(tmp_path):
    for folder in ("a", "b"):
        _curve(tmp_path / folder / "frame_1.csv")
    sidecar = tmp_path / "metadata.csv"
    sidecar.write_text("source_file,time_s\nframe_1.csv,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Ambiguous metadata"):
        discover_study(tmp_path, {"analysis": {"metadata_path": str(sidecar)}})


def test_configured_sample_metadata_cannot_silently_fall_back(tmp_path):
    _curve(tmp_path / "scan_1.csv")
    _curve(tmp_path / "scan_2.csv")
    sidecar = tmp_path / "metadata.csv"
    sidecar.write_text("source_file,sample_id\ntypo.csv,sample-A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="did not match any"):
        discover_study(tmp_path, {"analysis": {"metadata_path": str(sidecar)}})


def test_metadata_identity_and_frame_take_precedence_over_unused_regex(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "out"
    _curve(root / "unusual.csv")
    sidecar = tmp_path / "metadata.csv"
    sidecar.write_text("source_file,sample_id,frame_index,time_s\nunusual.csv,correct,77,5\n", encoding="utf-8")
    settings = {"grouping": "metadata", "sample_regex": r"(?P<sample>.+)_f(?P<frame>\d+)",
                "analysis": {"metadata_path": str(sidecar)}}
    samples = discover_study(root, settings)
    assert samples[0].sample_id == "correct"
    passed = []
    def run(directory, config, **kwargs):
        from app.core.batch_inputs import collect_batch_inputs
        collected = collect_batch_inputs(directory, config, input_paths=kwargs["input_paths"], input_metadata=kwargs["input_metadata"])
        passed.append(collected.curves[0].metadata)
        return AutoBatchRun(batch_id=config.batch_id, status="completed")
    monkeypatch.setattr(study, "run_auto_batch", run)
    _fake_package(monkeypatch)
    assert run_study(root, output, config=settings)["status"] == "completed"
    assert passed[0]["frame_index"] == 77


@pytest.mark.parametrize("config", [
    {"analysis": {"enable_pr": "false"}}, {"analysis": {"bootstrap_samples": True}},
    {"analysis": {"contrast": float("nan")}}, {"analysis": {"allowed_models": ["invented"]}},
    {"analysis": {"unknown_key": 1}}, {"figures": {"formats": ["jpg"]}},
    {"sample_regex": "(?P<sample>.*)"}, {"schema_version": True},
])
def test_invalid_config_fails_before_work(config):
    with pytest.raises(ValueError):
        validate_study_config(config)


def test_study_partitions_before_analysis_and_preserves_input_hashes(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "output"
    for sample in ("Ti15_LD", "Ti15_TD"):
        for frame in (1, 2):
            _curve(root / f"{sample}_f{frame}.csv", scale=frame, unit="nm" if frame == 2 else "A")
    config = {"sample_regex": r"(?P<sample>.+)_f(?P<frame>\d+)", "analysis": {"enable_shape_models": False}}
    before = {p: p.read_bytes() for p in root.glob("*.csv")}
    calls = []
    def run(directory, config, *, input_paths, input_metadata, **kwargs):
        calls.append((config, tuple(input_paths), input_metadata))
        return AutoBatchRun(batch_id=config.batch_id, status="completed")
    monkeypatch.setattr(study, "run_auto_batch", run)
    _fake_package(monkeypatch)
    result = run_study(root, output, config=config)
    assert result["status"] == "completed"
    assert len(calls) == 2
    for config, paths, metadata in calls:
        assert all(config.batch_id in path.name for path in paths)
        assert config.effective_q_range == pytest.approx((0.005, 0.2))
        assert [row["frame_index"] for row in metadata.values()] == [1, 2]
        assert all(row["sample_id"] == config.batch_id for row in metadata.values())
    assert all(p.read_bytes() == original for p, original in before.items())
    calls.clear()
    resumed = run_study(root, output, config={"sample_regex": r"(?P<sample>.+)_f(?P<frame>\d+)", "analysis": {"enable_shape_models": False}}, resume=True)
    assert resumed["status"] == "completed"
    assert not calls


def test_resume_rejects_changed_source_or_tampered_output(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "out"
    _curve(root / "sample_1.csv")
    monkeypatch.setattr(study, "run_auto_batch", lambda _, config, **kw: AutoBatchRun(batch_id=config.batch_id, status="completed"))
    _fake_package(monkeypatch)
    result = run_study(root, output)
    package = output / result["samples"]["sample"]["package"]
    (package / "payload.json").write_text("tampered")
    with pytest.raises(ValueError, match="artifacts changed"):
        run_study(root, output, resume=True)
    _curve(root / "sample_1.csv", scale=2)
    with pytest.raises(ValueError, match="fingerprint differs"):
        run_study(root, output, resume=True)


def test_failure_isolated_and_retry_uses_a_new_destination(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "out"
    for sample in ("good", "bad"):
        _curve(root / sample / "frame_1.csv")
    def run(_, config, **kwargs):
        if config.batch_id == "bad":
            raise RuntimeError("isolated failure")
        return AutoBatchRun(batch_id=config.batch_id, status="completed")
    monkeypatch.setattr(study, "run_auto_batch", run)
    _fake_package(monkeypatch)
    result = run_study(root, output)
    assert result["status"] == "partial_success"
    assert result["samples"]["bad"]["error"] == "isolated failure"
    good_package = result["samples"]["good"]["package"]
    monkeypatch.setattr(study, "run_auto_batch", lambda _, config, **kw: AutoBatchRun(batch_id=config.batch_id, status="completed"))
    result = run_study(root, output, resume=True, retry_failed=True)
    assert result["status"] == "completed"
    assert result["samples"]["good"]["package"] == good_package
    assert result["samples"]["bad"]["attempt_history"][0]["error"] == "isolated failure"


def test_cancelled_sample_resumes_with_auditable_attempt_history(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "out"
    _curve(root / "sample_1.csv")
    monkeypatch.setattr(study, "run_auto_batch", lambda _, config, **kw: AutoBatchRun(batch_id=config.batch_id, status="cancelled"))
    _fake_package(monkeypatch)
    result = run_study(root, output)
    assert result["status"] == "cancelled"
    first = result["samples"]["sample"]["package"]
    monkeypatch.setattr(study, "run_auto_batch", lambda _, config, **kw: AutoBatchRun(batch_id=config.batch_id, status="completed"))
    result = run_study(root, output, resume=True)
    assert result["status"] == "completed"
    assert result["samples"]["sample"]["package"] != first
    assert result["samples"]["sample"]["attempt_history"][0]["package"] == first
    assert (output / first).is_dir()


def test_no_input_overlap_or_overwrite(tmp_path, monkeypatch):
    root = tmp_path / "input"
    _curve(root / "sample_1.csv")
    with pytest.raises(ValueError, match="disjoint"):
        run_study(root, root / "results")
    with pytest.raises(ValueError, match="disjoint"):
        run_study(root, tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(FileExistsError):
        run_study(root, out)


def test_changed_source_during_run_never_publishes(tmp_path, monkeypatch):
    root, output = tmp_path / "input", tmp_path / "out"
    source = root / "sample_1.csv"
    _curve(source)
    def run(_, config, **kwargs):
        _curve(source, scale=2)
        return AutoBatchRun(batch_id=config.batch_id, status="completed")
    monkeypatch.setattr(study, "run_auto_batch", run)
    _fake_package(monkeypatch)
    result = run_study(root, output)
    assert result["status"] == "failed"
    assert "changed during analysis" in result["samples"]["sample"]["error"]
    assert "package" not in result["samples"]["sample"]


def test_cli_methods_and_discover_need_no_qt(tmp_path):
    _curve(tmp_path / "S1_001.csv")
    invocation = "import sys; import app.cli; assert not any(n.startswith('PySide6') for n in sys.modules); raise SystemExit(app.cli.main(sys.argv[1:]))"
    command = subprocess.run([sys.executable, "-c", invocation, "discover", "--input", str(tmp_path)], capture_output=True, text=True)
    assert command.returncode == 0, command.stderr
    assert json.loads(command.stdout)["samples"][0]["sample_id"] == "S1"
    command = subprocess.run([sys.executable, "-m", "app.cli", "methods"], capture_output=True, text=True)
    assert command.returncode == 0
    assert "guinier" in [row["method_id"] for row in json.loads(command.stdout)["methods"]]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"sample_regex": "["}), encoding="utf-8")
    command = subprocess.run([sys.executable, "-m", "app.cli", "discover", "--input", str(tmp_path), "--config", str(invalid)], capture_output=True, text=True)
    assert command.returncode == 3
    assert json.loads(command.stdout)["status"] == "error"
    assert not command.stderr


def test_real_cli_exports_and_resumes_without_loading_qt(tmp_path):
    root, output = tmp_path / "input", tmp_path / "out"
    _curve(root / "sample_1.csv")
    _curve(root / "sample_2.csv", scale=2, unit="nm")
    settings = tmp_path / "config.json"
    settings.write_text(json.dumps({"analysis": {"enable_shape_models": False, "enable_range_sensitivity": False,
                                               "allow_per_frame_range_fallback": True},
                                    "figures": {"formats": ["png"], "dpi": 72}}), encoding="utf-8")
    invocation = "import sys; import app.cli; code=app.cli.main(sys.argv[1:]); assert not any(n.startswith('PySide6') for n in sys.modules); raise SystemExit(code)"
    args = [sys.executable, "-c", invocation, "run", "--input", str(root), "--output", str(output), "--config", str(settings), "--quiet"]
    command = subprocess.run(args, capture_output=True, text=True)
    assert command.returncode in (0, 2), command.stdout + command.stderr
    payload = json.loads(command.stdout)
    assert payload["samples"][0]["curve_count"] == 2
    package = output / payload["samples"][0]["package"]
    assert (package / "data_bundle.zip").is_file()
    assert (package / "figures_bundle.zip").is_file()
    assert (package / "data" / "analysis_evolution.csv").is_file()
    index = pd.read_csv(package / "figures" / "figure_index.csv")
    assert len(index) >= 8
    checkpoint_before = json.loads((output / "study.json").read_text(encoding="utf-8"))
    resumed = subprocess.run([*args, "--resume"], capture_output=True, text=True)
    assert resumed.returncode == command.returncode, resumed.stdout + resumed.stderr
    checkpoint_after = json.loads((output / "study.json").read_text(encoding="utf-8"))
    assert checkpoint_after["samples"] == checkpoint_before["samples"]
