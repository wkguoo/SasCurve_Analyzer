from __future__ import annotations

from app.core.method_mapping import ANALYSIS_TO_PLOT, PLOT_TO_ANALYSIS, analysis_for_plot, plot_for_analysis
from app.ui.plotting_tab import PLOT_TYPE_ITEMS


def test_plot_to_analysis_mapping_covers_linked_plot_types() -> None:
    plot_keys = {key for _label, key in PLOT_TYPE_ITEMS}

    assert set(PLOT_TO_ANALYSIS).issuperset(plot_keys)
    assert analysis_for_plot("loglog") == "power_law"
    assert analysis_for_plot("guinier") == "guinier"
    assert analysis_for_plot("linear") is None


def test_analysis_to_plot_mapping_uses_valid_plot_keys() -> None:
    plot_keys = {key for _label, key in PLOT_TYPE_ITEMS}

    assert set(ANALYSIS_TO_PLOT.values()).issubset(plot_keys)
    assert plot_for_analysis("guinier") == "guinier"
    assert plot_for_analysis("power_law") == "loglog"


def test_analysis_mapping_covers_standard_model_free_choices() -> None:
    expected_analysis_keys = {
        "guinier",
        "power_law",
        "local_slope",
        "peak_detection",
        "invariant",
        "information_budget",
        "kratky_metrics",
        "porod_metrics",
    }

    assert set(ANALYSIS_TO_PLOT) == expected_analysis_keys
