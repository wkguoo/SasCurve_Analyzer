from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.data_model import CurveData


COMMENT_PREFIXES = ("#", ";", "//")


def _read_text_without_comments(path: Path) -> str:
    kept_lines: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
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

    history = [
        {
            "action": "import",
            "source_file": str(file_path),
            "q_column": q_column,
            "intensity_column": intensity_column,
            "error_column": error_column,
        }
    ]
    return CurveData.create(
        name=name or file_path.stem,
        q=q,
        intensity=intensity,
        error=error,
        q_unit=q_unit,
        intensity_unit=intensity_unit,
        source_file=file_path,
        metadata=metadata,
        processing_history=history,
    )

