from dataclasses import asdict

import pytest

from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig, ParameterValue


def test_auto_batch_config_rejects_invalid_consensus_coverage():
    with pytest.raises(ValueError, match="consensus_min_coverage"):
        AutoBatchConfig(batch_id="test", consensus_min_coverage=1.1)


def test_parameter_value_preserves_empty_value_with_reason():
    value = ParameterValue(
        name="Rg",
        value=None,
        unit="A",
        status=AnalysisStatus.MISSING_PREREQUISITE,
        invalid_reason="no valid Guinier interval",
    )
    payload = asdict(value)
    assert payload["value"] is None
    assert payload["status"] == AnalysisStatus.MISSING_PREREQUISITE
    assert payload["invalid_reason"] == "no valid Guinier interval"


def test_default_config_is_strict_batch_consensus():
    config = AutoBatchConfig(batch_id="series")
    assert config.consensus_min_coverage == 0.70
    assert config.allow_per_frame_range_fallback is False
    assert config.effective_q_range == (0.01, 0.05)


@pytest.mark.parametrize("q_range", [(0.05, 0.01), (-0.01, 0.05), (0.01, float("inf"))])
def test_effective_q_range_must_be_finite_nonnegative_and_ascending(q_range):
    with pytest.raises(ValueError, match="effective_q_range"):
        AutoBatchConfig(batch_id="series", effective_q_range=q_range)
