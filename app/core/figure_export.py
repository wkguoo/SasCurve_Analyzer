from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from matplotlib.figure import Figure


@dataclass(frozen=True)
class FigureExportPreset:
    label: str
    dpi: int
    file_format: str
    font_size: int
    line_width: float
    marker_size: float


FIGURE_EXPORT_PRESETS: dict[str, FigureExportPreset] = {
    "screen": FigureExportPreset("屏幕预览", dpi=150, file_format="png", font_size=10, line_width=1.2, marker_size=3),
    "presentation": FigureExportPreset("组会汇报", dpi=300, file_format="png", font_size=12, line_width=1.5, marker_size=4),
    "draft_publication": FigureExportPreset("论文初稿", dpi=600, file_format="svg", font_size=10, line_width=1.2, marker_size=3),
}

SUPPORTED_FIGURE_FORMATS = ("png", "svg", "pdf")


def safe_figure_filename(curve_name: str, plot_type: str, file_format: str, timestamp: str | None = None) -> str:
    stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{curve_name}_{plot_type}_{stamp}"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", base).strip("._")
    return f"{safe or 'figure'}.{file_format.lower()}"


def apply_figure_export_preset(figure: Figure, preset_key: str) -> FigureExportPreset:
    preset = FIGURE_EXPORT_PRESETS[preset_key]
    for axis in figure.axes:
        axis.xaxis.label.set_size(preset.font_size)
        axis.yaxis.label.set_size(preset.font_size)
        axis.title.set_size(preset.font_size + 1)
        axis.tick_params(labelsize=max(8, preset.font_size - 1))
        for line in axis.lines:
            line.set_linewidth(preset.line_width)
            line.set_markersize(preset.marker_size)
        legend = axis.get_legend()
        if legend is not None:
            for text in legend.get_texts():
                text.set_fontsize(max(8, preset.font_size - 1))
    figure.tight_layout()
    return preset


def export_figure_with_preset(
    figure: Figure,
    path: str | Path,
    *,
    preset_key: str,
    file_format: str | None = None,
) -> Path:
    if preset_key not in FIGURE_EXPORT_PRESETS:
        raise ValueError(f"Unknown figure export preset: {preset_key}")
    preset = apply_figure_export_preset(figure, preset_key)
    chosen_format = (file_format or preset.file_format).lower()
    if chosen_format not in SUPPORTED_FIGURE_FORMATS:
        raise ValueError(f"Unsupported figure format: {chosen_format}")
    target = Path(path)
    if target.suffix.lower().lstrip(".") != chosen_format:
        target = target.with_suffix(f".{chosen_format}")
    target.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(target, dpi=preset.dpi, format=chosen_format)
    return target
