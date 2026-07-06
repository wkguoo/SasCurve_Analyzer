from __future__ import annotations

import json

from app.core.settings import AppSettings, load_settings, save_settings


def test_load_default_settings_when_file_missing(tmp_path) -> None:
    settings = load_settings(tmp_path / "missing.json")
    assert settings == AppSettings()


def test_save_and_load_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    saved_path = save_settings(AppSettings(default_q_unit="nm^-1", default_export_dir="out"), path)
    loaded = load_settings(saved_path)
    assert loaded.default_q_unit == "nm^-1"
    assert loaded.default_export_dir == "out"


def test_load_settings_uses_defaults_for_missing_fields(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"default_q_unit": "nm^-1"}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.default_q_unit == "nm^-1"
    assert settings.default_figure_format == "png"


def test_load_settings_returns_defaults_for_invalid_json(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")
    settings = load_settings(path)
    assert settings == AppSettings()
