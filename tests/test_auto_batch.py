from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import app.core.auto_batch as auto_batch
from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchConfig, ParameterValue
from app.core.batch_consensus import ConsensusRegion
from app.core.batch_inputs import BatchInputCollection
from app.core.data_model import CurveData
from app.core.metric_registry import applicable_method_ids


def _write_curve(path: Path, scale: float) -> None:
    path.write_text(
        f"q,I\n0.01,{10 * scale}\n0.02,{5 * scale}\n0.03,{2 * scale}\n",
        encoding="utf-8",
    )


def _success_envelope(
    curve: CurveData,
    method_id: str,
    q_range: tuple[float, float] | None,
    *,
    suffix: str = "",
) -> AnalysisEnvelope:
    return AnalysisEnvelope(
        curve_id=curve.curve_id,
        curve_name=curve.name,
        analysis_id=f"{curve.curve_id}:{method_id}{suffix}",
        analysis_type=method_id,
        status=AnalysisStatus.SUCCESS,
        q_range=q_range,
    )


def _success_runner(curve, method_id, q_range, config):
    return [_success_envelope(curve, method_id, q_range)]


def test_one_method_failure_does_not_abort_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    _write_curve(tmp_path / "s_002.csv", 2)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        if curve.name == "s_001" and method_id == "power_law":
            raise RuntimeError("synthetic failure")
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    assert run.status == "partial_success"
    assert len(run.analyses) == 2 * len(applicable_method_ids(AutoBatchConfig(batch_id="s")))
    failed = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert len(failed) == 1
    assert failed[0].invalid_reason == "synthetic failure"


def test_immediate_cancellation_skips_input_consensus_and_runner_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_input(*args, **kwargs):
        pytest.fail("input collection must not run after immediate cancellation")

    def unexpected_consensus(*args, **kwargs):
        pytest.fail("consensus resolution must not run after immediate cancellation")

    monkeypatch.setattr(auto_batch, "collect_batch_inputs", unexpected_input)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", unexpected_consensus)

    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="s"),
        cancel_requested=lambda: True,
        analysis_runner=lambda *args: pytest.fail("runner must not run after cancellation"),
    )

    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert run.analyses == []
    assert any("Cancellation requested" in warning for warning in run.warnings)


def test_cancellation_after_input_copy_skips_consensus_and_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = CurveData.create(name="frame", q=[0.01, 0.02], intensity=[3.0, 2.0])
    collection = BatchInputCollection(curves=[curve], manifest=[])
    cancel_values = iter([False, True])

    def unexpected_consensus(*args, **kwargs):
        pytest.fail("consensus resolution must not run after post-input cancellation")

    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: collection)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", unexpected_consensus)

    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="s"),
        cancel_requested=lambda: next(cancel_values),
        analysis_runner=lambda *args: pytest.fail("runner must not run after post-input cancellation"),
    )

    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert len(run.analyses) == len(applicable_method_ids(AutoBatchConfig(batch_id="s")))
    assert all(item.status == AnalysisStatus.CANCELLED for item in run.analyses)
    assert any("Cancellation requested" in warning for warning in run.warnings)


def test_cancellation_after_consensus_skips_all_runner_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = CurveData.create(name="frame", q=[0.01, 0.02], intensity=[3.0, 2.0])
    collection = BatchInputCollection(curves=[curve], manifest=[])
    cancel_values = iter([False, False, True])
    consensus_calls = []

    def consensus(curves, config):
        consensus_calls.append((curves, config))
        return {}

    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: collection)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", consensus)

    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="s"),
        cancel_requested=lambda: next(cancel_values),
        analysis_runner=lambda *args: pytest.fail("runner must not run after post-consensus cancellation"),
    )

    assert len(consensus_calls) == 1
    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert len(run.analyses) == len(applicable_method_ids(AutoBatchConfig(batch_id="s")))
    assert all(item.status == AnalysisStatus.CANCELLED for item in run.analyses)
    assert any("Cancellation requested" in warning for warning in run.warnings)


def test_cancellation_before_second_job_preserves_first_result_and_skips_next_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = CurveData.create(name="frame", q=[0.01, 0.02], intensity=[3.0, 2.0])
    collection = BatchInputCollection(curves=[curve], manifest=[])
    cancel_values = iter([False, False, False, False, True])
    runner_calls: list[str] = []

    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: collection)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        runner_calls.append(method_id)
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(
        "unused",
        AutoBatchConfig(batch_id="s"),
        cancel_requested=lambda: next(cancel_values),
        analysis_runner=runner,
    )

    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert runner_calls == ["data_quality"]
    assert len(run.analyses) == len(applicable_method_ids(AutoBatchConfig(batch_id="s")))
    assert run.analyses[0].analysis_type == "data_quality"
    assert run.analyses[0].status == AnalysisStatus.SUCCESS
    assert all(item.status == AnalysisStatus.CANCELLED for item in run.analyses[1:])
    assert any("Cancellation requested" in warning for warning in run.warnings)


def test_missing_consensus_passes_none_without_per_frame_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    q_ranges: dict[str, tuple[float, float] | None] = {}

    def runner(curve, method_id, q_range, config):
        q_ranges[method_id] = q_range
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    assert run.status == "completed"
    assert q_ranges["guinier"] is None
    assert q_ranges["power_law"] is None
    assert q_ranges["local_slope"] is None
    assert q_ranges["crossover"] is None
    assert q_ranges["porod"] is None
    assert q_ranges["peaks"] is None
    assert q_ranges["shoulders"] is None
    assert q_ranges["oscillations"] is None
    assert any("strict per-frame fallback is disabled" in warning for warning in run.warnings)


def test_multiple_runner_envelopes_are_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        if method_id == "shape_models":
            return [
                _success_envelope(curve, method_id, q_range, suffix=":sphere"),
                _success_envelope(curve, method_id, q_range, suffix=":cylinder"),
            ]
        return [_success_envelope(curve, method_id, q_range)]

    config = AutoBatchConfig(batch_id="s")
    run = run_auto_batch(tmp_path, config, analysis_runner=runner)

    shape_envelopes = [item for item in run.analyses if item.analysis_type == "shape_models"]
    assert run.status == "completed"
    assert len(run.analyses) == len(applicable_method_ids(config)) + 1
    assert [item.analysis_id.rsplit(":", 1)[-1] for item in shape_envelopes] == ["sphere", "cylinder"]


def test_lamellar_and_peak_family_methods_share_peak_consensus_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    peak_region = ConsensusRegion(
        region_type="peak",
        q_range=(0.015, 0.025),
        coverage=1.0,
        median_score=0.9,
        supporting_curve_ids=("curve",),
    )
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {"peak": peak_region})
    q_ranges: dict[str, tuple[float, float] | None] = {}

    def runner(curve, method_id, q_range, config):
        q_ranges[method_id] = q_range
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(
        tmp_path,
        AutoBatchConfig(batch_id="s", sample_type="lamellar"),
        analysis_runner=runner,
    )

    assert run.status == "completed"
    assert run.consensus_regions == {"peak": (0.015, 0.025)}
    assert {method_id: q_ranges[method_id] for method_id in ("peaks", "shoulders", "oscillations", "lamellar")} == {
        "peaks": (0.015, 0.025),
        "shoulders": (0.015, 0.025),
        "oscillations": (0.015, 0.025),
        "lamellar": (0.015, 0.025),
    }


def test_consensus_resolution_failure_isolated_and_marks_partial_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)

    def fail_consensus(curves, config):
        raise RuntimeError("synthetic consensus failure")

    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", fail_consensus)
    config = AutoBatchConfig(batch_id="s")

    run = run_auto_batch(tmp_path, config, analysis_runner=_success_runner)

    assert run.status == "partial_success"
    assert run.consensus_regions == {}
    assert len(run.analyses) == len(applicable_method_ids(config))
    assert any("synthetic consensus failure" in warning for warning in run.warnings)


@pytest.mark.parametrize(
    ("bad_runner", "expected_fragment"),
    [
        (lambda curve, method_id, q_range, config: "not-a-list", "list[AnalysisEnvelope]"),
        (lambda curve, method_id, q_range, config: ["not-an-envelope"], "AnalysisEnvelope"),
    ],
    ids=["non-list", "non-envelope-item"],
)
def test_invalid_runner_contract_is_isolated_per_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    bad_runner,
    expected_fragment: str,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        if method_id == "guinier":
            return bad_runner(curve, method_id, q_range, config)
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    failures = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert run.status == "partial_success"
    assert len(failures) == 1
    assert failures[0].analysis_type == "guinier"
    assert expected_fragment in (failures[0].invalid_reason or "")


def test_failed_method_keeps_registered_parameter_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        if method_id == "guinier":
            raise RuntimeError("synthetic fit failure")
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)
    failure = next(item for item in run.analyses if item.analysis_type == "guinier")

    assert {parameter.name for parameter in failure.parameters} == {
        metric.name for metric in auto_batch.METHOD_REGISTRY["guinier"].metrics
    }
    assert all(parameter.value is None for parameter in failure.parameters)
    assert all(parameter.status == AnalysisStatus.FIT_FAILED for parameter in failure.parameters)
    assert all(parameter.invalid_reason == "synthetic fit failure" for parameter in failure.parameters)


@pytest.mark.parametrize(
    ("mismatch_field", "expected_fragment"),
    [("curve_id", "curve_id"), ("analysis_type", "analysis_type")],
    ids=["wrong-curve", "wrong-method"],
)
def test_runner_envelope_identity_mismatch_is_isolated_per_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch_field: str,
    expected_fragment: str,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    foreign_curve = CurveData.create(name="foreign", q=[0.01, 0.02], intensity=[3.0, 2.0])

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            if mismatch_field == "curve_id":
                envelope.curve_id = foreign_curve.curve_id
            else:
                envelope.analysis_type = "porod"
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    failures = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert run.status == "partial_success"
    assert len(failures) == 1
    assert failures[0].curve_id == run.curves[0].curve_id
    assert failures[0].analysis_type == "guinier"
    assert expected_fragment in (failures[0].invalid_reason or "")
    assert all(item.curve_id == run.curves[0].curve_id for item in run.analyses)


def test_any_identity_mismatch_in_multi_envelope_runner_output_is_one_fit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    foreign_curve = CurveData.create(name="foreign", q=[0.01, 0.02], intensity=[3.0, 2.0])

    def runner(curve, method_id, q_range, config):
        if method_id == "guinier":
            valid = _success_envelope(curve, method_id, q_range, suffix=":valid")
            mismatched = _success_envelope(curve, method_id, q_range, suffix=":foreign")
            mismatched.curve_id = foreign_curve.curve_id
            return [valid, mismatched]
        return [_success_envelope(curve, method_id, q_range)]

    config = AutoBatchConfig(batch_id="s")
    run = run_auto_batch(tmp_path, config, analysis_runner=runner)

    guinier_rows = [item for item in run.analyses if item.analysis_type == "guinier"]
    assert run.status == "partial_success"
    assert len(run.analyses) == len(applicable_method_ids(config))
    assert len(guinier_rows) == 1
    assert guinier_rows[0].status == AnalysisStatus.FIT_FAILED
    assert guinier_rows[0].curve_id == run.curves[0].curve_id
    assert "curve_id" in (guinier_rows[0].invalid_reason or "")


@pytest.mark.parametrize("invalid_status", ["not-a-real-status", []], ids=["invalid-string", "unhashable-list"])
def test_invalid_runner_envelope_status_is_isolated_per_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_status,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            envelope.status = invalid_status
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    failures = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert run.status == "partial_success"
    assert len(failures) == 1
    assert failures[0].analysis_type == "guinier"
    assert "AnalysisEnvelope.status" in (failures[0].invalid_reason or "")


@pytest.mark.parametrize(
    ("raw_status", "expected_status", "expected_run_status"),
    [
        ("success", AnalysisStatus.SUCCESS, "completed"),
        ("fit_failed", AnalysisStatus.FIT_FAILED, "partial_success"),
    ],
    ids=["success-string", "fit-failed-string"],
)
def test_valid_string_runner_status_is_normalized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_status: str,
    expected_status: AnalysisStatus,
    expected_run_status: str,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            envelope.status = raw_status
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    guinier = next(item for item in run.analyses if item.analysis_type == "guinier")
    assert guinier.status is expected_status
    assert run.status == expected_run_status


def test_empty_runner_list_is_isolated_as_one_fit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        if method_id == "guinier":
            return []
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    failures = [item for item in run.analyses if item.status == AnalysisStatus.FIT_FAILED]
    assert run.status == "partial_success"
    assert len(failures) == 1
    assert failures[0].analysis_type == "guinier"
    assert "non-empty list[AnalysisEnvelope]" in (failures[0].invalid_reason or "")


@pytest.mark.parametrize(
    "returned_status",
    [AnalysisStatus.FIT_FAILED, AnalysisStatus.INVALID, AnalysisStatus.CANCELLED],
    ids=["fit-failed", "invalid", "cancelled"],
)
def test_returned_non_success_envelope_makes_run_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returned_status: AnalysisStatus,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            envelope.status = returned_status
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    guinier = next(item for item in run.analyses if item.analysis_type == "guinier")
    assert guinier.status is returned_status
    assert run.status == "partial_success"


def test_progress_callback_failure_is_recorded_without_aborting_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    attempted_events = []

    def fail_progress(event):
        attempted_events.append(event)
        raise RuntimeError("synthetic progress failure")

    config = AutoBatchConfig(batch_id="s")
    run = run_auto_batch(
        tmp_path,
        config,
        analysis_runner=_success_runner,
        progress_callback=fail_progress,
    )

    assert run.status == "completed"
    assert len(attempted_events) == len(applicable_method_ids(config))
    assert all(event.total_units == len(applicable_method_ids(config)) for event in attempted_events)
    assert attempted_events[-1].completed_units == attempted_events[-1].total_units
    assert any("synthetic progress failure" in warning for warning in run.warnings)


def test_full_range_uses_only_finite_q_and_empty_q_is_passed_as_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finite_curve = CurveData.create(
        name="finite",
        q=[np.nan, 0.01, np.inf, 0.03],
        intensity=[1.0, 2.0, 3.0, 4.0],
    )
    empty_curve = CurveData.create(name="empty", q=[], intensity=[])
    collection = BatchInputCollection(curves=[finite_curve, empty_curve], manifest=[])
    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: collection)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    q_ranges: dict[tuple[str, str], tuple[float, float] | None] = {}

    def runner(curve, method_id, q_range, config):
        q_ranges[(curve.name, method_id)] = q_range
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch("unused", AutoBatchConfig(batch_id="s"), analysis_runner=runner)

    assert run.status == "completed"
    assert q_ranges[("finite", "data_quality")] == (0.01, 0.03)
    assert q_ranges[("empty", "data_quality")] is None
    assert q_ranges[("finite", "guinier")] is None
    assert q_ranges[("empty", "guinier")] is None
    assert any("Curve 'empty' has no safe finite full q range" in warning for warning in run.warnings)


def test_failed_input_rows_make_an_otherwise_successful_run_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curve = CurveData.create(name="valid", q=[0.01, 0.02], intensity=[3.0, 2.0])
    collection = BatchInputCollection(
        curves=[curve],
        manifest=[],
        failed_inputs=[{"file": "broken.csv", "error": "synthetic input failure"}],
    )
    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: collection)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    run = run_auto_batch("unused", AutoBatchConfig(batch_id="s"), analysis_runner=_success_runner)

    assert run.status == "partial_success"
    assert run.failed_inputs == collection.failed_inputs


def test_cancel_callback_error_safely_cancels_and_records_reason(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def fail_cancel_check():
        raise RuntimeError("synthetic cancellation failure")

    run = run_auto_batch(
        tmp_path,
        AutoBatchConfig(batch_id="s"),
        cancel_requested=fail_cancel_check,
        analysis_runner=lambda *args: pytest.fail("runner must not run after failed cancellation check"),
    )

    assert run.status == "cancelled"
    assert run.finished_at is not None
    assert any("synthetic cancellation failure" in warning for warning in run.warnings)


def test_cancel_during_last_runner_marks_run_and_remaining_contract_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    config = AutoBatchConfig(batch_id="s")
    methods = applicable_method_ids(config)
    cancel = False

    def runner(curve, method_id, q_range, config):
        nonlocal cancel
        if method_id == methods[-1]:
            cancel = True
        return [_success_envelope(curve, method_id, q_range)]

    run = run_auto_batch(
        tmp_path,
        config,
        analysis_runner=runner,
        cancel_requested=lambda: cancel,
    )

    assert run.status == "cancelled"
    assert len(run.analyses) == len(methods)


def test_cancel_before_first_job_materializes_all_unexecuted_envelopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})
    checks = iter([False, False, False, True])
    config = AutoBatchConfig(batch_id="s")

    run = run_auto_batch(
        tmp_path,
        config,
        analysis_runner=lambda *args: pytest.fail("cancelled jobs must not run"),
        cancel_requested=lambda: next(checks),
    )

    assert run.status == "cancelled"
    assert len(run.analyses) == len(applicable_method_ids(config))
    assert all(item.status == AnalysisStatus.CANCELLED for item in run.analyses)
    assert all(item.parameters for item in run.analyses)
    assert all(parameter.unit for item in run.analyses for parameter in item.parameters)


def test_default_runner_uses_production_registry_runner_and_records_model_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    config = AutoBatchConfig(batch_id="s")
    run = run_auto_batch(tmp_path, config)

    assert run.status == "partial_success"
    assert run.analyses
    assert {item.analysis_type for item in run.analyses} == set(applicable_method_ids(config))
    assert all(item.invalid_reason != "production runner is installed by Plan 2" for item in run.analyses)
    assert run.rankings
    assert run.main_model is None
    assert len(run.transition_flags) == len(run.curves)


def test_completed_batch_keeps_one_main_model_and_records_three_frame_transition_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curves = [
        CurveData.create(name=f"frame-{index}", q=[0.01, 0.02, 0.03], intensity=[3.0, 2.0, 1.0])
        for index in range(7)
    ]
    monkeypatch.setattr(auto_batch, "collect_batch_inputs", lambda input_dir, config: BatchInputCollection(curves=curves, manifest=[]))
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def model_envelope(curve: CurveData, model_name: str, aicc: float) -> AnalysisEnvelope:
        return AnalysisEnvelope(
            curve_id=curve.curve_id,
            curve_name=curve.name,
            analysis_id=f"{curve.curve_id}:shape_models:{model_name}",
            analysis_type="shape_models",
            status=AnalysisStatus.SUCCESS,
            q_range=(0.01, 0.03),
            parameters=[
                ParameterValue(name="model_name", value=model_name),
                ParameterValue(name="radius", value=10.0, stderr=0.2, bound_hit=False),
            ],
            fit_quality={"AICc": aicc, "BIC": aicc + 1.0, "residual_pass": True, "uncertainty_score": 0.02},
        )

    def runner(curve, method_id, q_range, config):
        if method_id != "shape_models":
            return [_success_envelope(curve, method_id, q_range)]
        index = int(curve.name.rsplit("-", 1)[-1])
        sphere_aicc, cylinder_aicc = (20.0, 10.0) if index < 3 else (5.0, 30.0)
        return [model_envelope(curve, "sphere", sphere_aicc), model_envelope(curve, "cylinder", cylinder_aicc)]

    run = run_auto_batch("unused", AutoBatchConfig(batch_id="model-sequence"), analysis_runner=runner)

    assert run.status == "completed"
    assert run.main_model == "sphere"
    assert {row["model_name"] for row in run.rankings} == {"sphere", "cylinder"}
    assert [row["possible_model_transition"] for row in run.transition_flags] == [False, False, True, False, False, False, False]
    assert all(row["main_model"] == "sphere" for row in run.transition_flags)


def test_missing_prerequisite_with_success_marks_completed_with_limitations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            envelope.status = AnalysisStatus.MISSING_PREREQUISITE
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="limits"), analysis_runner=runner)

    assert run.status == "completed_with_limitations"
    assert any(item.status is AnalysisStatus.SUCCESS for item in run.analyses)
    assert any(item.status is AnalysisStatus.MISSING_PREREQUISITE for item in run.analyses)


def test_all_missing_prerequisite_marks_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        envelope.status = AnalysisStatus.MISSING_PREREQUISITE
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="no-usable"), analysis_runner=runner)

    assert run.status == "failed"
    assert run.analyses
    assert all(item.status is AnalysisStatus.MISSING_PREREQUISITE for item in run.analyses)


def test_assumption_dependent_only_marks_completed_with_limitations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        envelope.status = AnalysisStatus.ASSUMPTION_DEPENDENT
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="assumptions"), analysis_runner=runner)

    assert run.status == "completed_with_limitations"


def test_all_hard_failures_mark_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        envelope.status = AnalysisStatus.FIT_FAILED
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="all-fail"), analysis_runner=runner)

    assert run.status == "failed"


def test_hard_failure_with_success_remains_partial_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_curve(tmp_path / "s_001.csv", 1)
    monkeypatch.setattr(auto_batch, "resolve_consensus_regions", lambda curves, config: {})

    def runner(curve, method_id, q_range, config):
        envelope = _success_envelope(curve, method_id, q_range)
        if method_id == "guinier":
            envelope.status = AnalysisStatus.INVALID
        return [envelope]

    run = run_auto_batch(tmp_path, AutoBatchConfig(batch_id="mixed-hard"), analysis_runner=runner)

    assert run.status == "partial_success"
