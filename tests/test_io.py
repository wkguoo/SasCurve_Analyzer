from __future__ import annotations

from pathlib import Path

import numpy as np

from app.core.io import load_curve


def test_csv_import() -> None:
    path = Path("examples/example_absolute_sas_curve.csv")
    curve = load_curve(path, q_column="q", intensity_column="I", error_column="error")
    assert curve.q.size == 30
    assert curve.error is not None
    assert curve.source_file is not None
    assert curve.processing_history[0]["action"] == "import"


def test_txt_dat_separator_detection(tmp_path: Path) -> None:
    txt_path = tmp_path / "curve.dat"
    txt_path.write_text("# comment\nq I sigma\n0.1 10 0.2\n0.2 5 0.1\n", encoding="utf-8")
    curve = load_curve(txt_path, q_column="q", intensity_column="I", error_column="sigma")
    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])
    assert curve.error is not None


def test_import_without_error_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.1,10\n0.2,5\n", encoding="utf-8")
    curve = load_curve(csv_path, q_column="q", intensity_column="I", error_column=None)
    assert curve.error is None
    assert curve.q.size == 2


def test_blank_error_column_is_treated_as_missing(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("q,I\n0.1,10\n0.2,5\n", encoding="utf-8")
    curve = load_curve(csv_path, q_column="q", intensity_column="I", error_column="")
    assert curve.error is None


def test_import_reads_gbk_encoded_curve(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve_gbk.csv"
    csv_path.write_bytes("# 样品\nq,I\n0.1,10\n0.2,5\n".encode("gbk"))

    curve = load_curve(csv_path, q_column="q", intensity_column="I")

    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])


def test_import_reads_utf16_encoded_curve(tmp_path: Path) -> None:
    csv_path = tmp_path / "curve_utf16.csv"
    csv_path.write_text("# sample\nq,I\n0.1,10\n0.2,5\n", encoding="utf-16")

    curve = load_curve(csv_path, q_column="q", intensity_column="I")

    assert np.allclose(curve.q, [0.1, 0.2])
    assert np.allclose(curve.intensity, [10.0, 5.0])

