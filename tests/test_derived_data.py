from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.data_model import CurveData
from app.core.derived_data import (
    DerivedDataOptions,
    build_curve_derived_table,
)


def assert_close(actual, expected) -> None:
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-15, equal_nan=True)


def test_derived_table_computes_core_formulas() -> None:
    q = np.array([0.1, 0.2, 0.4], dtype=float)
    intensity = np.array([10.0, 5.0, 2.5], dtype=float)
    curve = CurveData.create(name="curve", q=q, intensity=intensity)

    result = build_curve_derived_table(curve, options=DerivedDataOptions(alpha=4.0, rg=3.0, diameter=10.0, radius=5.0))
    table = result.table

    assert_close(table["q2"], q**2)
    assert_close(table["ln_q"], np.log(q))
    assert_close(table["log10_q"], np.log10(q))
    assert_close(table["inv_q"], 1 / q)
    assert_close(table["d_2pi_over_q"], 2 * np.pi / q)
    assert_close(table["ln_I"], np.log(intensity))
    assert_close(table["log10_I"], np.log10(intensity))
    assert_close(table["qI"], q * intensity)
    assert_close(table["q2I"], q**2 * intensity)
    assert_close(table["q3I"], q**3 * intensity)
    assert_close(table["q4I"], q**4 * intensity)
    assert_close(table["q_alpha_I"], q**4 * intensity)
    assert_close(table["qRg"], q * 3.0)
    assert_close(table["qD"], q * 10.0)
    assert_close(table["qR"], q * 5.0)
    assert set(["q2", "ln_q", "q4I"]).issubset(result.units)
    assert "log10(q)" in result.formulas["log10_q"]


def test_derived_table_preserves_invalid_q_rows_and_flags() -> None:
    curve = CurveData.create(name="curve", q=[-0.1, 0.0, 0.2], intensity=[10.0, 5.0, 2.5])

    table = build_curve_derived_table(curve).table

    assert table["q"].tolist() == [-0.1, 0.0, 0.2]
    assert_close(table["ln_q"], [np.nan, np.nan, np.log(0.2)])
    assert_close(table["log10_q"], [np.nan, np.nan, np.log10(0.2)])
    assert_close(table["d_2pi_over_q"], [np.nan, np.nan, 2 * np.pi / 0.2])
    assert table["valid_ln_q"].tolist() == [False, False, True]
    assert table["valid_log10_q"].tolist() == [False, False, True]
    assert table["valid_d_2pi_over_q"].tolist() == [False, False, True]


def test_derived_table_q_range_keeps_only_selected_rows_and_source_indices() -> None:
    curve = CurveData.create(
        name="limited",
        q=[0.005, 0.01, 0.02, 0.05, 0.1],
        intensity=[5.0, 4.0, 3.0, 2.0, 1.0],
    )

    result = build_curve_derived_table(curve, q_range=(0.01, 0.05))

    assert result.table["q"].tolist() == [0.01, 0.02, 0.05]
    assert result.table["row_index"].tolist() == [1, 2, 3]
    assert result.metadata["row_count"] == 3
    assert result.metadata["source_row_count"] == 5
    assert result.metadata["q_range"] == (0.01, 0.05)


def test_derived_table_preserves_invalid_intensity_rows_and_flags() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2, 0.3], intensity=[10.0, 0.0, -1.0])

    table = build_curve_derived_table(curve).table

    assert table["I"].tolist() == [10.0, 0.0, -1.0]
    assert_close(table["ln_I"], [np.log(10.0), np.nan, np.nan])
    assert_close(table["log10_I"], [np.log10(10.0), np.nan, np.nan])
    assert table["valid_ln_I"].tolist() == [True, False, False]
    assert table["valid_log10_I"].tolist() == [True, False, False]
    assert table["valid_local_slope"].tolist() == [False, False, False]


def test_q_alpha_matches_fixed_power_columns() -> None:
    q = np.array([0.1, 0.2, 0.4], dtype=float)
    intensity = np.array([10.0, 5.0, 2.5], dtype=float)
    curve = CurveData.create(name="curve", q=q, intensity=intensity)

    alpha4 = build_curve_derived_table(curve, options=DerivedDataOptions(alpha=4.0)).table
    alpha2 = build_curve_derived_table(curve, options=DerivedDataOptions(alpha=2.0)).table

    assert_close(alpha4["q_alpha_I"], alpha4["q4I"])
    assert_close(alpha2["q_alpha_I"], alpha2["q2I"])


def test_parameter_columns_require_explicit_values() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10.0, 5.0])

    missing = build_curve_derived_table(curve)
    provided = build_curve_derived_table(curve, options=DerivedDataOptions(rg=10.0, diameter=20.0, radius=5.0))

    assert_close(missing.table["qRg"], [np.nan, np.nan])
    assert any("Rg was not provided" in warning for warning in missing.warnings)
    assert_close(provided.table["qRg"], [1.0, 2.0])
    assert_close(provided.table["qD"], [2.0, 4.0])
    assert_close(provided.table["qR"], [0.5, 1.0])


def test_optional_parameter_warnings_can_be_suppressed_for_plot_analysis() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10.0, 5.0])

    quiet = build_curve_derived_table(curve, options=DerivedDataOptions(include_optional_parameter_warnings=False))
    verbose = build_curve_derived_table(curve)

    quiet_text = "\n".join(quiet.warnings)
    verbose_text = "\n".join(verbose.warnings)
    assert "q_alpha_I is NaN" not in quiet_text
    assert "qRg is NaN" not in quiet_text
    assert "no reference curve was provided" not in quiet_text
    assert "q_alpha_I is NaN" in verbose_text
    assert "qRg is NaN" in verbose_text


def test_reference_ratio_and_difference_require_matching_q_grid() -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10.0, 5.0])
    reference = CurveData.create(name="ref", q=[0.1, 0.2], intensity=[2.0, 0.0])
    mismatch = CurveData.create(name="mismatch", q=[0.1, 0.25], intensity=[2.0, 4.0])

    matched = build_curve_derived_table(curve, reference_curve=reference)
    mismatched = build_curve_derived_table(curve, reference_curve=mismatch)

    assert_close(matched.table["I_over_ref"], [5.0, np.nan])
    assert_close(matched.table["I_minus_ref"], [8.0, 5.0])
    assert matched.table["valid_I_over_ref"].tolist() == [True, False]
    assert_close(mismatched.table["I_over_ref"], [np.nan, np.nan])
    assert any("q grid differs" in warning for warning in mismatched.warnings)


def test_local_slope_matches_power_law_exponent() -> None:
    q = np.array([0.1, 0.2, 0.4, 0.8, 1.6], dtype=float)
    intensity = 3.0 * q**-4
    curve = CurveData.create(name="power", q=q, intensity=intensity)

    table = build_curve_derived_table(curve).table

    assert_close(table["local_slope_dlnI_dlnq"], [-4.0, -4.0, -4.0, -4.0, -4.0])
    assert_close(table["alpha_local"], [4.0, 4.0, 4.0, 4.0, 4.0])


def test_export_csv_round_trip_preserves_derived_values(tmp_path) -> None:
    curve = CurveData.create(name="curve", q=[0.1, 0.2, 0.4], intensity=[10.0, 5.0, 2.5])
    table = build_curve_derived_table(curve, options=DerivedDataOptions(alpha=4.0)).table
    path = tmp_path / "curve_derived.csv"

    table.to_csv(path, index=False)
    loaded = pd.read_csv(path)

    assert_close(loaded["q2"], table["q2"])
    assert_close(loaded["ln_q"], table["ln_q"])
    assert_close(loaded["q4I"], table["q4I"])
    assert_close(loaded["q_alpha_I"], table["q_alpha_I"])
