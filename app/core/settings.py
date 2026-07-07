from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


DEFAULT_SETTINGS_PATH = Path("sas_curve_analyzer_settings.json")


@dataclass
class AppSettings:
    default_q_unit: str = "A^-1"
    default_figure_format: str = "png"
    show_error_bars: bool = True
    show_method_warnings: bool = True
    default_export_dir: str = "exports"
    log_level: str = "INFO"
    allow_slight_negative_intensity: bool = True
    slight_negative_abs_ratio_threshold: float = 1e-3
    slight_negative_fraction_threshold: float = 0.05


@dataclass
class SettingsLoadInfo:
    path: str
    exists: bool
    loaded_from_file: bool
    used_defaults: bool
    error_message: str | None = None


def load_settings_with_info(path: str | Path | None = None) -> tuple[AppSettings, SettingsLoadInfo]:
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return AppSettings(), SettingsLoadInfo(str(settings_path), exists=False, loaded_from_file=False, used_defaults=True)
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return AppSettings(), SettingsLoadInfo(
            str(settings_path), exists=True, loaded_from_file=False, used_defaults=True, error_message=str(exc)
        )
    if not isinstance(payload, dict):
        return AppSettings(), SettingsLoadInfo(
            str(settings_path), exists=True, loaded_from_file=False, used_defaults=True, error_message="Settings JSON root is not an object."
        )
    defaults = asdict(AppSettings())
    allowed = {field.name for field in fields(AppSettings)}
    merged = {**defaults, **{key: value for key, value in payload.items() if key in allowed}}
    return AppSettings(**merged), SettingsLoadInfo(str(settings_path), exists=True, loaded_from_file=True, used_defaults=False)


def load_settings(path: str | Path | None = None) -> AppSettings:
    settings, _info = load_settings_with_info(path)
    return settings


def save_settings(settings: AppSettings, path: str | Path | None = None) -> Path:
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path
