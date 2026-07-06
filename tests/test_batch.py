from __future__ import annotations

import numpy as np

from app.core.batch import average_replicates
from app.core.data_model import CurveData


def test_average_matching_q_grid() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20], error=[1, 1])
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[14, 22], error=[1, 1])
    averaged, record = average_replicates([c1, c2], interpolate=False)
    assert np.allclose(averaged.q, [0.1, 0.2])
    assert np.allclose(averaged.intensity, [12, 21])
    assert record.action_type == "average_replicates"


def test_average_interpolates_mismatched_q_grid() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2, 0.3], intensity=[10, 20, 30])
    c2 = CurveData.create(name="b", q=[0.15, 0.25, 0.35], intensity=[15, 25, 35])
    averaged, record = average_replicates([c1, c2], interpolate=True)
    assert averaged.q.min() >= 0.15
    assert averaged.q.max() <= 0.3
    assert record.warnings


def test_average_does_not_modify_original_curves() -> None:
    c1 = CurveData.create(name="a", q=[0.1, 0.2], intensity=[10, 20])
    original = c1.intensity.copy()
    c2 = CurveData.create(name="b", q=[0.1, 0.2], intensity=[14, 22])
    averaged, _record = average_replicates([c1, c2])
    assert np.allclose(c1.intensity, original)
    assert averaged.curve_id != c1.curve_id

