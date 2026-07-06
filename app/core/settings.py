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


def load_settings(path: str | Path | None = None) -> AppSettings:
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return AppSettings()
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    if not isinstance(payload, dict):
        return AppSettings()
    defaults = asdict(AppSettings())
    allowed = {field.name for field in fields(AppSettings)}
    merged = {**defaults, **{key: value for key, value in payload.items() if key in allowed}}
    return AppSettings(**merged)


def save_settings(settings: AppSettings, path: str | Path | None = None) -> Path:
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return settings_path
