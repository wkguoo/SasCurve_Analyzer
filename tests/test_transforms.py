from __future__ import annotations

import numpy as np

from app.core.data_model import CurveData
from app.core.transforms import convert_q_unit


def test_angstrom_to_nm_conversion() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2], intensity=[10, 5], q_unit="A^-1")
    converted = convert_q_unit(curve, "nm^-1")
    assert converted.q_unit == "nm^-1"
    assert np.allclose(converted.q, [1.0, 2.0])


def test_nm_to_angstrom_conversion() -> None:
    curve = CurveData.create(name="test", q=[1.0, 2.0], intensity=[10, 5], q_unit="nm^-1")
    converted = convert_q_unit(curve, "A^-1")
    assert converted.q_unit == "A^-1"
    assert np.allclose(converted.q, [0.1, 0.2])


def test_conversion_does_not_modify_original_curve() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2], intensity=[10, 5], q_unit="A^-1")
    original_q = curve.q.copy()
    converted = convert_q_unit(curve, "nm^-1")
    assert np.allclose(curve.q, original_q)
    assert converted.curve_id != curve.curve_id
    assert converted.parent_id == curve.curve_id


def test_processing_history_is_written() -> None:
    curve = CurveData.create(name="test", q=[0.1, 0.2], intensity=[10, 5], q_unit="A^-1")
    converted = convert_q_unit(curve, "nm^-1")
    assert converted.processing_history[-1]["action"] == "convert_q_unit"
    assert converted.processing_history[-1]["factor"] == 10.0

