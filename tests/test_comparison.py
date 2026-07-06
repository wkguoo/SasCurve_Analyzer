from __future__ import annotations

import numpy as np

from app.core.comparison import compare_curves, normalized_intensity
from app.core.data_model import CurveData


def test_difference() -> None:
    a = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20])
    b = CurveData.create(name="b", q=[0.1, 0.2], intensity=[12, 17])
    result = compare_curves(a, b, "difference")
    assert np.allclose(result.values, [2, -3])


def test_ratio() -> None:
    a = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20])
    b = CurveData.create(name="b", q=[0.1, 0.2], intensity=[20, 10])
    result = compare_curves(a, b, "ratio")
    assert np.allclose(result.values, [2.0, 0.5])


def test_relative_difference_and_zero_warning() -> None:
    a = CurveData.create(name="a", q=[0.1, 0.2], intensity=[0, 20])
    b = CurveData.create(name="b", q=[0.1, 0.2], intensity=[20, 10])
    result = compare_curves(a, b, "relative_difference")
    assert result.q.size == 1
    assert np.allclose(result.values, [-0.5])
    assert result.warnings


def test_display_normalization() -> None:
    curve = CurveData.create(name="n", q=[0.1, 0.2], intensity=[2, 4])
    normalized, warnings = normalized_intensity(curve, "I/Imax")
    assert np.allclose(normalized, [0.5, 1.0])
    assert warnings

