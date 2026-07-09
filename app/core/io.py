from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.data_model import CurveData


COMMENT_PREFIXES = ("#", ";", "//")
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "utf-16")


class QImportRangeFilterError(ValueError):
    """Raised when import-time q range filtering leaves too few points."""

    def __init__(self, message: str, diagnostics: dict[str, Any]):
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


def read_text_with_encoding_fallback(path: str | Path) -> tuple[str, str]:
    file_path = Path(path)
    errors: list[str] = []
    for encoding in TEXT_ENCODINGS:
        try:
            return file_path.read_text(encoding=encoding), encoding
        except UnicodeError as exc:
            errors.append(f"{encoding}: {exc}")
    tried = ", ".join(TEXT_ENCODINGS)
    raise UnicodeError(f"Could not decode {file_path} with supported encodings: {tried}. Details: {' | '.join(errors)}")


def _read_text_without_comments(path: Path) -> str:
    kept_lines: list[str] = []
    text, _encoding = read_text_with_encoding_fallback(path)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in COMMENT_PREFIXES):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def read_table(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    text = _read_text_without_comments(file_path)
    if not text.strip():
        raise ValueError(f"No tabular data found in {file_path}")
    return pd.read_csv(StringIO(text), sep=r"[,\t ]+", engine="python")


def _column_to_series(df: pd.DataFrame, column: str | int) -> pd.Series:
    if isinstance(column, int):
        return df.iloc[:, column]
    if column in df.columns:
        return df[column]

    normalized = {str(name).strip().lower(): name for name in df.columns}
    key = str(column).strip().lower()
    if key in normalized:
        return df[normalized[key]]
    raise KeyError(f"Column '{column}' was not found. Available columns: {list(df.columns)}")


def validate_q_import_range(
    limit_q_range: bool,
    q_min: float | None,
    q_max: float | None,
) -> tuple[float | None, float | None]:
    if not limit_q_range:
        return None, None
    if q_min is None or q_max is None:
        raise ValueError("q range filter requires both q_min and q_max.")
    try:
        q_min_value = float(q_min)
        q_max_value = float(q_max)
    except (TypeError, ValueError) as exc:
        raise ValueError("q_min and q_max must be numeric finite values.") from exc
    if not np.isfinite(q_min_value) or not np.isfinite(q_max_value):
        raise ValueError("q_min and q_max must be finite values.")
    if q_min_value >= q_max_value:
        raise ValueError(f"q range is invalid: q_min={q_min_value} must be less than q_max={q_max_value}.")
    return q_min_value, q_max_value


def _finite_min_max(values: np.ndarray) -> tuple[float | None, float | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None, None
    return float(np.min(finite)), float(np.max(finite))


def apply_q_import_range_filter(
    q: Any,
    intensity: Any,
    error: Any | None = None,
    *,
    limit_q_range: bool,
    q_min: float | None,
    q_max: float | None,
    minimum_points: int = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, dict[str, Any]]:
    q_array = np.asarray(q, dtype=float)
    intensity_array = np.asarray(intensity, dtype=float)
    error_array = None if error is None else np.asarray(error, dtype=float)

    if q_array.shape != intensity_array.shape:
        raise ValueError("q and intensity columns must have the same length.")
    if error_array is not None and error_array.shape != q_array.shape:
        raise ValueError("error column must have the same length as q.")

    q_min_value, q_max_value = validate_q_import_range(limit_q_range, q_min, q_max)
    raw_point_count = int(q_array.size)
    finite_qi_mask = np.isfinite(q_array) & np.isfinite(intensity_array)

    if limit_q_range:
        keep_mask = finite_qi_mask & (q_array >= q_min_value) & (q_array <= q_max_value)
        q_filtered = q_array[keep_mask]
        intensity_filtered = intensity_array[keep_mask]
        error_filtered = None if error_array is None else error_array[keep_mask]
    else:
        q_filtered = q_array
        intensity_filtered = intensity_array
        error_filtered = error_array

    if q_filtered.shape != intensity_filtered.shape:
        raise ValueError("q and intensity columns have different lengths after q range filtering.")
    if error_filtered is not None and error_filtered.shape != q_filtered.shape:
        raise ValueError("error column has a different length after q range filtering.")

    imported_point_count = int(q_filtered.size)
    imported_q_min, imported_q_max = _finite_min_max(q_filtered)
    diagnostics = {
        "q_range_filter_enabled": bool(limit_q_range),
        "q_range_filter_min": q_min_value,
        "q_range_filter_max": q_max_value,
        "raw_point_count": raw_point_count,
        "finite_qi_point_count": int(np.sum(finite_qi_mask)),
        "imported_point_count": imported_point_count,
        "filtered_out_point_count": raw_point_count - imported_point_count,
        "q_min_imported": imported_q_min,
        "q_max_imported": imported_q_max,
    }

    if limit_q_range and imported_point_count < minimum_points:
        message = (
            "q range filter kept "
            f"{imported_point_count} points. Check q_min={q_min_value} and q_max={q_max_value} "
            "or disable the import q-range filter."
        )
        raise QImportRangeFilterError(message, diagnostics)

    return q_filtered, intensity_filtered, error_filtered, diagnostics


def load_curve(
    path: str | Path,
    *,
    q_column: str | int = "q",
    intensity_column: str | int = "I",
    error_column: str | int | None = None,
    name: str | None = None,
    q_unit: str = "A^-1",
    intensity_unit: str = "a.u.",
    metadata: dict[str, Any] | None = None,
    limit_q_range: bool = False,
    q_min: float | None = None,
    q_max: float | None = None,
) -> CurveData:
    file_path = Path(path)
    df = read_table(file_path)
    if isinstance(error_column, str) and not error_column.strip():
        error_column = None
    q = pd.to_numeric(_column_to_series(df, q_column), errors="coerce").to_numpy()
    intensity = pd.to_numeric(_column_to_series(df, intensity_column), errors="coerce").to_numpy()

    error = None
    if error_column is not None:
        error = pd.to_numeric(_column_to_series(df, error_column), errors="coerce").to_numpy()

    if q.shape != intensity.shape:
        raise ValueError("q and intensity columns must have the same length.")
    if error is not None and error.shape != q.shape:
        raise ValueError("error column must have the same length as q.")

    q, intensity, error, q_filter_diagnostics = apply_q_import_range_filter(
        q,
        intensity,
        error,
        limit_q_range=limit_q_range,
        q_min=q_min,
        q_max=q_max,
    )

    curve_metadata = dict(metadata or {})
    if limit_q_range:
        curve_metadata["import_q_range_filter"] = {
            "enabled": True,
            "q_min": q_filter_diagnostics["q_range_filter_min"],
            "q_max": q_filter_diagnostics["q_range_filter_max"],
            "raw_point_count": q_filter_diagnostics["raw_point_count"],
            "finite_qi_point_count": q_filter_diagnostics["finite_qi_point_count"],
            "imported_point_count": q_filter_diagnostics["imported_point_count"],
            "filtered_out_point_count": q_filter_diagnostics["filtered_out_point_count"],
            "q_min_imported": q_filter_diagnostics["q_min_imported"],
            "q_max_imported": q_filter_diagnostics["q_max_imported"],
        }

    history = [
        {
            "action": "import",
            "source_file": str(file_path),
            "q_column": q_column,
            "intensity_column": intensity_column,
            "error_column": error_column,
        }
    ]
    if limit_q_range:
        history[0].update(
            {
                "q_range_filter_enabled": True,
                "q_range_filter_min": q_filter_diagnostics["q_range_filter_min"],
                "q_range_filter_max": q_filter_diagnostics["q_range_filter_max"],
                "raw_point_count": q_filter_diagnostics["raw_point_count"],
                "finite_qi_point_count": q_filter_diagnostics["finite_qi_point_count"],
                "imported_point_count": q_filter_diagnostics["imported_point_count"],
                "filtered_out_point_count": q_filter_diagnostics["filtered_out_point_count"],
            }
        )
    return CurveData.create(
        name=name or file_path.stem,
        q=q,
        intensity=intensity,
        error=error,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        source_file=file_path,
        metadata=curve_metadata,
        processing_history=history,
    )

