from __future__ import annotations

PLOT_TO_ANALYSIS: dict[str, str | None] = {
    "linear": None,
    "semilog": None,
    "loglog": "power_law",
    "guinier": "guinier",
    "kratky": "kratky_metrics",
    "porod": "porod_metrics",
    "invariant": "invariant",
    "invariant_contribution": "information_budget",
    "local_slope": "local_slope",
    "peak_spacing": "peak_detection",
}

ANALYSIS_TO_PLOT: dict[str, str] = {
    "guinier": "guinier",
    "power_law": "loglog",
    "local_slope": "local_slope",
    "peak_detection": "peak_spacing",
    "invariant": "invariant",
    "information_budget": "invariant_contribution",
    "kratky_metrics": "kratky",
    "porod_metrics": "porod",
}


def analysis_for_plot(plot_type: str) -> str | None:
    return PLOT_TO_ANALYSIS.get(plot_type)


def plot_for_analysis(analysis_type: str) -> str | None:
    return ANALYSIS_TO_PLOT.get(analysis_type)
