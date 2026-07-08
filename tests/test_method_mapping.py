from __future__ import annotations

from app.core.method_mapping import ANALYSIS_TO_PLOT, PLOT_TO_ANALYSIS, analysis_for_plot, plot_for_analysis
from app.ui.plotting_tab import PLOT_TYPE_ITEMS


EXPECTED_PLOT_KEYS = [
    "linear",
    "semilog",
    "loglog",
    "guinier",
    "kratky",
    "porod",
    "invariant",
    "local_slope",
]


def test_plot_type_items_are_restricted_to_eight_main_views() -> None:
    assert [key for _label, key in PLOT_TYPE_ITEMS] == EXPECTED_PLOT_KEYS
    assert "invariant_contribution" not in {key for _label, key in PLOT_TYPE_ITEMS}
    assert "peak_spacing" not in {key for _label, key in PLOT_TYPE_ITEMS}


def test_plot_to_analysis_mapping_covers_eight_plot_types() -> None:
    plot_keys = {key for _label, key in PLOT_TYPE_ITEMS}

    assert set(PLOT_TO_ANALYSIS) == plot_keys
    assert analysis_for_plot("loglog") == "loglog"
    assert analysis_for_plot("guinier") == "guinier"
    assert analysis_for_plot("linear") == "linear"


def test_analysis_to_plot_mapping_uses_valid_plot_keys_and_keeps_aliases() -> None:
    plot_keys = {key for _label, key in PLOT_TYPE_ITEMS}

    assert set(ANALYSIS_TO_PLOT.values()).issubset(plot_keys)
    assert plot_for_analysis("guinier") == "guinier"
    assert plot_for_analysis("loglog") == "loglog"
    assert plot_for_analysis("power_law") == "loglog"
    assert plot_for_analysis("kratky_metrics") == "kratky"
    assert plot_for_analysis("porod_metrics") == "porod"
