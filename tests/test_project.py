from __future__ import annotations

import json
import os

from app.core.data_model import CurveData
from app.core.project import ProjectState, load_project, save_project

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import app.ui.main_window as main_window_module
from app.ui.main_window import MainWindow


class _FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class _SaveChoiceMessageBox:
    Warning = object()
    AcceptRole = object()
    DestructiveRole = object()
    RejectRole = object()

    def __init__(self, _parent=None) -> None:
        self._clicked = None

    def setIcon(self, _icon) -> None:
        return None

    def setWindowTitle(self, _title: str) -> None:
        return None

    def setText(self, _text: str) -> None:
        return None

    def setInformativeText(self, _text: str) -> None:
        return None

    def addButton(self, text: str, _role):
        if text == "保存":
            self._clicked = text
        return text

    def setDefaultButton(self, _button) -> None:
        return None

    def exec(self) -> int:
        return 0

    def clickedButton(self):
        return self._clicked


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


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


def test_project_revision_tracks_changes_and_load_resets_clean_baseline(tmp_path) -> None:
    project = ProjectState()
    assert project.revision == 0

    project.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
    assert project.revision > 0

    save_project(project, tmp_path)
    loaded = load_project(tmp_path)

    assert len(loaded.curves) == 1
    assert loaded.revision == 0


def test_load_project_rejects_path_traversal_data_file(tmp_path) -> None:
    project = ProjectState()
    project.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
    save_project(project, tmp_path)

    outside = tmp_path.parent / "outside_secret.json"
    outside.write_text(json.dumps({"q": [1.0], "I": [2.0], "error": None}), encoding="utf-8")

    project_path = tmp_path / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["curves"][0]["data_file"] = f"../{outside.name}"
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_project(tmp_path)
        raise AssertionError("Expected path traversal data_file to be rejected")
    except ValueError as exc:
        assert "escapes the project folder" in str(exc) or "relative path" in str(exc)


def test_load_project_rejects_absolute_data_file(tmp_path) -> None:
    project = ProjectState()
    project.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
    save_project(project, tmp_path)

    project_path = tmp_path / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    absolute = (tmp_path / payload["curves"][0]["data_file"]).resolve()
    payload["curves"][0]["data_file"] = str(absolute)
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    try:
        load_project(tmp_path)
        raise AssertionError("Expected absolute data_file to be rejected")
    except ValueError as exc:
        assert "relative path" in str(exc)


def test_load_project_ignores_unknown_curve_fields(tmp_path) -> None:
    project = ProjectState()
    project.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
    save_project(project, tmp_path)

    project_path = tmp_path / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["curves"][0]["unexpected_future_field"] = {"nested": True}
    payload["groups"] = [
        {
            "group_id": "g1",
            "name": "group",
            "curve_ids": [payload["curves"][0]["curve_id"]],
            "unexpected_group_field": 123,
        }
    ]
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_project(tmp_path)

    assert len(loaded.curves) == 1
    assert loaded.curves[0].name == "curve"
    assert len(loaded.groups) == 1
    assert loaded.groups[0].name == "group"
    assert not hasattr(loaded.curves[0], "unexpected_future_field")


def test_main_window_save_and_open_project_lifecycle(tmp_path) -> None:
    _app()
    window = MainWindow()
    try:
        assert not window.is_project_dirty()
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))

        assert window.is_project_dirty()
        assert window.windowTitle().endswith("*")

        project_file = window.save_project_to_folder(tmp_path)

        assert project_file.name == "project.json"
        assert project_file.exists()
        assert not window.is_project_dirty()
        assert window.current_project_folder == tmp_path

        window.add_curve(CurveData.create(name="second", q=[0.1, 0.2], intensity=[20, 30]))
        assert window.is_project_dirty()

        window.open_project_folder(tmp_path)

        assert not window.is_project_dirty()
        assert len(window.project.curves) == 1
        assert window.project.curves[0].name == "curve"
        assert window.curve_list.count() == 1
    finally:
        window.close()


def test_dirty_project_cancel_blocks_new_project(monkeypatch) -> None:
    _app()
    window = MainWindow()
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(window, "_handle_unsaved_changes_before_destructive_action", lambda: False)

        window.new_project()

        assert len(window.project.curves) == 1
    finally:
        window.close()


def test_dirty_project_discard_allows_new_project(monkeypatch) -> None:
    _app()
    window = MainWindow()
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(window, "_handle_unsaved_changes_before_destructive_action", lambda: True)

        window.new_project()

        assert len(window.project.curves) == 0
        assert not window.is_project_dirty()
    finally:
        window.close()


def test_dirty_project_save_choice_calls_save_and_continues(monkeypatch) -> None:
    _app()
    window = MainWindow()
    called = {"save": False}
    try:
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(window, "save_project", lambda: called.__setitem__("save", True) or True)
        monkeypatch.setattr(main_window_module, "QMessageBox", _SaveChoiceMessageBox)

        result = window._handle_unsaved_changes_before_destructive_action()

        assert result is True
        assert called["save"] is True
    finally:
        window.close()


def test_save_without_project_path_enters_save_as(monkeypatch) -> None:
    _app()
    window = MainWindow()
    called = {"save_as": False}
    try:
        window.current_project_folder = None
        monkeypatch.setattr(window, "save_project_as_dialog", lambda: called.__setitem__("save_as", True) or False)

        assert window.save_project() is False
        assert called["save_as"] is True
    finally:
        window.hide()
        window.close()


def test_dirty_project_cancel_blocks_visible_close(monkeypatch) -> None:
    _app()
    window = MainWindow()
    try:
        window.show()
        window.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
        monkeypatch.setattr(window, "_handle_unsaved_changes_before_destructive_action", lambda: False)
        event = _FakeCloseEvent()

        window.closeEvent(event)

        assert event.ignored is True
        assert event.accepted is False
    finally:
        window.close()

def test_project_writes_schema_version_and_loads_legacy_without_it(tmp_path) -> None:
    from app.core.project import PROJECT_SCHEMA_VERSION, load_project, save_project

    project = ProjectState()
    project.add_curve(CurveData.create(name="curve", q=[0.1, 0.2], intensity=[10, 20]))
    save_project(project, tmp_path)
    payload = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == PROJECT_SCHEMA_VERSION

    # Legacy projects without schema_version still load.
    del payload["schema_version"]
    (tmp_path / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    restored = load_project(tmp_path)
    assert len(restored.curves) == 1
