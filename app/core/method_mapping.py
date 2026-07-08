from __future__ import annotations

PLOT_TO_ANALYSIS: dict[str, str | None] = {
    "linear": "linear",
    "semilog": "semilog",
    "loglog": "loglog",
    "guinier": "guinier",
    "kratky": "kratky",
    "porod": "porod",
    "invariant": "invariant",
    "local_slope": "local_slope",
}

ANALYSIS_TO_PLOT: dict[str, str] = {
    "linear": "linear",
    "semilog": "semilog",
    "guinier": "guinier",
    "loglog": "loglog",
    "power_law": "loglog",
    "local_slope": "local_slope",
    "invariant": "invariant",
    "information_budget": "invariant",
    "kratky": "kratky",
    "kratky_metrics": "kratky",
    "porod": "porod",
    "porod_metrics": "porod",
}


def analysis_for_plot(plot_type: str) -> str | None:
    return PLOT_TO_ANALYSIS.get(plot_type)


def plot_for_analysis(analysis_type: str) -> str | None:
    return ANALYSIS_TO_PLOT.get(analysis_type)
