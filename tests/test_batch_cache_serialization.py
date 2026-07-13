from __future__ import annotations

from app.core.auto_batch_schema import AnalysisEnvelope, AnalysisStatus, AutoBatchRun
from app.core.batch_cache import (
    envelope_from_dict,
    envelope_to_dict,
    load_run_checkpoint,
    save_run_checkpoint,
)


def test_analysis_envelope_dual_track_audit_fields_round_trip() -> None:
    envelope = AnalysisEnvelope(
        curve_id="frame-001",
        curve_name="frame_001.csv",
        analysis_id="frame-001:power_law:common",
        analysis_type="power_law",
        status=AnalysisStatus.SUCCESS,
        q_range=(0.015, 0.04),
        range_track="common",
        common_range_supported=True,
        robustness_status="completed",
        uncertainty_interpretation="robustness_interval_not_measurement_ci",
        reporting_status="reportable",
        reporting_reason_codes=["power_law_formal_gate_passed"],
    )

    restored = envelope_from_dict(envelope_to_dict(envelope))

    assert restored.status is AnalysisStatus.SUCCESS
    assert restored.q_range == (0.015, 0.04)
    assert restored.range_track == "common"
    assert restored.common_range_supported is True
    assert restored.robustness_status == "completed"
    assert restored.uncertainty_interpretation == "robustness_interval_not_measurement_ci"
    assert restored.reporting_status == "reportable"
    assert restored.reporting_reason_codes == ["power_law_formal_gate_passed"]


def test_analysis_envelope_old_cache_payload_uses_safe_new_field_defaults() -> None:
    restored = envelope_from_dict(
        {
            "curve_id": "legacy-frame",
            "curve_name": "legacy.csv",
            "analysis_id": "legacy-frame:guinier",
            "analysis_type": "guinier",
            "status": "success",
            "q_range": [0.01, 0.02],
        }
    )

    assert restored.range_track == "effective"
    assert restored.common_range_supported is None
    assert restored.robustness_status == "not_evaluated"
    assert restored.uncertainty_interpretation == "not_evaluated"


def test_run_checkpoint_preserves_candidate_windows(tmp_path) -> None:
    run = AutoBatchRun(batch_id="checkpoint-demo")
    run.candidate_windows = [
        {
            "curve_id": "frame-001",
            "method_id": "guinier",
            "q_start": 0.01,
            "q_end": 0.03,
            "range_track": "adaptive",
        }
    ]
    run.range_audit = [{"curve_id": "frame-001", "method_id": "guinier", "status": "ok"}]

    cache = tmp_path / "compute_cache"
    save_run_checkpoint(cache, run)
    restored = load_run_checkpoint(cache)

    assert restored.candidate_windows == run.candidate_windows
    assert restored.range_audit == run.range_audit
