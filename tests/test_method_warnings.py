from __future__ import annotations

from app.core.data_model import CurveData
from app.core.method_warnings import guinier_warnings, invariant_warnings, peak_warnings, porod_plateau_warnings, warning_to_dict, warning_to_text
from app.core.model_free import guinier_analysis, invariant_measured, porod_metrics


def test_guinier_qrg_warning() -> None:
    warnings = guinier_warnings(qrg_max=1.5)
    assert any(w.warning_code == "GUINIER_QRG_HIGH" for w in warnings)


def test_invariant_finite_range_warning() -> None:
    warnings = invariant_warnings()
    assert any(w.warning_code == "INVARIANT_FINITE_RANGE" for w in warnings)


def test_peak_d_warning() -> None:
    warnings = peak_warnings()
    assert any(w.warning_code == "PEAK_D_NOT_DIAMETER" for w in warnings)


def test_porod_plateau_warning() -> None:
    warnings = porod_plateau_warnings([1.0, 3.0, 0.5])
    assert any(w.warning_code == "POROD_NO_STABLE_PLATEAU" for w in warnings)


def test_method_warning_serialization_helpers() -> None:
    warning = guinier_warnings(qrg_max=1.5)[0]
    payload = warning_to_dict(warning)
    assert payload["warning_code"] == "GUINIER_QRG_HIGH"
    assert "GUINIER_QRG_HIGH" in warning_to_text(warning)


def test_analysis_result_contains_structured_warnings() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2, 0.3, 0.4, 0.5], intensity=[10, 9, 8, 7, 6])
    result = guinier_analysis(curve, (0.1, 0.5))
    assert isinstance(result.structured_warnings, list)
    assert all("warning_code" in warning for warning in result.structured_warnings)


def test_invariant_and_porod_add_structured_method_warnings() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2, 0.3], intensity=[10, 9, 8])
    invariant = invariant_measured(curve, (0.1, 0.3))
    porod = porod_metrics(curve, (0.1, 0.3))
    assert any(w["warning_code"] == "INVARIANT_FINITE_RANGE" for w in invariant.structured_warnings)
    assert any(w["warning_code"] == "POROD_NO_ABSOLUTE_SURFACE" for w in porod.structured_warnings)

