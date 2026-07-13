from __future__ import annotations

import json
from types import SimpleNamespace
import warnings

import numpy as np
import pytest

from app.core.cancellation import cancel_scope
from app.core.uncertainty_analysis import (
    bootstrap_fit,
    moving_block_residual_bootstrap_fit,
    range_sensitivity,
)


@pytest.fixture
def simple_fit_callback():
    included_indices = np.arange(12, dtype=int)

    def callback(sampled_indices: np.ndarray) -> dict[str, float]:
        values = np.asarray(sampled_indices, dtype=float)
        return {
            "mean_index": float(np.mean(values)),
            "index_span": float(np.max(values) - np.min(values)),
        }

    callback.included_indices = included_indices
    return callback


@pytest.fixture
def simple_range_callback():
    def callback(q_range: tuple[float, float]) -> dict[str, float]:
        q_low, q_high = q_range
        return {"q_mid": (q_low + q_high) / 2.0, "q_width": q_high - q_low}

    return callback


def test_bootstrap_is_reproducible(simple_fit_callback) -> None:
    first = bootstrap_fit(simple_fit_callback, sample_count=50, seed=123)
    second = bootstrap_fit(simple_fit_callback, sample_count=50, seed=123)

    assert first.parameter_quantiles == second.parameter_quantiles


def test_range_sensitivity_reports_boundary_variants(simple_range_callback) -> None:
    result = range_sensitivity(simple_range_callback, (0.01, 0.1), boundary_fraction=0.05)

    assert result.variant_count == 9
    assert result.sensitivity_score is not None


def test_bootstrap_records_resamples_seed_statistics_and_json_safe_output(simple_fit_callback) -> None:
    original_indices = simple_fit_callback.included_indices.copy()

    result = bootstrap_fit(simple_fit_callback, sample_count=12, seed=17)

    assert result.status == "completed"
    assert result.seed == 17
    assert result.sample_count == 12
    assert result.success_count == 12
    assert result.failure_count == 0
    assert len(result.attempts) == 12
    assert all(len(row["resampled_indices"]) == original_indices.size for row in result.attempts)
    assert all(set(row["resampled_indices"]) <= set(original_indices) for row in result.attempts)
    assert "mean_index" in result.parameter_quantiles
    assert result.coefficient_of_variation["mean_index"] is not None
    assert 0.0 <= result.sensitivity_score <= 1.0
    np.testing.assert_array_equal(simple_fit_callback.included_indices, original_indices)
    json.loads(json.dumps(result.to_dict(), allow_nan=False))


def test_bootstrap_optional_failure_is_audited_without_raising() -> None:
    callback_calls = 0

    def failing_callback(_sampled_indices: np.ndarray) -> dict[str, float]:
        nonlocal callback_calls
        callback_calls += 1
        raise RuntimeError("synthetic optional uncertainty failure")

    failing_callback.included_indices = np.arange(6, dtype=int)
    result = bootstrap_fit(failing_callback, sample_count=5, seed=7, minimum_valid_fits=3)

    assert callback_calls == 5
    assert result.status == "insufficient_valid_fits"
    assert result.success_count == 0
    assert result.failure_count == 5
    assert result.parameter_quantiles == {}
    assert all(row["reason"] == "callback_exception:RuntimeError" for row in result.attempts)


def test_bootstrap_respects_optional_enabled_gate_without_calling_callback(simple_fit_callback) -> None:
    calls = 0

    def callback(_sampled_indices: np.ndarray) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"parameter": 1.0}

    callback.included_indices = simple_fit_callback.included_indices
    result = bootstrap_fit(callback, sample_count=8, seed=9, enabled=False)

    assert calls == 0
    assert result.enabled is False
    assert result.status == "not_enabled"
    assert result.reason == "bootstrap_not_enabled"


def test_range_sensitivity_records_all_boundary_pairs_and_isolates_callback_failures() -> None:
    def callback(q_range: tuple[float, float]) -> dict[str, float]:
        q_low, q_high = q_range
        if q_low > 0.01:
            raise RuntimeError("synthetic range failure")
        return {"q_mid": (q_low + q_high) / 2.0, "q_width": q_high - q_low}

    result = range_sensitivity(callback, (0.01, 0.1), boundary_fraction=0.05, minimum_valid_fits=3)
    pairs = {(row["lower_shift_fraction"], row["upper_shift_fraction"]) for row in result.attempts}

    assert result.variant_count == 9
    assert len(result.attempts) == 9
    assert pairs == {
        (-0.05, -0.05),
        (-0.05, 0.0),
        (-0.05, 0.05),
        (0.0, -0.05),
        (0.0, 0.0),
        (0.0, 0.05),
        (0.05, -0.05),
        (0.05, 0.0),
        (0.05, 0.05),
    }
    assert result.success_count == 6
    assert result.failure_count == 3
    assert result.status == "completed"
    assert 0.0 <= result.sensitivity_score <= 1.0
    assert any(row["reason"] == "callback_exception:RuntimeError" for row in result.attempts)


def test_range_sensitivity_rejects_invalid_range_without_throwing(simple_range_callback) -> None:
    result = range_sensitivity(simple_range_callback, (0.1, 0.01), boundary_fraction=0.05)

    assert result.status == "invalid_input"
    assert result.reason == "q_range_must_contain_two_finite_ascending_bounds"
    assert result.sensitivity_score is None


def test_optional_analysis_honors_config_enablement_and_audit_values(simple_fit_callback, simple_range_callback) -> None:
    calls = 0

    def callback(_sampled_indices: np.ndarray) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"parameter": 1.0}

    callback.included_indices = simple_fit_callback.included_indices
    bootstrap_config = SimpleNamespace(enable_bootstrap=False, bootstrap_samples=11, bootstrap_seed=44)
    bootstrap = bootstrap_fit(callback, config=bootstrap_config)
    range_config = SimpleNamespace(enable_range_sensitivity=False, sensitivity_boundary_fraction=0.08)
    sensitivity = range_sensitivity(simple_range_callback, (0.01, 0.1), config=range_config)

    assert calls == 0
    assert bootstrap.status == "not_enabled"
    assert bootstrap.sample_count == 11
    assert bootstrap.seed == 44
    assert sensitivity.status == "not_enabled"


def test_metadata_only_callback_results_are_failed_not_fabricated_parameters(simple_fit_callback) -> None:
    def bootstrap_metadata_only(_sampled_indices: np.ndarray) -> dict[str, bool]:
        return {"converged": True}

    bootstrap_metadata_only.included_indices = simple_fit_callback.included_indices
    bootstrap = bootstrap_fit(bootstrap_metadata_only, sample_count=4, seed=12, minimum_valid_fits=3)
    sensitivity = range_sensitivity(lambda _q_range: {"converged": True}, (0.01, 0.1), minimum_valid_fits=3)

    for result, expected_failures in ((bootstrap, 4), (sensitivity, 9)):
        assert result.status == "insufficient_valid_fits"
        assert result.success_count == 0
        assert result.failure_count == expected_failures
        assert result.parameter_quantiles == {}
        assert result.coefficient_of_variation == {}
        assert result.sensitivity_score is None
        assert all(row["reason"] == "callback_returned_no_finite_parameters" for row in result.attempts)
        json.loads(json.dumps(result.to_dict(), allow_nan=False))

    mixed = bootstrap_fit(
        lambda _sampled_indices: {"converged": True, "radius": 4.0},
        included_indices=simple_fit_callback.included_indices,
        sample_count=3,
        seed=12,
        minimum_valid_fits=3,
    )
    assert set(mixed.parameter_quantiles) == {"radius"}


@pytest.mark.parametrize(
    "bad_q_range",
    [
        (0.01, 0.1, 0.2),
        (0.01,),
        "0.01,0.1",
        (np.nan, 0.1),
        (0.01, np.inf),
        (0.1, 0.01),
        (True, 0.1),
        ("0.01", "0.1"),
    ],
)
def test_range_sensitivity_rejects_every_malformed_two_bound_input(bad_q_range) -> None:
    calls = 0

    def callback(_q_range: tuple[float, float]) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"parameter": 1.0}

    result = range_sensitivity(callback, bad_q_range)

    assert calls == 0
    assert result.status == "invalid_input"
    assert result.reason == "q_range_must_contain_two_finite_ascending_bounds"
    assert result.attempts == []
    json.loads(json.dumps(result.to_dict(), allow_nan=False))


@pytest.mark.parametrize("bad_seed", [-1, 1.5, np.nan, np.inf, True])
def test_bootstrap_invalid_seed_is_structured_optional_failure_not_exception(simple_fit_callback, bad_seed) -> None:
    calls = 0

    def callback(_sampled_indices: np.ndarray) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"parameter": 1.0}

    callback.included_indices = simple_fit_callback.included_indices
    direct = bootstrap_fit(callback, sample_count=4, seed=bad_seed)
    via_config = bootstrap_fit(
        callback,
        sample_count=4,
        seed=9,
        config=SimpleNamespace(enable_bootstrap=True, bootstrap_samples=4, bootstrap_seed=bad_seed),
    )

    assert calls == 0
    for result in (direct, via_config):
        assert result.status == "invalid_input"
        assert result.reason == "seed_must_be_non_negative_finite_integer"
        assert result.seed is None
        assert result.attempts == []
        json.loads(json.dumps(result.to_dict(), allow_nan=False))


@pytest.mark.parametrize(
    "array_parameter",
    [
        np.array(7.0),
        np.array([True]),
        np.array([7.0]),
        np.array([[7.0]]),
    ],
)
def test_callback_ndarray_parameter_values_never_become_scalar_uncertainty(simple_fit_callback, array_parameter) -> None:
    def callback(_sampled_indices: np.ndarray) -> dict[str, np.ndarray]:
        return {"radius": array_parameter}

    callback.included_indices = simple_fit_callback.included_indices
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        bootstrap = bootstrap_fit(callback, sample_count=3, seed=7, minimum_valid_fits=3)
        sensitivity = range_sensitivity(lambda _q_range: {"radius": array_parameter}, (0.01, 0.1), minimum_valid_fits=3)

    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]
    for result, failure_count in ((bootstrap, 3), (sensitivity, 9)):
        assert result.status == "insufficient_valid_fits"
        assert result.success_count == 0
        assert result.failure_count == failure_count
        assert result.parameter_quantiles == {}
        assert result.sensitivity_score is None
        assert all(row["reason"] == "callback_returned_no_finite_parameters" for row in result.attempts)


@pytest.mark.parametrize(
    "bad_q_range",
    [
        np.array([[0.01], [0.1]]),
        np.array([[0.01, 0.1]]),
        np.array([0.01, 0.1, 0.2]),
        np.array(0.1),
    ],
)
def test_range_sensitivity_rejects_ndarray_ranges_without_implicit_scalar_conversion(bad_q_range) -> None:
    calls = 0

    def callback(_q_range: tuple[float, float]) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"radius": 4.0}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = range_sensitivity(callback, bad_q_range)

    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]
    assert calls == 0
    assert result.status == "invalid_input"
    assert result.reason == "q_range_must_contain_two_finite_ascending_bounds"


def test_range_sensitivity_accepts_one_dimensional_two_value_numeric_ndarray() -> None:
    calls = 0

    def callback(_q_range: tuple[float, float]) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"radius": 4.0}

    result = range_sensitivity(callback, np.array([0.01, 0.1]), minimum_valid_fits=3)

    assert calls == 9
    assert result.status == "completed"


@pytest.mark.parametrize("bad_seed", [np.array(7), np.array([7]), np.array([[7]]), 7.0])
def test_bootstrap_ndarray_or_non_integer_scalar_seed_is_invalid_before_rng(simple_fit_callback, bad_seed) -> None:
    calls = 0

    def callback(_sampled_indices: np.ndarray) -> dict[str, float]:
        nonlocal calls
        calls += 1
        return {"radius": 4.0}

    callback.included_indices = simple_fit_callback.included_indices
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        direct = bootstrap_fit(callback, sample_count=3, seed=bad_seed)
        via_config = bootstrap_fit(
            callback,
            sample_count=3,
            seed=np.int64(7),
            config=SimpleNamespace(enable_bootstrap=True, bootstrap_samples=3, bootstrap_seed=bad_seed),
        )

    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]
    assert calls == 0
    for result in (direct, via_config):
        assert result.status == "invalid_input"
        assert result.reason == "seed_must_be_non_negative_finite_integer"
        assert result.seed is None
        assert result.attempts == []

    allowed = bootstrap_fit(callback, sample_count=3, seed=np.int64(7), minimum_valid_fits=3)
    assert allowed.status == "completed"


def test_moving_block_residual_bootstrap_is_reproducible_and_keeps_block_order() -> None:
    def callback(donor_indices: np.ndarray) -> dict[str, dict[str, float]]:
        return {"parameters": {"donor_mean": float(np.mean(donor_indices))}}

    first = moving_block_residual_bootstrap_fit(
        callback,
        residual_count=12,
        sample_count=8,
        seed=41,
        block_length=3,
    )
    second = moving_block_residual_bootstrap_fit(
        callback,
        residual_count=12,
        sample_count=8,
        seed=41,
        block_length=3,
    )

    assert first.to_dict() == second.to_dict()
    assert first.status == "completed"
    for attempt in first.attempts:
        indices = attempt["resampled_indices"]
        assert attempt["q_order_preserved"] is True
        assert attempt["block_length"] == 3
        for start in range(0, len(indices), 3):
            block = indices[start : start + 3]
            assert all((right - left) % 12 == 1 for left, right in zip(block, block[1:]))


def test_range_sensitivity_clips_every_attempt_to_hard_q_boundary(simple_range_callback) -> None:
    result = range_sensitivity(
        simple_range_callback,
        (0.01, 0.05),
        hard_q_range=(0.01, 0.05),
    )

    assert result.status == "completed"
    assert all(0.01 <= row["q_range"][0] < row["q_range"][1] <= 0.05 for row in result.attempts)

def test_moving_block_bootstrap_stops_when_cancel_requested() -> None:
    state = {"n": 0}

    def callback(_indices: np.ndarray) -> dict[str, float]:
        state["n"] += 1
        return {"value": float(state["n"])}

    def cancel_after_five() -> bool:
        return state["n"] >= 5

    with cancel_scope(cancel_after_five):
        result = moving_block_residual_bootstrap_fit(
            callback,
            residual_count=24,
            sample_count=200,
            seed=3,
            minimum_valid_fits=1,
        )

    assert result.status == "cancelled"
    assert result.reason == "cancel_requested"
    assert len(result.attempts) == 5
    assert result.success_count == 5


def test_range_sensitivity_stops_when_cancel_requested(simple_range_callback) -> None:
    state = {"n": 0}

    def callback(q_range: tuple[float, float]) -> dict[str, float]:
        state["n"] += 1
        return simple_range_callback(q_range)

    def cancel_after_three() -> bool:
        return state["n"] >= 3

    with cancel_scope(cancel_after_three):
        result = range_sensitivity(callback, (0.01, 0.1), boundary_fraction=0.05, minimum_valid_fits=1)

    assert result.status == "cancelled"
    assert result.variant_count == 3
    assert len(result.attempts) == 3
