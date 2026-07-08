from __future__ import annotations

import numpy as np
import pytest

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


def test_comparison_interpolates_after_sorting_unsorted_q() -> None:
    a = CurveData.create(name="a", q=[0.3, 0.1, 0.2], intensity=[30, 10, 20])
    b = CurveData.create(name="b", q=[0.1, 0.2, 0.3], intensity=[11, 22, 33])

    result = compare_curves(a, b, "difference", interpolate=True)

    assert np.allclose(result.q, [0.1, 0.2, 0.3])
    assert np.allclose(result.values, [1, 2, 3])


def test_compare_rejects_mismatched_q_units() -> None:
    a = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20], q_unit="A^-1")
    b = CurveData.create(name="b", q=[0.1, 0.2], intensity=[12, 17], q_unit="nm^-1")

    with pytest.raises(ValueError, match="q units differ"):
        compare_curves(a, b, "difference")


def test_compare_rejects_mismatched_intensity_units() -> None:
    a = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20], intensity_unit="cm^-1")
    b = CurveData.create(name="b", q=[0.1, 0.2], intensity=[12, 17], intensity_unit="a.u.")

    with pytest.raises(ValueError, match="intensity units differ"):
        compare_curves(a, b, "difference")


def test_display_normalization() -> None:
    curve = CurveData.create(name="n", q=[0.1, 0.2], intensity=[2, 4])
    normalized, warnings = normalized_intensity(curve, "I/Imax")
    assert np.allclose(normalized, [0.5, 1.0])
    assert warnings


def test_q_reference_normalization_uses_sorted_q_for_interpolation() -> None:
    curve = CurveData.create(name="n", q=[0.3, 0.1, 0.2], intensity=[30, 10, 20])

    normalized, _warnings = normalized_intensity(curve, "I/I(q_ref)", q_ref=0.15)

    assert np.allclose(normalized, [2.0, 2.0 / 3.0, 4.0 / 3.0])


def test_integral_normalization_uses_sorted_q_for_positive_area() -> None:
    curve = CurveData.create(name="n", q=[0.3, 0.1, 0.2], intensity=[30, 10, 20])

    normalized_area, _warnings = normalized_intensity(curve, "I/area")
    normalized_invariant, _warnings = normalized_intensity(curve, "I/Q_measured")

    assert np.all(normalized_area > 0)
    assert np.all(normalized_invariant > 0)

