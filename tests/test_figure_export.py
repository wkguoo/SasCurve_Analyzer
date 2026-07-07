from __future__ import annotations

from matplotlib.figure import Figure

from app.core.figure_export import FIGURE_EXPORT_PRESETS, export_figure_with_preset, safe_figure_filename


def test_figure_export_presets_have_required_fields() -> None:
    assert set(FIGURE_EXPORT_PRESETS) == {"screen", "presentation", "draft_publication"}
    for preset in FIGURE_EXPORT_PRESETS.values():
        assert preset.dpi > 0
        assert preset.file_format in {"png", "svg", "pdf"}
        assert preset.font_size > 0
        assert preset.line_width > 0
        assert preset.marker_size > 0


def test_safe_figure_filename_removes_unsafe_characters() -> None:
    filename = safe_figure_filename("sample 1/测试", "loglog", "png", timestamp="20260707_170000")

    assert filename.endswith(".png")
    assert "/" not in filename
    assert " " not in filename
    assert "loglog" in filename


def test_export_figure_with_preset_writes_file(tmp_path) -> None:
    figure = Figure()
    axis = figure.add_subplot(111)
    axis.plot([0.1, 0.2], [10, 5], marker="o", label="curve")
    axis.set_xlabel("q")
    axis.set_ylabel("I(q)")
    axis.legend()

    path = export_figure_with_preset(figure, tmp_path / "figure.png", preset_key="presentation", file_format="png")

    assert path.exists()
    assert path.suffix == ".png"
    assert path.stat().st_size > 0
