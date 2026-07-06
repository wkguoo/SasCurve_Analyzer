from __future__ import annotations

import json

from app.core.data_model import CurveData
from app.core.project import ProjectState, load_project, save_project


def test_project_curve_data_is_saved_as_json(tmp_path) -> None:
    project = ProjectState()
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    project.add_curve(curve)

    save_project(project, tmp_path)

    project_payload = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    data_file = project_payload["curves"][0]["data_file"]
    assert data_file.endswith(".json")
    curve_payload = json.loads((tmp_path / data_file).read_text(encoding="utf-8"))
    assert curve_payload["q"] == [0.1, 0.2]


def test_project_loads_legacy_csv_json_curve_data(tmp_path) -> None:
    project = ProjectState()
    curve = CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20])
    project.add_curve(curve)
    save_project(project, tmp_path)

    project_path = tmp_path / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    old_data_file = payload["curves"][0]["data_file"]
    legacy_data_file = old_data_file.replace(".json", ".csv")
    (tmp_path / legacy_data_file).write_text((tmp_path / old_data_file).read_text(encoding="utf-8"), encoding="utf-8")
    payload["curves"][0]["data_file"] = legacy_data_file
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_project(tmp_path)

    assert len(loaded.curves) == 1
    assert loaded.curves[0].name == "curve"
