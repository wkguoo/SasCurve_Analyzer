from __future__ import annotations

from app.core.analysis_preflight import check_analysis_preflight, format_analysis_preflight
from app.core.data_model import CurveData


def test_analysis_preflight_passes_normal_guinier_range() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03, 0.04], intensity=[100, 90, 80, 70])

    preflight = check_analysis_preflight(curve, "guinier", (0.01, 0.04))

    assert preflight.severity == "ok"
    assert preflight.can_run
    assert preflight.log_usable_points == 4
    formatted = format_analysis_preflight(preflight)
    assert "预检通过" in formatted
    assert "next_actions" not in formatted
    assert "建议操作" not in formatted


def test_analysis_preflight_rejects_reversed_range() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02], intensity=[100, 90])

    preflight = check_analysis_preflight(curve, "guinier", (0.02, 0.01))

    assert preflight.severity == "error"
    assert not preflight.can_run
    assert any("q_min" in message for message in preflight.messages)


def test_analysis_preflight_rejects_negative_raw_q_range() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02], intensity=[100, 90])

    preflight = check_analysis_preflight(curve, "power_law", (-1.0, 0.02))

    assert preflight.severity == "error"
    assert any("raw q" in message for message in preflight.messages)


def test_analysis_preflight_rejects_insufficient_log_usable_points() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03], intensity=[100, 0, -1])

    preflight = check_analysis_preflight(curve, "power_law", (0.01, 0.03))

    assert preflight.severity == "error"
    assert preflight.log_usable_points == 1
    assert any("log 可用点" in message for message in preflight.messages)


def test_analysis_preflight_warns_for_peak_detection_with_few_points() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03], intensity=[1, 10, 1])

    preflight = check_analysis_preflight(curve, "peak_detection", (0.01, 0.03))

    assert preflight.severity == "warning"
    assert preflight.can_run
    assert any("峰识别" in message for message in preflight.messages)


def test_analysis_preflight_reports_no_curve() -> None:
    preflight = check_analysis_preflight(None, "guinier", (0.01, 0.02))

    assert preflight.severity == "error"
    assert not preflight.can_run
    assert preflight.total_points == 0
