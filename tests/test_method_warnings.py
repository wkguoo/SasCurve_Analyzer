from __future__ import annotations

from app.core.method_warnings import guinier_warnings, invariant_warnings, peak_warnings, porod_plateau_warnings


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

