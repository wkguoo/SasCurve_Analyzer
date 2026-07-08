from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from app.core.analysis_schema import (
    EXPORT_TABLE_AUTO_REGION_CANDIDATES,
    RESULT_GROUP_AUTO_REGION,
    RELIABILITY_INVALID,
    RELIABILITY_MEDIUM,
    merge_standard_metadata,
)
from app.core.data_model import AnalysisResult, CurveData
from app.core.feature_extraction import detect_peaks
from app.core.model_free import guinier_analysis, invariant_measured, power_law_analysis
from app.core.porod_analysis import porod_deep_analysis
from app.core.region_scanners import (
    curve_quality_metrics,
    deep_peak_detection,
    detect_high_q_noise,
    detect_low_q_upturn,
    scan_guinier_candidates,
    scan_porod_candidates,
    scan_power_law_candidates,
)
from app.core.reliability import reliability_from_checks, validity_check, warning_messages_from_checks


REGION_TYPE_LABELS = {
    "guinier_candidate": "候选 Guinier 区",
    "power_law_candidate": "候选 Power-law 区",
    "porod_candidate": "Porod-like 候选区",
    "peak_candidate": "峰候选区",
    "low_q_upturn": "低 q 上翘信号",
    "high_q_noise": "高 q 噪声/背景风险区",
    "invariant_range": "有限 q 不变量计算区",
    "shoulder_candidate": "肩峰候选",
    "crossover_candidate": "Crossover 候选",
}

DETECTION_METHODS = {
    "sliding_window_guinier": "滑动窗口 Guinier 扫描",
    "sliding_window_power_law": "滑动窗口 Power-law 扫描",
    "sliding_window_porod": "滑动窗口 Porod 扫描",
    "peak_detection_scipy": "Scipy 峰检测",
    "low_q_upturn_combined": "组合判据低 q 上翘",
    "high_q_noise_multi_metric": "多指标高 q 噪声评估",
    "invariant_integration": "Trapezoid 不变量积分",
}


@dataclass
class AutoRegionOptions:
    min_points_guinier: int = 8
    min_points_power_law: int = 8
    min_points_porod: int = 8
    max_candidates_per_type: int = 8
    max_scanned_windows: int = 200
    local_slope_window: int = 5
    local_slope_std_threshold: float = 0.15
    qrg_limit: float = 1.3
    porod_alpha_target: float = 4.0
    porod_alpha_tolerance: float = 0.4
    porod_plateau_cv_recommended: float = 0.20
    porod_plateau_cv_usable: float = 0.35
    porod_plateau_cv_caution: float = 0.50
    high_confidence_threshold: float = 0.85
    usable_confidence_threshold: float = 0.70
    caution_confidence_threshold: float = 0.50


@dataclass(frozen=True)
class AutoRegionCandidate:
    region_id: str
    curve_id: str
    curve_name: str
    region_type: str
    q_start: float
    q_end: float
    d_start: float | None
    d_end: float | None
    transformed_x_start: float | None
    transformed_x_end: float | None
    n_points: int
    detection_method: str
    score: float
    confidence_label: str
    fit_ready: bool
    recommended_analysis: str | None
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    source_detection_analysis_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AutoRegionCandidate":
        return cls(
            region_id=str(payload["region_id"]),
            curve_id=str(payload["curve_id"]),
            curve_name=str(payload.get("curve_name", "")),
            region_type=str(payload["region_type"]),
            q_start=float(payload["q_start"]),
            q_end=float(payload["q_end"]),
            d_start=_optional_float(payload.get("d_start")),
            d_end=_optional_float(payload.get("d_end")),
            transformed_x_start=_optional_float(payload.get("transformed_x_start")),
            transformed_x_end=_optional_float(payload.get("transformed_x_end")),
            n_points=int(payload.get("n_points", 0)),
            detection_method=str(payload["detection_method"]),
            score=float(payload.get("score", 0.0)),
            confidence_label=str(payload.get("confidence_label", "not_recommended")),
            fit_ready=bool(payload.get("fit_ready", False)),
            recommended_analysis=payload.get("recommended_analysis"),
            metrics=dict(payload.get("metrics") or {}),
            warnings=list(payload.get("warnings") or []),
            source_detection_analysis_id=payload.get("source_detection_analysis_id"),
        )


@dataclass(frozen=True)
class AutoRegionDetectionResult:
    curve_id: str
    curve_name: str
    q_range: tuple[float, float]
    candidates: list[AutoRegionCandidate]
    quality: dict[str, Any]
    detection_warnings: list[str]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def characteristic_d_from_q(q: float) -> float | None:
    q_value = _optional_float(q)
    if q_value is None or q_value <= 0:
        return None
    return float(2.0 * math.pi / q_value)


def confidence_label(score: float, options: AutoRegionOptions | None = None) -> str:
    opts = options or AutoRegionOptions()
    value = float(score)
    if value >= opts.high_confidence_threshold:
        return "recommended"
    if value >= opts.usable_confidence_threshold:
        return "usable"
    if value >= opts.caution_confidence_threshold:
        return "caution"
    return "not_recommended"


def log_q_position_fraction(q_center: float, q_min: float, q_max: float) -> float:
    if q_center <= 0 or q_min <= 0 or q_max <= 0 or q_min == q_max:
        raise ValueError("q_center, q_min, and q_max must be positive and span a non-zero range.")
    lower = min(q_min, q_max)
    upper = max(q_min, q_max)
    return float((math.log(q_center) - math.log(lower)) / (math.log(upper) - math.log(lower)))


def region_type_label(region_type: str) -> str:
    return REGION_TYPE_LABELS.get(region_type, region_type)


def _q_range_for_curve(curve: CurveData, q_range: tuple[float, float] | None) -> tuple[float, float]:
    finite_q = curve.q[np.isfinite(curve.q)]
    if q_range is not None:
        return (float(min(q_range)), float(max(q_range)))
    if finite_q.size == 0:
        return (float("nan"), float("nan"))
    return (float(np.nanmin(finite_q)), float(np.nanmax(finite_q)))


def _detection_warnings(curve: CurveData, q_range: tuple[float, float]) -> list[str]:
    warnings: list[str] = []
    q = curve.q
    intensity = curve.intensity
    finite_q = q[np.isfinite(q)]
    selected = np.isfinite(q) & np.isfinite(intensity) & (q >= q_range[0]) & (q <= q_range[1])
    selected_q = q[selected]
    selected_i = intensity[selected]
    if q.size == 0 or intensity.size == 0:
        warnings.append("Curve has no q/I data for automatic q-region detection.")
    if np.any(~np.isfinite(q)):
        warnings.append(f"Excluded {int(np.sum(~np.isfinite(q)))} non-finite q values from temporary auto-region arrays.")
    if np.any(~np.isfinite(intensity)):
        warnings.append(f"Excluded {int(np.sum(~np.isfinite(intensity)))} non-finite I(q) values from temporary auto-region arrays.")
    if selected_q.size >= 2 and not np.all(np.diff(selected_q) > 0):
        warnings.append("q values are non-monotonic; automatic q-region detection used a temporary sorted copy.")
    if finite_q.size and np.unique(finite_q).size != finite_q.size:
        warnings.append("duplicate q values were found; scanner arrays used temporary de-duplicated q values.")
    nonpositive_q = int(np.sum(selected_q <= 0))
    if nonpositive_q:
        warnings.append(f"Excluded {nonpositive_q} points with q <= 0 from log-based auto-region detection.")
    nonpositive_i = int(np.sum(selected_i <= 0))
    if nonpositive_i:
        warnings.append(f"Excluded {nonpositive_i} points with I(q) <= 0 from log-based auto-region detection.")
    positive_log = selected & (q > 0) & (intensity > 0)
    if int(np.sum(positive_log)) < 8:
        warnings.append("Fewer than 8 q>0 and I(q)>0 points are available for log-based auto-region detection.")
    if finite_q.size >= 2:
        q_min = float(np.nanmin(finite_q[finite_q > 0])) if np.any(finite_q > 0) else None
        q_max = float(np.nanmax(finite_q[finite_q > 0])) if np.any(finite_q > 0) else None
        if q_min and q_max and q_min > 0 and q_max / q_min < 1.5:
            warnings.append("q range is narrow; automatic region confidence may be limited.")
    if curve.error is None:
        warnings.append("No error column found; automatic candidate scoring uses unweighted fits where applicable.")
    return warnings


def _candidate(
    *,
    curve: CurveData,
    region_type: str,
    index: int,
    q_start: float,
    q_end: float,
    n_points: int,
    detection_method: str,
    score: float,
    fit_ready: bool,
    recommended_analysis: str | None,
    metrics: dict[str, Any],
    warnings: list[str] | None = None,
    options: AutoRegionOptions,
    transformed_x_start: float | None = None,
    transformed_x_end: float | None = None,
) -> AutoRegionCandidate:
    if detection_method not in DETECTION_METHODS:
        raise ValueError(f"Unknown detection_method: {detection_method}")
    q_lower = float(min(q_start, q_end))
    q_upper = float(max(q_start, q_end))
    score_value = float(max(0.0, min(1.0, score)))
    return AutoRegionCandidate(
        region_id=f"{curve.curve_id}:{region_type}:{index}",
        curve_id=curve.curve_id,
        curve_name=curve.name,
        region_type=region_type,
        q_start=q_lower,
        q_end=q_upper,
        d_start=characteristic_d_from_q(q_lower),
        d_end=characteristic_d_from_q(q_upper),
        transformed_x_start=transformed_x_start,
        transformed_x_end=transformed_x_end,
        n_points=int(n_points),
        detection_method=detection_method,
        score=score_value,
        confidence_label=confidence_label(score_value, options),
        fit_ready=bool(fit_ready),
        recommended_analysis=recommended_analysis,
        metrics=dict(metrics),
        warnings=list(warnings or []),
    )


def _best_dict(candidates: list[AutoRegionCandidate], region_type: str) -> dict[str, Any] | None:
    matching = [candidate for candidate in candidates if candidate.region_type == region_type]
    return matching[0].to_dict() if matching else None


def _near_or_overlaps(candidate_q: tuple[float, float], risk_q: tuple[float, float]) -> bool:
    candidate_start, candidate_end = sorted(candidate_q)
    risk_start, risk_end = sorted(risk_q)
    width = max(candidate_end - candidate_start, risk_end - risk_start, 0.0)
    margin = 0.50 * width
    return candidate_start <= risk_end + margin and candidate_end >= risk_start - margin


def _guinier_row_from_interval(curve: CurveData, q_range: tuple[float, float], *, min_points: int) -> dict[str, Any]:
    result = guinier_analysis(curve, q_range, min_points=min_points)
    residuals = result.results.get("residuals", [])
    residual_arr = np.asarray(residuals, dtype=float) if residuals else np.asarray([], dtype=float)
    residual_rms = float(np.sqrt(np.mean(residual_arr[np.isfinite(residual_arr)] ** 2))) if np.any(np.isfinite(residual_arr)) else None
    return {
        "q_min": float(q_range[0]),
        "q_max": float(q_range[1]),
        "fit_points": result.results.get("fit_points"),
        "Rg": result.results.get("Rg"),
        "I0": result.results.get("I0"),
        "lnI0": result.results.get("lnI0"),
        "slope": result.results.get("slope"),
        "intercept": result.results.get("intercept"),
        "qRg_min": result.results.get("qRg_min"),
        "qRg_max": result.results.get("qRg_max"),
        "R2": result.results.get("R2"),
        "reduced_chi_square": result.results.get("reduced_chi_square"),
        "residual_rms": residual_rms,
        "score": 0.0,
        "warnings": result.warnings,
        "scanned_windows": 1,
        "max_scanned_windows": 1,
        "max_scanned_windows_reached": False,
    }


def detect_auto_regions(
    curve: CurveData,
    q_range: tuple[float, float] | None = None,
    options: AutoRegionOptions | None = None,
) -> AnalysisResult:
    opts = options or AutoRegionOptions()
    final_q_range = _q_range_for_curve(curve, q_range)
    detection_warnings = _detection_warnings(curve, final_q_range)
    quality = curve_quality_metrics(curve, final_q_range)
    candidates: list[AutoRegionCandidate] = []
    upturn = detect_low_q_upturn(curve, final_q_range, min_points=opts.min_points_guinier)

    guinier_rows = scan_guinier_candidates(
        curve,
        final_q_range,
        min_points=opts.min_points_guinier,
        max_candidates=opts.max_candidates_per_type,
        max_scanned_windows=opts.max_scanned_windows,
    )
    if upturn is not None and not any(
        float(row["q_min"]) <= float(upturn["q_max"]) and float(row["q_max"]) >= float(upturn["q_min"])
        for row in guinier_rows
    ):
        guinier_rows.append(
            _guinier_row_from_interval(
                curve,
                (float(upturn["q_min"]), float(upturn["q_max"])),
                min_points=opts.min_points_guinier,
            )
        )

    for index, row in enumerate(guinier_rows):
        q_start = float(row["q_min"])
        q_end = float(row["q_max"])
        score = float(row.get("score") or 0.0)
        warnings = list(row.get("warnings") or [])
        if row.get("qRg_max") is not None and row["qRg_max"] > opts.qrg_limit:
            warnings.append("qRg_max is above 1.3; treat this as a Guinier candidate only.")
        if upturn is not None and _near_or_overlaps((q_start, q_end), (float(upturn["q_min"]), float(upturn["q_max"]))):
            score = min(score * 0.75, 0.84)
            warnings.append("Low-q upturn overlaps or is near this Guinier candidate; treat Rg as tentative.")
        candidates.append(
            _candidate(
                curve=curve,
                region_type="guinier_candidate",
                index=index + 1,
                q_start=q_start,
                q_end=q_end,
                n_points=int(row.get("fit_points") or 0),
                detection_method="sliding_window_guinier",
                score=score,
                fit_ready=bool(score >= opts.caution_confidence_threshold and row.get("Rg") is not None),
                recommended_analysis="guinier_analysis",
                metrics=row,
                warnings=warnings,
                options=opts,
                transformed_x_start=q_start**2,
                transformed_x_end=q_end**2,
            )
        )

    for index, row in enumerate(
        scan_power_law_candidates(
            curve,
            final_q_range,
            min_points=opts.min_points_power_law,
            max_candidates=opts.max_candidates_per_type,
            max_scanned_windows=opts.max_scanned_windows,
        )
    ):
        q_start = float(row["q_min"])
        q_end = float(row["q_max"])
        score = float(row.get("score") or 0.0)
        candidates.append(
            _candidate(
                curve=curve,
                region_type="power_law_candidate",
                index=index + 1,
                q_start=q_start,
                q_end=q_end,
                n_points=int(row.get("fit_points") or 0),
                detection_method="sliding_window_power_law",
                score=score,
                fit_ready=bool(score >= opts.caution_confidence_threshold and row.get("alpha") is not None),
                recommended_analysis="power_law_analysis",
                metrics=row,
                warnings=list(row.get("warnings") or []),
                options=opts,
                transformed_x_start=math.log(q_start) if q_start > 0 else None,
                transformed_x_end=math.log(q_end) if q_end > 0 else None,
            )
        )

    for index, row in enumerate(
        scan_porod_candidates(
            curve,
            final_q_range,
            min_points=opts.min_points_porod,
            max_candidates=opts.max_candidates_per_type,
            max_scanned_windows=opts.max_scanned_windows,
            alpha_target=opts.porod_alpha_target,
            alpha_tolerance=opts.porod_alpha_tolerance,
            global_q_range=final_q_range,
        )
    ):
        q_start = float(row["q_min"])
        q_end = float(row["q_max"])
        score = float(row.get("score") or 0.0)
        candidates.append(
            _candidate(
                curve=curve,
                region_type="porod_candidate",
                index=index + 1,
                q_start=q_start,
                q_end=q_end,
                n_points=int(row.get("fit_points") or 0),
                detection_method="sliding_window_porod",
                score=score,
                fit_ready=bool(score >= opts.caution_confidence_threshold),
                recommended_analysis="porod_deep_analysis",
                metrics=row,
                warnings=list(row.get("warnings") or []),
                options=opts,
                transformed_x_start=math.log(q_start) if q_start > 0 else None,
                transformed_x_end=math.log(q_end) if q_end > 0 else None,
            )
        )

    peaks, peak_warnings = deep_peak_detection(curve, final_q_range)
    detection_warnings.extend(peak_warnings)
    for index, peak in enumerate(peaks[: opts.max_candidates_per_type]):
        q_star = _optional_float(peak.get("peak_q"))
        q_start = _optional_float(peak.get("q_start"))
        q_end = _optional_float(peak.get("q_end"))
        if q_start is None or q_end is None or q_start == q_end:
            if q_star is None:
                continue
            q_start, q_end = q_star, q_star
        metrics = dict(peak)
        metrics["q_star"] = q_star
        metrics["d_star"] = characteristic_d_from_q(q_star) if q_star is not None else None
        score = 0.65 if peak.get("q_boundary_source") == "fwhm" else 0.50
        point_mask = np.isfinite(curve.q) & (curve.q >= min(q_start, q_end)) & (curve.q <= max(q_start, q_end))
        candidates.append(
            _candidate(
                curve=curve,
                region_type="peak_candidate",
                index=index + 1,
                q_start=q_start,
                q_end=q_end,
                n_points=max(1, int(np.sum(point_mask))),
                detection_method="peak_detection_scipy",
                score=score,
                fit_ready=bool(q_start < q_end),
                recommended_analysis="peak",
                metrics=metrics,
                warnings=list(metrics.get("warnings") or []),
                options=opts,
            )
        )

    if upturn is not None:
        candidates.append(
            _candidate(
                curve=curve,
                region_type="low_q_upturn",
                index=1,
                q_start=float(upturn["q_min"]),
                q_end=float(upturn["q_max"]),
                n_points=int(upturn["n_points"]),
                detection_method="low_q_upturn_combined",
                score=float(upturn["score"]),
                fit_ready=False,
                recommended_analysis=None,
                metrics=upturn,
                warnings=list(upturn.get("warnings") or []),
                options=opts,
            )
        )

    high_noise = detect_high_q_noise(curve, final_q_range, min_points=opts.min_points_porod)
    if high_noise is not None:
        candidates.append(
            _candidate(
                curve=curve,
                region_type="high_q_noise",
                index=1,
                q_start=float(high_noise["q_min"]),
                q_end=float(high_noise["q_max"]),
                n_points=int(high_noise["n_points"]),
                detection_method="high_q_noise_multi_metric",
                score=float(high_noise["score"]),
                fit_ready=False,
                recommended_analysis=None,
                metrics=high_noise,
                warnings=list(high_noise.get("warnings") or []),
                options=opts,
            )
        )

    invariant = invariant_measured(curve, final_q_range)
    if invariant.results.get("integration_points", 0) >= 2:
        candidates.append(
            _candidate(
                curve=curve,
                region_type="invariant_range",
                index=1,
                q_start=final_q_range[0],
                q_end=final_q_range[1],
                n_points=int(invariant.results.get("integration_points") or 0),
                detection_method="invariant_integration",
                score=0.75,
                fit_ready=True,
                recommended_analysis="invariant_measured",
                metrics={
                    "Q_measured": invariant.results.get("Q_measured"),
                    "q_min": final_q_range[0],
                    "q_max": final_q_range[1],
                    "integration_method": "trapezoid",
                    "negative_intensity_points": invariant.results.get("negative_intensity_points"),
                },
                warnings=list(invariant.warnings),
                options=opts,
            )
        )

    candidates.sort(key=lambda candidate: (candidate.fit_ready, candidate.score), reverse=True)
    candidate_dicts = [candidate.to_dict() for candidate in candidates]

    checks = [
        validity_check(
            "enough_positive_log_points",
            quality.get("positive_log_points", 0) >= min(opts.min_points_guinier, opts.min_points_power_law),
            severity="error",
            message="Need enough q>0 and I(q)>0 points for automatic q-region detection.",
            value=quality.get("positive_log_points"),
        ),
        validity_check(
            "has_candidates",
            bool(candidate_dicts),
            severity="warning",
            message="No automatic q-region candidates were detected.",
        ),
        validity_check(
            "q_monotonic",
            bool(quality.get("q_monotonic", False)),
            severity="warning",
            message="q values were not strictly increasing; temporary sorting was used.",
        ),
    ]
    label, reliability_score = reliability_from_checks(checks)
    warnings = warning_messages_from_checks(checks)
    warnings.extend(detection_warnings)
    if not candidate_dicts and label != RELIABILITY_INVALID:
        label = RELIABILITY_MEDIUM

    results = {
        "auto_detection_version": "1.0",
        "candidates": candidate_dicts,
        "candidate_count": len(candidate_dicts),
        "guinier_candidate_count": len([row for row in candidate_dicts if row["region_type"] == "guinier_candidate"]),
        "power_law_candidate_count": len([row for row in candidate_dicts if row["region_type"] == "power_law_candidate"]),
        "porod_candidate_count": len([row for row in candidate_dicts if row["region_type"] == "porod_candidate"]),
        "peak_candidate_count": len([row for row in candidate_dicts if row["region_type"] == "peak_candidate"]),
        "best_guinier": _best_dict(candidates, "guinier_candidate"),
        "best_power_law": _best_dict(candidates, "power_law_candidate"),
        "best_porod": _best_dict(candidates, "porod_candidate"),
        "best_peak": _best_dict(candidates, "peak_candidate"),
        "curve_quality": quality,
        "finite_invariant": invariant.results.get("Q_measured"),
        "detection_warnings": detection_warnings,
    }
    results = merge_standard_metadata(
        results,
        result_group=RESULT_GROUP_AUTO_REGION,
        reliability_label=label,
        reliability_score=reliability_score,
        validity_checks=checks,
        interpretation_limits=[
            "Automatic q-region detection ranks candidate intervals; it does not prove a unique SAS structure.",
            "Peak d=2π/q is a characteristic spacing, not a particle diameter without an explicit morphology model.",
            "Porod-like and power-law labels are descriptive candidates and require material context.",
        ],
        export_tables={EXPORT_TABLE_AUTO_REGION_CANDIDATES: candidate_dicts},
    )
    result = AnalysisResult.create(
        curve=curve,
        analysis_type="auto_region_detection",
        q_range=final_q_range,
        parameters={"options": asdict(opts)},
        results=results,
        warnings=warnings,
    )
    for row in result.results["candidates"]:
        row["source_detection_analysis_id"] = result.analysis_id
    result.results["export_tables"][EXPORT_TABLE_AUTO_REGION_CANDIDATES] = result.results["candidates"]
    for key in ("best_guinier", "best_power_law", "best_porod", "best_peak"):
        if result.results.get(key):
            result.results[key]["source_detection_analysis_id"] = result.analysis_id
    return result


def _source_metadata(
    candidate: AutoRegionCandidate,
    final_q_range: tuple[float, float],
    *,
    user_overrode_range: bool,
) -> dict[str, Any]:
    return {
        "source_auto_region_id": candidate.region_id,
        "source_region_type": candidate.region_type,
        "auto_score": candidate.score,
        "confidence_label": candidate.confidence_label,
        "original_q_range": (candidate.q_start, candidate.q_end),
        "final_q_range": final_q_range,
        "user_overrode_range": user_overrode_range,
    }


def run_analysis_for_region(
    curve: CurveData,
    candidate: AutoRegionCandidate,
    *,
    user_overridden_q_range: tuple[float, float] | None = None,
    force: bool = False,
    contrast: float | None = None,
    volume_fraction: float | None = None,
    absolute_intensity: bool = False,
    prominence: float | None = None,
    min_points: int | None = None,
) -> AnalysisResult:
    user_overrode_range = user_overridden_q_range is not None
    final_q_range = (
        (float(min(user_overridden_q_range)), float(max(user_overridden_q_range)))
        if user_overridden_q_range is not None
        else (candidate.q_start, candidate.q_end)
    )
    source = _source_metadata(candidate, final_q_range, user_overrode_range=user_overrode_range)
    if not candidate.fit_ready and not force:
        warning = (
            f"Auto-region candidate {candidate.region_id} is not fit-ready; no fitting/calculation was run. "
            "Use force=True only after manual review."
        )
        results = merge_standard_metadata(
            dict(source),
            result_group=RESULT_GROUP_AUTO_REGION,
            reliability_label=RELIABILITY_INVALID,
            reliability_score=0.0,
            interpretation_limits=["This result records a skipped automatic-region action, not a scientific fit."],
        )
        return AnalysisResult.create(
            curve=curve,
            analysis_type="auto_region_skipped",
            q_range=final_q_range,
            parameters={"force": force, **source},
            results=results,
            warnings=[warning, *candidate.warnings],
        )

    if candidate.region_type == "guinier_candidate":
        result = guinier_analysis(curve, final_q_range, min_points=min_points or 5)
    elif candidate.region_type == "power_law_candidate":
        result = power_law_analysis(curve, final_q_range, min_points=min_points or 5)
    elif candidate.region_type == "porod_candidate":
        result = porod_deep_analysis(
            curve,
            final_q_range,
            contrast=contrast,
            volume_fraction=volume_fraction,
            absolute_intensity=absolute_intensity,
        )
    elif candidate.region_type == "peak_candidate":
        result = detect_peaks(curve, final_q_range, prominence=prominence)
    elif candidate.region_type == "invariant_range":
        result = invariant_measured(curve, final_q_range)
    else:
        warning = f"Auto-region type {candidate.region_type} is a risk/annotation region and has no default analysis runner."
        results = merge_standard_metadata(
            dict(source),
            result_group=RESULT_GROUP_AUTO_REGION,
            reliability_label=RELIABILITY_INVALID,
            reliability_score=0.0,
            interpretation_limits=["This candidate type is not a default fitting/calculation target."],
        )
        return AnalysisResult.create(
            curve=curve,
            analysis_type="auto_region_skipped",
            q_range=final_q_range,
            parameters={"force": force, **source},
            results=results,
            warnings=[warning, *candidate.warnings],
        )

    result.results.update(source)
    result.parameters.update(
        {
            "auto_region": True,
            "force": force,
            **source,
        }
    )
    return result
