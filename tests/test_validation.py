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


def test_error_warnings() -> None:
    curve = make_curve([0.1, 0.2, 0.3], [10, 8, 6], error=[0.1, 0.0, -1.0])
    codes = issue_codes(curve)
    assert "error_zero" in codes
    assert "error_negative" in codes

