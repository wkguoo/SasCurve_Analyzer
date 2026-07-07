from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.validation import validate_curve


def make_curve(q, intensity, error=None) -> CurveData:
    return CurveData.create(name="test", q=q, intensity=intensity, error=error)


def issue_codes(curve: CurveData) -> set[str]:
    return {issue.code for issue in validate_curve(curve).issues}


def test_monotonic_q_has_no_q_order_warning() -> None:
    curve = make_curve([0.1, 0.2, 0.3], [10, 8, 6])
    assert "q_not_monotonic" not in issue_codes(curve)


def test_duplicate_q_warning() -> None:
    curve = make_curve([0.1, 0.2, 0.2], [10, 8, 7])
    codes = issue_codes(curve)
    assert "q_duplicate" in codes
    assert "q_not_monotonic" in codes


def test_nan_warnings() -> None:
    curve = make_curve([0.1, np.nan, 0.3], [10, np.nan, 6])
    codes = issue_codes(curve)
    assert "q_nan" in codes
    assert "intensity_nan" in codes


def test_negative_intensity_warning() -> None:
    curve = make_curve([0.1, 0.2, 0.3], [10, -1, 0])
    codes = issue_codes(curve)
    assert "intensity_negative" in codes
    assert "intensity_zero" in codes


def test_slight_negative_intensity_is_classified_as_info() -> None:
    q = np.linspace(0.1, 2.1, 21)
    intensity = np.linspace(10.0, 8.0, 21)
    intensity[-1] = -0.001
    curve = make_curve(q, intensity)
    report = validate_curve(curve)
    issues = {issue.code: issue for issue in report.issues}

    assert "intensity_slight_negative" in issues
    assert issues["intensity_slight_negative"].severity == "info"
    assert "intensity_negative" not in issues
    assert report.summary["negative_I_count"] == 1
    assert report.summary["negative_I_fraction"] < 0.05
    assert report.summary["log_invalid_points"] == 1


def test_significant_negative_intensity_still_warns() -> None:
    curve = make_curve([0.1, 0.2, 0.3, 0.4], [10.0, 9.0, 8.0, -1.0])
    report = validate_curve(curve)
    codes = {issue.code for issue in report.issues}

    assert "intensity_negative" in codes
    assert "intensity_slight_negative" not in codes
    assert report.summary["I_min_abs_ratio_to_positive_median"] > 1e-3
    assert report.summary["positive_dynamic_range"] > 1.0


def test_slight_negative_can_be_disabled_by_setting() -> None:
    q = np.linspace(0.1, 2.1, 21)
    intensity = np.linspace(10.0, 8.0, 21)
    intensity[-1] = -0.001
    curve = make_curve(q, intensity)

    report = validate_curve(curve, allow_slight_negative_intensity=False)
    codes = {issue.code for issue in report.issues}

    assert "intensity_negative" in codes
    assert "intensity_slight_negative" not in codes
    assert report.summary["allow_slight_negative_intensity"] is False


def test_slight_negative_thresholds_are_reported_and_configurable() -> None:
    q = np.linspace(0.1, 2.1, 21)
    intensity = np.linspace(10.0, 8.0, 21)
    intensity[-1] = -0.01
    curve = make_curve(q, intensity)

    strict_report = validate_curve(curve, slight_negative_abs_ratio_threshold=1e-4)
    lenient_report = validate_curve(curve, slight_negative_abs_ratio_threshold=0.01)

    assert "intensity_negative" in {issue.code for issue in strict_report.issues}
    assert "intensity_slight_negative" in {issue.code for issue in lenient_report.issues}
    assert lenient_report.summary["slight_negative_abs_ratio_threshold"] == 0.01
    assert lenient_report.summary["slight_negative_fraction_threshold"] == 0.05


def test_error_warnings() -> None:
    curve = make_curve([0.1, 0.2, 0.3], [10, 8, 6], error=[0.1, 0.0, -1.0])
    codes = issue_codes(curve)
    assert "error_zero" in codes
    assert "error_negative" in codes
