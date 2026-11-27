"""1D metallic spinodal decomposition diagnostics: Teubner-Strey, interface topology, and sequences."""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from scipy.optimize import least_squares

from app.core.analysis_schema import (
    EXPORT_TABLE_FIT_CURVES,
    EXPORT_TABLE_RESIDUALS,
    RESULT_GROUP_TWO_PHASE,
    merge_standard_metadata,
)
from app.core.data_model import AnalysisResult, CurveData
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks
from app.core.transforms import normalize_q_unit


def _finite_scalar(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _length_unit(q_unit: str) -> str:
    try:
        canon = normalize_q_unit(q_unit)
    except ValueError:
        return f"1/({q_unit or 'q'})"
    return "nm" if canon == "nm^-1" else "A"


def _clean_curve_arrays(
    curve: CurveData,
    q_range: tuple[float, float] | None,
    *,
    positive_intensity: bool = False,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    q_all = np.asarray(curve.q, dtype=float)
    I_all = np.asarray(curve.intensity, dtype=float)
    if q_range is None:
        fin = np.isfinite(q_all) & (q_all > 0.0)
        if not np.any(fin):
            return np.empty(0, dtype=float), np.empty(0, dtype=float), (0.0, 0.0)
        q_lo, q_hi = float(np.min(q_all[fin])), float(np.max(q_all[fin]))
    else:
        q_lo, q_hi = float(q_range[0]), float(q_range[1])
        if not (math.isfinite(q_lo) and math.isfinite(q_hi)) or q_lo > q_hi:
            raise ValueError("q_range must contain finite bounds with q_min <= q_max.")

    mask = np.isfinite(q_all) & np.isfinite(I_all) & (q_all > 0.0) & (q_all >= q_lo) & (q_all <= q_hi)
    if positive_intensity:
        mask &= I_all > 0.0
    q_sel = q_all[mask]
    I_sel = I_all[mask]
    if q_sel.size > 1:
        order = np.argsort(q_sel, kind="stable")
        q_sel = q_sel[order]
        I_sel = I_sel[order]
    return q_sel, I_sel, (q_lo, q_hi)


def classify_lifshitz_regime(fa: float | None) -> str:
    """Classify Teubner-Strey amphiphilicity ``f_a`` relative to the Lifshitz line."""
    if fa is None or not math.isfinite(fa):
        return "unavailable"
    if fa < -0.5:
        return "ordered_lamellar_or_strongly_periodic"
    if fa < -0.05:
        return "bicontinuous_spinodal"
    if fa <= 0.05:
        return "lifshitz_crossover"
    if fa < 1.0:
        return "disordered_structured_fluid"
    return "ornstein_zernike_disordered"


def fit_teubner_strey_1d(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    fit_background: bool = True,
    background_subtracted: bool = False,
) -> AnalysisResult:
    """Fit the Teubner-Strey two-phase correlation model to extract ``(d_TS, xi_TS, f_a)``.

    Multi-seed log-residual bounded optimization avoids trapping on low-q tails and
    extracts the universal Lifshitz/amphiphilicity factor ``f_a``.
    """
    q_sel, I_sel, eff_range = _clean_curve_arrays(curve, q_range, positive_intensity=True)
    n_pts = int(q_sel.size)
    len_unit = _length_unit(curve.q_unit)

    if n_pts < 10 or float(np.ptp(q_sel)) <= 1e-12:
        checks = [
            validity_check(
                "enough_positive_points",
                False,
                severity="error",
                message="Teubner-Strey fitting needs at least 10 positive finite points.",
                value=n_pts,
                threshold=10,
            )
        ]
        results = merge_standard_metadata(
            {
                "d_ts": None,
                "xi_ts": None,
                "amphiphilicity_fa": None,
                "xi_over_d": None,
                "q_peak_ts": None,
                "lifshitz_regime": "unavailable",
                "log_rmse": None,
                "r2_log": None,
                "n_points": n_pts,
                "length_unit": len_unit,
            },
            result_group=RESULT_GROUP_TWO_PHASE,
            reliability_label="invalid",
            reliability_score=0.0,
            assumptions=["two_phase_required", "teubner_strey_bicontinuous_assumption"],
            validity_checks=checks,
        )
        return AnalysisResult.create(
            curve=curve,
            analysis_type="teubner_strey_1d",
            q_range=eff_range,
            parameters={"fit_background": bool(fit_background), "background_subtracted": bool(background_subtracted)},
            results=results,
            warnings=warning_messages_from_checks(checks),
        )

    idx_pk = int(np.argmax(I_sel))
    q_pk_obs = float(q_sel[idx_pk])
    I_pk_obs = float(I_sel[idx_pk])
    d_lo = max(2.0 * math.pi / float(q_sel[-1]) * 0.5, 1e-4)
    d_hi = min(2.0 * math.pi / float(q_sel[0]) * 5.0, 1e5)
    xi_lo = max(0.05 / float(q_sel[-1]), 1e-4)
    xi_hi = min(200.0 / max(q_pk_obs, float(q_sel[0])), 1e5)

    bg_cap = float(np.percentile(I_sel, 25)) if fit_background else 0.0
    bg_hi = max(bg_cap, 1e-9) if fit_background else 1e-12

    ln_I_obs = np.log(I_sel)
    k_seeds = [q_pk_obs, max(float(q_sel[0]) * 1.4, q_pk_obs * 1.25), float(np.median(q_sel))]
    xi_mults = [1.5, 0.5, 4.0]

    best_fit = None
    best_cost = float("inf")

    def _eval(p: np.ndarray, qv: np.ndarray) -> np.ndarray:
        sc = math.exp(float(p[0]))
        k2 = (2.0 * math.pi / float(p[1])) ** 2
        inv_xi2 = 1.0 / (float(p[2]) ** 2)
        a2 = (k2 + inv_xi2) ** 2
        c1 = 2.0 * (inv_xi2 - k2)
        bkg = float(p[3]) if fit_background else 0.0
        denom = np.maximum(a2 + c1 * (qv ** 2) + (qv ** 4), 1e-30)
        return sc * (a2 / denom) + bkg

    for k0 in k_seeds:
        d0 = float(np.clip(2.0 * math.pi / max(k0, 1e-8), d_lo * 1.05, d_hi * 0.95))
        for xm in xi_mults:
            xi0 = float(np.clip(xm * d0 / (2.0 * math.pi), xi_lo * 1.05, xi_hi * 0.95))
            k2_0 = (2.0 * math.pi / d0) ** 2
            ix2_0 = 1.0 / (xi0 ** 2)
            fa0 = (ix2_0 - k2_0) / (ix2_0 + k2_0)
            sc0 = max(I_pk_obs * max(1.0 - fa0 ** 2, 0.05), 1e-12)
            if fit_background:
                p0 = np.array([math.log(sc0), d0, xi0, min(0.1 * bg_hi, bg_hi * 0.5)], dtype=float)
                lo = np.array([-35.0, d_lo, xi_lo, 0.0], dtype=float)
                hi = np.array([35.0, d_hi, xi_hi, bg_hi], dtype=float)
            else:
                p0 = np.array([math.log(sc0), d0, xi0], dtype=float)
                lo = np.array([-35.0, d_lo, xi_lo], dtype=float)
                hi = np.array([35.0, d_hi, xi_hi], dtype=float)
            try:
                res = least_squares(
                    lambda p: np.log(np.maximum(_eval(p, q_sel), 1e-30)) - ln_I_obs,
                    p0,
                    bounds=(lo, hi),
                    max_nfev=800,
                )
            except (ValueError, RuntimeError, FloatingPointError):
                continue
            if math.isfinite(float(res.cost)) and float(res.cost) < best_cost:
                best_cost = float(res.cost)
                best_fit = res

    if best_fit is None:
        checks = [validity_check("optimizer_converged", False, severity="error", message="Teubner-Strey optimizer failed.")]
        results = merge_standard_metadata(
            {
                "d_ts": None,
                "xi_ts": None,
                "amphiphilicity_fa": None,
                "xi_over_d": None,
                "q_peak_ts": None,
                "lifshitz_regime": "unavailable",
                "log_rmse": None,
                "r2_log": None,
                "n_points": n_pts,
                "length_unit": len_unit,
            },
            result_group=RESULT_GROUP_TWO_PHASE,
            reliability_label="invalid",
            reliability_score=0.0,
            assumptions=["two_phase_required", "teubner_strey_bicontinuous_assumption"],
            validity_checks=checks,
        )
        return AnalysisResult.create(
            curve=curve,
            analysis_type="teubner_strey_1d",
            q_range=eff_range,
            parameters={"fit_background": bool(fit_background)},
            results=results,
            warnings=warning_messages_from_checks(checks),
        )

    pred = _eval(best_fit.x, q_sel)
    log_resid = ln_I_obs - np.log(np.maximum(pred, 1e-30))
    log_sse = float(np.sum(log_resid ** 2))
    log_sst = float(np.sum((ln_I_obs - float(np.mean(ln_I_obs))) ** 2))
    r2_log = _finite_scalar(1.0 - log_sse / log_sst) if log_sst > 1e-30 else 1.0
    log_rmse = _finite_scalar(math.sqrt(log_sse / float(n_pts)))

    d_ts = float(best_fit.x[1])
    xi_ts = float(best_fit.x[2])
    scale_val = math.exp(float(best_fit.x[0]))
    bkg_val = float(best_fit.x[3]) if fit_background else 0.0
    k2_f = (2.0 * math.pi / d_ts) ** 2
    ix2_f = 1.0 / (xi_ts ** 2)
    fa = (ix2_f - k2_f) / (ix2_f + k2_f)
    q_pk_ts = _finite_scalar(math.sqrt(k2_f - ix2_f)) if k2_f > ix2_f else None
    regime = classify_lifshitz_regime(fa)

    at_bound = (
        abs(d_ts - d_lo) <= 1e-4 * max(d_lo, 1.0)
        or abs(d_ts - d_hi) <= 1e-4 * max(d_hi, 1.0)
        or abs(xi_ts - xi_lo) <= 1e-4 * max(xi_lo, 1.0)
        or abs(xi_ts - xi_hi) <= 1e-4 * max(xi_hi, 1.0)
    )
    assumptions = ["two_phase_required", "teubner_strey_bicontinuous_assumption"]
    if not background_subtracted:
        assumptions.append("background_subtracted_not_verified")
    checks = [
        validity_check("optimizer_converged", bool(best_fit.success), severity="warning", message="Optimizer reached iteration cap."),
        validity_check("good_log_fit", (r2_log or 0.0) >= 0.90, severity="warning", message="Teubner-Strey log R^2 is below 0.90.", value=r2_log, threshold=0.90),
        validity_check("parameters_interior", not at_bound, severity="warning", message="d_ts or xi_ts hit optimization boundary."),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)

    fit_rows = [
        {"q": float(qv), "I_observed": float(iv), "I_fitted": float(pv)}
        for qv, iv, pv in zip(q_sel, I_sel, pred)
    ]
    resid_rows = [
        {"q": float(qv), "log_residual": float(rv)}
        for qv, rv in zip(q_sel, log_resid)
    ]
    results = merge_standard_metadata(
        {
            "d_ts": _finite_scalar(d_ts),
            "xi_ts": _finite_scalar(xi_ts),
            "amphiphilicity_fa": _finite_scalar(fa),
            "xi_over_d": _finite_scalar(xi_ts / d_ts),
            "q_peak_ts": q_pk_ts,
            "scale": _finite_scalar(scale_val),
            "background": _finite_scalar(bkg_val),
            "lifshitz_regime": regime,
            "log_rmse": log_rmse,
            "r2_log": r2_log,
            "n_points": n_pts,
            "length_unit": len_unit,
            "at_bound": bool(at_bound),
        },
        result_group=RESULT_GROUP_TWO_PHASE,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "Teubner-Strey assumes a bicontinuous two-phase Gaussian random field; f_a < 0 corresponds to correlated spinodal/microemulsion waves, f_a = 0 to the Lifshitz line."
        ],
        export_tables={EXPORT_TABLE_FIT_CURVES: fit_rows, EXPORT_TABLE_RESIDUALS: resid_rows},
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="teubner_strey_1d",
        q_range=eff_range,
        parameters={"fit_background": bool(fit_background), "background_subtracted": bool(background_subtracted)},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )


def spinodal_interface_and_topology(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    *,
    background_subtracted: bool = False,
    absolute_intensity: bool = False,
    porod_q_range: tuple[float, float] | None = None,
    q_peak: float | None = None,
) -> AnalysisResult:
    """Compute Porod chord length ``l_P = 4Q/(pi K_P)``, Ruland diffuse width ``sigma_int``,
    dimensionless topology invariants ``q1 * l_P`` / ``qm * l_P``, and (strictly gated)
    model-free RMS SLD fluctuation ``sigma_rho``.

    Notice ``l_P`` and ``S_V / [phi(1-phi)] = 4 / l_P`` are scale- and contrast-invariant
    whenever high-q background is properly removed.
    """
    q_sel, I_sel, eff_range = _clean_curve_arrays(curve, q_range, positive_intensity=False)
    n_pts = int(q_sel.size)
    len_unit = _length_unit(curve.q_unit)

    if n_pts < 12 or float(np.ptp(q_sel)) <= 1e-12:
        checks = [
            validity_check("enough_points", False, severity="error", message="Need at least 12 points in q_range.", value=n_pts, threshold=12)
        ]
        results = merge_standard_metadata(
            {
                "Q_win": None,
                "q1_moment": None,
                "q_peak": None,
                "K_porod": None,
                "porod_exponent": None,
                "l_P": None,
                "S_V_over_phi_1mphi": None,
                "q1_lP": None,
                "qm_lP": None,
                "ruland_sigma_int": None,
                "ruland_r2": None,
                "sigma_rho_A_inv2": None,
                "length_unit": len_unit,
            },
            result_group=RESULT_GROUP_TWO_PHASE,
            reliability_label="invalid",
            reliability_score=0.0,
            assumptions=["background_subtracted_required_for_porod"],
            validity_checks=checks,
        )
        return AnalysisResult.create(
            curve=curve,
            analysis_type="spinodal_interface_topology",
            q_range=eff_range,
            parameters={"background_subtracted": bool(background_subtracted), "absolute_intensity": bool(absolute_intensity)},
            results=results,
            warnings=warning_messages_from_checks(checks),
        )

    I_pos = np.maximum(I_sel, 0.0)
    Q_win = _finite_scalar(np.trapezoid(I_pos * (q_sel ** 2), q_sel))
    if Q_win is None or Q_win <= 0.0:
        Q_win = None
        q1_val = None
    else:
        q1_val = _finite_scalar(np.trapezoid(I_pos * (q_sel ** 3), q_sel) / Q_win)

    idx_pk = int(np.argmax(I_pos))
    edge_pk = (idx_pk == 0) or (idx_pk == n_pts - 1)
    q_pk_val = _finite_scalar(q_peak) if (q_peak is not None and _finite_scalar(q_peak) is not None and float(q_peak) > 0.0) else (_finite_scalar(q_sel[idx_pk]) if not edge_pk else None)

    if porod_q_range is not None:
        plo, phi_q = float(porod_q_range[0]), float(porod_q_range[1])
        tail_mask = (q_sel >= plo) & (q_sel <= phi_q) & (I_pos > 0.0)
    else:
        q_ref = q_pk_val if q_pk_val is not None else (q1_val if q1_val is not None else float(q_sel[n_pts // 3]))
        q_tail_lo = min(max(2.0 * q_ref, float(q_sel[max(0, (2 * n_pts) // 3)])), float(q_sel[-min(10, n_pts)]))
        tail_mask = (q_sel >= q_tail_lo) & (I_pos > 0.0)
        if int(np.count_nonzero(tail_mask)) < 8:
            tail_mask = np.zeros(n_pts, dtype=bool)
            tail_mask[-min(max(8, n_pts // 4), n_pts):] = True
            tail_mask &= I_pos > 0.0

    qt = q_sel[tail_mask]
    It = I_pos[tail_mask]
    K_porod: float | None = None
    porod_exp: float | None = None
    sigma_int: float | None = None
    ruland_r2: float | None = None

    if qt.size >= 5 and float(np.ptp(qt)) > 1e-12:
        q4I = (qt ** 4) * It
        K_med = float(np.median(q4I))
        sl_p, _ = np.polyfit(np.log(qt), np.log(It), 1)
        porod_exp = _finite_scalar(-sl_p)

        # Ruland diffuse-interface fit: ln(q^4 * I) = ln(K_sharp) - sigma_int^2 * q^2
        x_r = qt ** 2
        y_r = np.log(np.maximum(q4I, 1e-30))
        sl_r, icp_r = np.polyfit(x_r, y_r, 1)
        yh_r = sl_r * x_r + icp_r
        sse_r = float(np.sum((y_r - yh_r) ** 2))
        sst_r = float(np.sum((y_r - float(np.mean(y_r))) ** 2))
        ruland_r2 = _finite_scalar(1.0 - sse_r / sst_r) if sst_r > 1e-30 else 0.0
        if sl_r < 0.0 and (ruland_r2 or 0.0) >= 0.70 and math.isfinite(math.exp(min(icp_r, 500.0))):
            sigma_int = _finite_scalar(math.sqrt(-sl_r))
            K_ruland = _finite_scalar(math.exp(icp_r))
            # Use Ruland intercept K only when Porod regime has mild diffuse damping; guard wild extrapolations
            K_porod = K_ruland if (K_ruland is not None and 0.2 * K_med <= K_ruland <= 15.0 * K_med) else _finite_scalar(K_med)
        else:
            sigma_int = 0.0 if sl_r >= 0.0 else _finite_scalar(math.sqrt(max(-sl_r, 0.0)))
            K_porod = _finite_scalar(K_med)

    l_P: float | None = None
    sv_proxy: float | None = None
    q1_lP: float | None = None
    qm_lP: float | None = None
    if Q_win is not None and K_porod is not None and K_porod > 0.0:
        l_P = _finite_scalar(4.0 * Q_win / (math.pi * K_porod))
        if l_P is not None and l_P > 0.0:
            sv_proxy = _finite_scalar(4.0 / l_P)
            if q1_val is not None:
                q1_lP = _finite_scalar(q1_val * l_P)
            if q_pk_val is not None:
                qm_lP = _finite_scalar(q_pk_val * l_P)

    # Strictly gated model-free RMS SLD fluctuation (requires both calibrated cm^-1 & background subtraction)
    sigma_rho: float | None = None
    Q_A_inv3: float | None = None
    if absolute_intensity is True and background_subtracted is True and Q_win is not None:
        try:
            q_canon = normalize_q_unit(curve.q_unit)
            scale_q_to_A_inv = 0.1 if q_canon == "nm^-1" else 1.0
            Q_A_inv3 = Q_win * (scale_q_to_A_inv ** 3)
            # Q in cm^-1 A^-3 -> 1e-8 * Q in A^-4
            sigma_rho = _finite_scalar(math.sqrt(1.0e-8 * Q_A_inv3 / (2.0 * (math.pi ** 2))))
        except ValueError:
            sigma_rho = None

    assumptions = ["two_phase_sharp_or_diffuse_interface_model"]
    if background_subtracted is not True:
        assumptions.append("background_subtracted_not_verified")
    if absolute_intensity is not True:
        assumptions.append("absolute_intensity_required_for_sigma_rho")
    checks = [
        validity_check("positive_invariant", Q_win is not None and Q_win > 0.0, severity="error", message="Q_win must be positive.", value=Q_win),
        validity_check("porod_constant_positive", K_porod is not None and K_porod > 0.0, severity="warning", message="Positive high-q Porod K could not be determined.", value=K_porod),
        validity_check("background_subtracted", background_subtracted is True, severity="warning", message="Chord length l_P and sigma_rho assume high-q flat background is removed."),
        validity_check("absolute_intensity", absolute_intensity is True, severity="warning", message="Model-free sigma_rho requires absolute intensity calibration in cm^-1."),
    ]
    label, score = reliability_from_checks(checks, assumptions=assumptions)

    results = merge_standard_metadata(
        {
            "Q_win": Q_win,
            "Q_win_cm_inv_A_inv3": _finite_scalar(Q_A_inv3),
            "q1_moment": q1_val,
            "q_peak": q_pk_val,
            "K_porod": K_porod,
            "porod_exponent": porod_exp,
            "l_P": l_P,
            "S_V_over_phi_1mphi": sv_proxy,
            "q1_lP": q1_lP,
            "qm_lP": qm_lP,
            "ruland_sigma_int": sigma_int,
            "ruland_r2": ruland_r2,
            "sigma_rho_A_inv2": sigma_rho,
            "length_unit": len_unit,
        },
        result_group=RESULT_GROUP_TWO_PHASE,
        reliability_label=label,
        reliability_score=score,
        assumptions=assumptions,
        validity_checks=checks,
        interpretation_limits=[
            "l_P = 4*Q/(pi*K_P) is contrast- and scale-invariant once background is subtracted.",
            "sigma_rho = sqrt(Q_3D / (2*pi^2)) avoids phi*(1-phi)*(Delta rho)^2 degeneracy without assumed contrast.",
        ],
    )
    return AnalysisResult.create(
        curve=curve,
        analysis_type="spinodal_interface_topology",
        q_range=eff_range,
        parameters={"background_subtracted": bool(background_subtracted), "absolute_intensity": bool(absolute_intensity)},
        results=results,
        warnings=warning_messages_from_checks(checks),
    )


def analyze_spinodal_sequence(
    curves: Sequence[CurveData],
    times: Sequence[float] | None = None,
    *,
    q_range: tuple[float, float] | None = None,
    reference_mode: str = "first",
    subtract_highq_offset: bool = True,
    highq_offset_fraction: float = 0.12,
    absolute_intensity: bool = False,
    run_teubner_strey: bool = True,
) -> dict[str, Any]:
    """Analyze an in-situ spinodal sequence via excess scattering ``Delta I = I(t) - I_ref``.

    Does not mutate input ``CurveData`` objects. Extracts single-observable consistent
    kinetics ``q1(t), q_peak(t), I_peak(t), Q_ex(t), l_P(t), sigma_int(t)``, joint
    exponents ``(a, b, c, b/a)``, LMK/Furukawa dynamical scaling collapse, and early-frame
    Cahn-Hilliard-Cook dispersion linearity test.
    """
    n_curves = len(curves)
    if n_curves < 3:
        return {
            "status": "unavailable",
            "reason": "need_at_least_3_curves",
            "n_curves": n_curves,
            "frames": [],
        }

    try:
        q_units = [normalize_q_unit(c.q_unit) for c in curves]
    except ValueError as exc:
        return {"status": "unavailable", "reason": str(exc), "n_curves": n_curves, "frames": []}
    target_unit = q_units[0]
    q_scales = [1.0 if u == target_unit else (10.0 if target_unit == "nm^-1" else 0.1) for u in q_units]

    t_vals = (
        np.asarray(times, dtype=float)
        if times is not None
        else np.arange(n_curves, dtype=float)
    )
    if t_vals.shape != (n_curves,):
        raise ValueError("times must match curves length")

    # Sort chronologically if times are finite
    if np.all(np.isfinite(t_vals)):
        order = np.argsort(t_vals, kind="stable")
    else:
        order = np.arange(n_curves)

    ordered_curves = [curves[int(i)] for i in order]
    ordered_times = t_vals[order]
    ordered_scales = [q_scales[int(i)] for i in order]

    # Build common overlap grid from positive finite q of all curves
    clean_pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for c, sc in zip(ordered_curves, ordered_scales):
        qa = np.asarray(c.q, dtype=float) * sc
        Ia = np.asarray(c.intensity, dtype=float)
        m = np.isfinite(qa) & np.isfinite(Ia) & (qa > 0.0)
        qs, Is = qa[m], Ia[m]
        so = np.argsort(qs, kind="stable")
        clean_pairs.append((qs[so], Is[so]))

    common_lo = max(float(qp[0][0]) for qp in clean_pairs)
    common_hi = min(float(qp[0][-1]) for qp in clean_pairs)
    if q_range is not None:
        common_lo = max(common_lo, float(q_range[0]))
        common_hi = min(common_hi, float(q_range[1]))
    if not (math.isfinite(common_lo) and math.isfinite(common_hi) and common_lo < common_hi):
        return {"status": "unavailable", "reason": "no_common_q_overlap", "n_curves": n_curves, "frames": []}

    q_ref_grid = clean_pairs[0][0]
    q_grid = q_ref_grid[(q_ref_grid >= common_lo) & (q_ref_grid <= common_hi)]
    if q_grid.size < 16:
        q_grid = np.linspace(common_lo, common_hi, max(64, int(clean_pairs[0][0].size)))

    I_mat = np.vstack([np.interp(q_grid, qv, Iv) for qv, Iv in clean_pairs])

    ref_mode = str(reference_mode or "first").strip().lower()
    if ref_mode == "first":
        I_ref = I_mat[0]
    elif ref_mode == "none":
        I_ref = np.zeros_like(q_grid)
    else:
        raise ValueError("reference_mode must be 'first' or 'none'")

    delta_mat = I_mat - I_ref[None, :]
    n_tail = max(4, int(round(float(highq_offset_fraction) * q_grid.size)))
    offsets = np.zeros(n_curves, dtype=float)
    if subtract_highq_offset:
        offsets = np.median(delta_mat[:, -n_tail:], axis=1)
        delta_mat = delta_mat - offsets[:, None]

    # Per-frame spinodal topology + TS
    frame_rows: list[dict[str, Any]] = []
    start_idx = 1 if (ref_mode == "first" and n_curves > 3) else 0
    for idx in range(n_curves):
        dI_pos = np.maximum(delta_mat[idx], 0.0)
        diff_curve = CurveData.create(
            name=f"{ordered_curves[idx].name}_excess",
            q=q_grid,
            intensity=dI_pos,
            q_unit=target_unit,
            intensity_unit=ordered_curves[idx].intensity_unit,
        )
        topo = spinodal_interface_and_topology(
            diff_curve,
            (float(q_grid[0]), float(q_grid[-1])),
            background_subtracted=True,
            absolute_intensity=absolute_intensity,
        )
        tr = topo.results
        ts_data: dict[str, Any] = {}
        if run_teubner_strey and float(np.max(dI_pos)) > 1e-12:
            ts_res = fit_teubner_strey_1d(
                diff_curve,
                (float(q_grid[0]), float(q_grid[-1])),
                fit_background=True,
                background_subtracted=True,
            ).results
            ts_data = {
                "d_ts": ts_res.get("d_ts"),
                "xi_ts": ts_res.get("xi_ts"),
                "amphiphilicity_fa": ts_res.get("amphiphilicity_fa"),
                "xi_over_d": ts_res.get("xi_over_d"),
                "lifshitz_regime": ts_res.get("lifshitz_regime"),
                "ts_r2_log": ts_res.get("r2_log"),
            }
        frame_rows.append({
            "frame_order": idx,
            "curve_id": ordered_curves[idx].curve_id,
            "name": ordered_curves[idx].name,
            "time": _finite_scalar(ordered_times[idx]),
            "highq_offset_subtracted": _finite_scalar(offsets[idx]),
            "Q_ex": tr.get("Q_win"),
            "q1": tr.get("q1_moment"),
            "q_peak": tr.get("q_peak"),
            "I_peak": _finite_scalar(np.interp(tr["q_peak"], q_grid, dI_pos)) if tr.get("q_peak") else None,
            "l_P": tr.get("l_P"),
            "q1_lP": tr.get("q1_lP"),
            "qm_lP": tr.get("qm_lP"),
            "ruland_sigma_int": tr.get("ruland_sigma_int"),
            "sigma_rho_A_inv2": tr.get("sigma_rho_A_inv2"),
            **ts_data,
        })

    # Joint scaling exponents on consistent q1 and peak observables over positive-time frames
    t_sub = np.array([r["time"] if r["time"] is not None else np.nan for r in frame_rows[start_idx:]], dtype=float)
    q1_sub = np.array([r["q1"] if r["q1"] is not None else np.nan for r in frame_rows[start_idx:]], dtype=float)
    qpk_sub = np.array([r["q_peak"] if r["q_peak"] is not None else np.nan for r in frame_rows[start_idx:]], dtype=float)
    Ipk_sub = np.array([r["I_peak"] if r["I_peak"] is not None else np.nan for r in frame_rows[start_idx:]], dtype=float)
    Q_sub = np.array([r["Q_ex"] if r["Q_ex"] is not None else np.nan for r in frame_rows[start_idx:]], dtype=float)

    # Prefer interior q_peak if >=4 points exist, else q1 + I(q1)
    q_use_arr = qpk_sub
    I_use_arr = Ipk_sub
    if int(np.count_nonzero(np.isfinite(qpk_sub) & np.isfinite(t_sub) & (t_sub > 0.0))) < 4:
        q_use_arr = q1_sub
        I_use_arr = np.array([
            float(np.interp(q1v, q_grid, np.maximum(delta_mat[start_idx + k], 0.0))) if (np.isfinite(q1v) and q1v > 0) else np.nan
            for k, q1v in enumerate(q1_sub)
        ], dtype=float)

    exp_mask = (t_sub > 0.0) & np.isfinite(t_sub) & (q_use_arr > 0.0) & np.isfinite(q_use_arr) & (I_use_arr > 0.0) & np.isfinite(I_use_arr) & (Q_sub > 0.0) & np.isfinite(Q_sub)
    exponents: dict[str, Any] = {"status": "unavailable", "n_points": int(np.count_nonzero(exp_mask))}
    if int(np.count_nonzero(exp_mask)) >= 3 and int(np.unique(t_sub[exp_mask]).size) >= 3:
        lx = np.log(t_sub[exp_mask])
        a_val = float(-np.polyfit(lx, np.log(q_use_arr[exp_mask]), 1)[0])
        a_q1 = float(-np.polyfit(lx, np.log(q1_sub[exp_mask]), 1)[0]) if np.all(q1_sub[exp_mask] > 0.0) else a_val
        b_val = float(np.polyfit(lx, np.log(I_use_arr[exp_mask]), 1)[0])
        c_val = float(np.polyfit(lx, np.log(Q_sub[exp_mask]), 1)[0])
        ba_val = _finite_scalar(b_val / a_val) if abs(a_val) > 0.015 else None
        exponents = {
            "status": "estimated",
            "n_points": int(np.count_nonzero(exp_mask)),
            "a": _finite_scalar(a_val),
            "a_q1": _finite_scalar(a_q1),
            "b": _finite_scalar(b_val),
            "c": _finite_scalar(c_val),
            "ba_ratio": ba_val,
        }

    # Dynamical scaling collapse across active frames
    x_grid = np.linspace(0.45, 2.2, 50)
    F_rows = []
    for k, row in enumerate(frame_rows[start_idx:]):
        qc = row.get("q1")
        Qv = row.get("Q_ex")
        if qc is None or Qv is None or qc <= 0 or Qv <= 0:
            continue
        x_v = q_grid / qc
        F_v = (qc ** 3) * np.maximum(delta_mat[start_idx + k], 0.0) / Qv
        F_rows.append(np.interp(x_grid, x_v, F_v, left=np.nan, right=np.nan))
    collapse_cv_late: float | None = None
    if len(F_rows) >= 2:
        late_n = max(2, len(F_rows) // 2)
        F_late = np.asarray(F_rows[-late_n:], dtype=float)
        ok = (np.sum(np.isfinite(F_late), axis=0) >= 2) & (x_grid >= 0.5) & (x_grid <= 2.0)
        if np.any(ok):
            mu = np.nanmean(F_late[:, ok], axis=0)
            sd = np.nanstd(F_late[:, ok], axis=0)
            pos = mu > 1e-12
            if np.any(pos):
                collapse_cv_late = _finite_scalar(float(np.mean(sd[pos] / mu[pos])))

    return {
        "status": "estimated",
        "n_curves": n_curves,
        "q_unit": target_unit,
        "length_unit": _length_unit(target_unit),
        "reference_mode": ref_mode,
        "frames": frame_rows,
        "joint_exponents": exponents,
        "collapse_cv_late": collapse_cv_late,
    }


__all__ = [
    "analyze_spinodal_sequence",
    "classify_lifshitz_regime",
    "fit_teubner_strey_1d",
    "spinodal_interface_and_topology",
]
