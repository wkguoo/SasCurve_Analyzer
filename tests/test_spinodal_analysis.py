from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.data_model import CurveData
from app.core.shape_models import evaluate_model, teubner_strey_model
from app.core.spinodal_analysis import (
    analyze_spinodal_sequence,
    classify_lifshitz_regime,
    fit_teubner_strey_1d,
    spinodal_interface_and_topology,
)


def test_teubner_strey_1d_recovers_bicontinuous_and_lifshitz_regimes() -> None:
    q = np.linspace(0.05, 1.8, 120)
    # Strongly periodic spinodal: d = 30 nm, xi = 14 nm => xi/d = 0.467 => fa < 0
    d_true, xi_true = 30.0, 14.0
    I = teubner_strey_model(q, d_true, xi_true, scale=25.0, background=0.05)
    curve = CurveData.create(name="ts_spinodal", q=q, intensity=I, q_unit="nm^-1", intensity_unit="cm^-1")

    res = fit_teubner_strey_1d(curve, (0.05, 1.8), fit_background=True, background_subtracted=True)
    r = res.results
    assert r["d_ts"] == pytest.approx(d_true, rel=0.05)
    assert r["xi_ts"] == pytest.approx(xi_true, rel=0.08)
    assert r["amphiphilicity_fa"] < -0.5
    assert r["lifshitz_regime"] == "ordered_lamellar_or_strongly_periodic"
    assert r["r2_log"] > 0.999

    # Lifshitz line check: 2*pi*xi == d => fa == 0
    assert classify_lifshitz_regime(0.0) == "lifshitz_crossover"
    assert classify_lifshitz_regime(-0.25) == "bicontinuous_spinodal"
    assert classify_lifshitz_regime(0.6) == "disordered_structured_fluid"
    assert np.allclose(evaluate_model("teubner_strey", q, [d_true, xi_true, 25.0, 0.05]), I)


def test_spinodal_interface_chord_length_is_scale_invariant_and_gates_sigma_rho() -> None:
    # Build two-phase curve with diffuse Ruland high-q damping: I(q) = F(q) * exp(-sigma^2 * q^2) + K/q^4...
    # Cleaner: Teubner-Strey at high q decays strictly as K_inf * q^-4 -> sigma_int ~ 0 -> exact l_P = 4Q/(pi K_P)!
    # Also test Ruland Gaussian smoothing I(q) = I_sharp(q) * exp(-sigma^2 * q^2).
    q = np.linspace(0.06, 2.5, 250)
    d_true, xi_true = 25.0, 10.0
    I_raw = teubner_strey_model(q, d_true, xi_true, scale=40.0, background=0.0)
    sigma_true = 0.28
    I_diff = I_raw * np.exp(-(sigma_true ** 2) * (q ** 2))

    c1 = CurveData.create(name="uncal", q=q, intensity=I_diff, q_unit="nm^-1", intensity_unit="a.u.")
    c100 = CurveData.create(name="scaled", q=q, intensity=I_diff * 100.0, q_unit="nm^-1", intensity_unit="cm^-1")

    r1 = spinodal_interface_and_topology(
        c1, (0.06, 2.5), background_subtracted=True, absolute_intensity=False, porod_q_range=(1.0, 2.2)
    ).results
    r100 = spinodal_interface_and_topology(
        c100, (0.06, 2.5), background_subtracted=True, absolute_intensity=True, porod_q_range=(1.0, 2.2)
    ).results

    # Scale invariance of l_P, S_V/(phi*(1-phi)), q1_lP, and Ruland sigma_int!
    assert r1["l_P"] is not None and r1["l_P"] > 0.0
    assert r1["l_P"] == pytest.approx(r100["l_P"], rel=1e-6)
    assert r1["q1_lP"] == pytest.approx(r100["q1_lP"], rel=1e-6)
    assert r1["ruland_sigma_int"] == pytest.approx(sigma_true, abs=0.08)
    assert r1["ruland_sigma_int"] == pytest.approx(r100["ruland_sigma_int"], rel=1e-6)

    # Strict calibration gate: uncalibrated must withhold sigma_rho; calibrated must compute exact sqrt(Q_3d/(2*pi^2))
    assert r1["sigma_rho_A_inv2"] is None
    assert r100["sigma_rho_A_inv2"] is not None and r100["sigma_rho_A_inv2"] > 0.0
    Q_A3 = r100["Q_win_cm_inv_A_inv3"]
    assert r100["sigma_rho_A_inv2"] == pytest.approx(math.sqrt(1e-8 * Q_A3 / (2.0 * math.pi ** 2)), rel=1e-9)


def test_analyze_spinodal_sequence_excess_scattering_preserves_inputs() -> None:
    q = np.linspace(0.08, 2.2, 160)
    # Static RT background + evolving excess Teubner-Strey wave with slow coarsening & growth
    I_rt = 2.0 * (q ** -3.8) + 0.3
    times = np.array([0.0, 10.0, 20.0, 40.0, 80.0, 160.0])
    curves = []
    for k, t in enumerate(times):
        if k == 0:
            I_tot = I_rt.copy()
        else:
            d_t = 22.0 * (t / 10.0) ** 0.12
            I_ex = (8.0 * (t / 10.0) ** 0.45) * teubner_strey_model(q, d_t, 0.45 * d_t, scale=1.0, background=0.0)
            I_tot = I_rt + I_ex
        curves.append(CurveData.create(name=f"f{k}", q=q, intensity=I_tot, q_unit="nm^-1", intensity_unit="cm^-1"))

    orig_q0 = curves[1].q.copy()
    orig_I0 = curves[1].intensity.copy()
    seq = analyze_spinodal_sequence(curves, times=times, reference_mode="first", absolute_intensity=True)
    np.testing.assert_array_equal(curves[1].q, orig_q0)
    np.testing.assert_array_equal(curves[1].intensity, orig_I0)

    assert seq["status"] == "estimated"
    assert seq["joint_exponents"]["a"] == pytest.approx(0.12, abs=0.04)
    assert seq["joint_exponents"]["ba_ratio"] > 3.0
    assert seq["collapse_cv_late"] < 0.12
    assert seq["frames"][-1]["amphiphilicity_fa"] < 0.0
