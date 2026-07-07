from __future__ import annotations

import json

from app.core.settings import AppSettings, load_settings, load_settings_with_info, save_settings


def test_load_default_settings_when_file_missing(tmp_path) -> None:
    settings = load_settings(tmp_path / "missing.json")
    assert settings == AppSettings()
    assert settings.allow_slight_negative_intensity is True
    assert settings.slight_negative_abs_ratio_threshold == 1e-3
    assert settings.slight_negative_fraction_threshold == 0.05


def test_load_settings_with_info_marks_missing_file_defaults(tmp_path) -> None:
    settings, info = load_settings_with_info(tmp_path / "missing.json")
    assert settings == AppSettings()
    assert info.exists is False
    assert info.loaded_from_file is False
    assert info.used_defaults is True


def test_save_and_load_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    saved_path = save_settings(AppSettings(default_q_unit="nm^-1", default_export_dir="out"), path)
    loaded, info = load_settings_with_info(saved_path)
    assert loaded.default_q_unit == "nm^-1"
    assert loaded.default_export_dir == "out"
    assert info.exists is True
    assert info.loaded_from_file is True
    assert info.used_defaults is False


def test_load_settings_uses_defaults_for_missing_fields(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"default_q_unit": "nm^-1"}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.default_q_unit == "nm^-1"
    assert settings.default_figure_format == "png"
    assert settings.allow_slight_negative_intensity is True
    assert settings.slight_negative_abs_ratio_threshold == 1e-3


def test_load_settings_returns_defaults_for_invalid_json(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{invalid", encoding="utf-8")
    settings, info = load_settings_with_info(path)
    assert settings == AppSettings()
    assert info.exists is True
    assert info.loaded_from_file is False
    assert info.used_defaults is True
    assert info.error_message


def test_negative_intensity_threshold_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    original = AppSettings(
        allow_slight_negative_intensity=False,
        slight_negative_abs_ratio_threshold=0.02,
        slight_negative_fraction_threshold=0.25,
    )
    saved_path = save_settings(original, path)
    loaded, info = load_settings_with_info(saved_path)

    assert info.loaded_from_file is True
    assert loaded.allow_slight_negative_intensity is False
    assert loaded.slight_negative_abs_ratio_threshold == 0.02
    assert loaded.slight_negative_fraction_threshold == 0.25
