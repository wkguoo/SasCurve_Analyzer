from __future__ import annotations

from app.core.analysis_templates import AnalysisTemplate, apply_template, load_template, save_template
from app.core.data_model import CurveData


def test_template_save_and_load(tmp_path) -> None:
    template = AnalysisTemplate.create("routine", q_range=(0.01, 0.1))
    path = save_template(template, tmp_path / "template.json")
    loaded = load_template(path)
    assert loaded.name == "routine"
    assert loaded.q_range == (0.01, 0.1)


def test_template_apply_to_curve() -> None:
    curve = CurveData.create(name="curve", q=[0.01, 0.02, 0.03, 0.04, 0.05], intensity=[100, 90, 80, 70, 60])
    template = AnalysisTemplate.create("routine", q_range=(0.01, 0.05), power_law_settings={"enabled": False})
    run, analyses, history = apply_template(template, [curve])
    assert run.status == "completed"
    assert analyses
    assert history

