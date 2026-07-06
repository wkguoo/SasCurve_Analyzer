from __future__ import annotations

from typing import Any


RESULT_GROUP_MODEL_FREE = "model_free"
RESULT_GROUP_PEAK = "peak"
RESULT_GROUP_POROD = "porod"
RESULT_GROUP_INVARIANT = "invariant"
RESULT_GROUP_PR = "pr"
RESULT_GROUP_SHAPE_FIT = "shape_fit"
RESULT_GROUP_FRACTAL = "fractal"
RESULT_GROUP_LAMELLAR = "lamellar"
RESULT_GROUP_TWO_PHASE = "two_phase"
RESULT_GROUP_QUALITY = "quality"

RELIABILITY_HIGH = "high"
RELIABILITY_MEDIUM = "medium"
RELIABILITY_LOW = "low"
RELIABILITY_ASSUMPTION_DEPENDENT = "assumption_dependent"
RELIABILITY_INVALID = "invalid"

STANDARD_RESULT_FIELDS = {
    "result_group",
    "reliability_label",
    "reliability_score",
    "assumptions",
    "validity_checks",
    "interpretation_limits",
    "export_tables",
}

EXPORT_TABLE_FIT_CURVES = "fit_curves"
EXPORT_TABLE_PEAKS = "peaks"
EXPORT_TABLE_GUINIER_CANDIDATES = "guinier_candidates"
EXPORT_TABLE_POWER_LAW_CANDIDATES = "power_law_candidates"
EXPORT_TABLE_PR_DISTRIBUTION = "pr_distribution"
EXPORT_TABLE_CORRELATION_FUNCTION = "correlation_function"
EXPORT_TABLE_RESIDUALS = "residuals"


def merge_standard_metadata(
    results: dict[str, Any],
    *,
    result_group: str,
    reliability_label: str,
    reliability_score: float,
    assumptions: list[str] | None = None,
    validity_checks: list[dict[str, Any]] | None = None,
    interpretation_limits: list[str] | None = None,
    export_tables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(results)
    enriched.update(
        {
            "result_group": result_group,
            "reliability_label": reliability_label,
            "reliability_score": float(max(0.0, min(1.0, reliability_score))),
            "assumptions": list(assumptions or []),
            "validity_checks": list(validity_checks or []),
            "interpretation_limits": list(interpretation_limits or []),
            "export_tables": dict(export_tables or {}),
        }
    )
    return enriched


def scalar_result_items(results: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in results.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }

