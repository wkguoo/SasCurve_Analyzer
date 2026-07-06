from __future__ import annotations

from typing import Any

from app.core.analysis_schema import (
    RELIABILITY_ASSUMPTION_DEPENDENT,
    RELIABILITY_HIGH,
    RELIABILITY_INVALID,
    RELIABILITY_LOW,
    RELIABILITY_MEDIUM,
)


def validity_check(
    name: str,
    passed: bool,
    *,
    severity: str = "warning",
    message: str = "",
    value: Any = None,
    threshold: Any = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity,
        "message": message,
        "value": value,
        "threshold": threshold,
    }


def reliability_from_checks(
    checks: list[dict[str, Any]],
    *,
    base_score: float = 1.0,
    assumptions: list[str] | None = None,
) -> tuple[str, float]:
    score = float(base_score)
    invalid = False
    for check in checks:
        if check.get("passed", False):
            continue
        severity = check.get("severity", "warning")
        if severity == "error":
            invalid = True
            score -= 0.55
        elif severity == "warning":
            score -= 0.18
        else:
            score -= 0.08
    score = max(0.0, min(1.0, score))
    if invalid or score < 0.2:
        return RELIABILITY_INVALID, score
    if assumptions:
        if score >= 0.65:
            return RELIABILITY_ASSUMPTION_DEPENDENT, score
        return RELIABILITY_LOW, score
    if score >= 0.8:
        return RELIABILITY_HIGH, score
    if score >= 0.55:
        return RELIABILITY_MEDIUM, score
    return RELIABILITY_LOW, score


def warning_messages_from_checks(checks: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for check in checks:
        if check.get("passed", False):
            continue
        message = check.get("message") or check.get("name")
        messages.append(f"{check.get('severity', 'warning')}: {message}")
    return messages

