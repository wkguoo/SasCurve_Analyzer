from __future__ import annotations

from hashlib import sha256
from io import StringIO
from pathlib import Path

import numpy as np
import pytest

from app.core import io
from app.core.import_preview import preview_curve_file


def _file(path: Path, intensity: int = 10) -> Path:
    path.write_text(f"q,I,error\n0.01,{intensity},0.1\n0.02,5,0.2\n0.03,2,0.3\n", encoding="utf-8")
    return path


def _count_parses(monkeypatch) -> list:
    calls = []
    original = io.pd.read_csv

    def parse(source, *args, **kwargs):
        if isinstance(source, StringIO):
            calls.append(source.getvalue())
        return original(source, *args, **kwargs)

    monkeypatch.setattr(io.pd, "read_csv", parse)
    return calls


def test_preview_mapping_range_and_import_reuse_only_raw_table(tmp_path, monkeypatch):
    path = _file(tmp_path / "curve.csv")
    calls = _count_parses(monkeypatch)
    cache = io.TableReadCache()
    first = preview_curve_file(path, table_cache=cache)
    second = preview_curve_file(path, table_cache=cache, limit_q_range=True, q_min=0.01, q_max=0.02)
    curve = io.load_curve(path, error_column="error", table_cache=cache)
    assert len(calls) == 1
    assert first.row_count == 3
    assert second.diagnostics["would_import_point_count"] == 2
    assert curve.q.size == curve.error.size == 3
    assert not preview_curve_file(path, q_column="missing", intensity_column="I", table_cache=cache).can_import
    assert len(calls) == 1  # Mapping diagnostics are recomputed without reparsing.


@pytest.mark.parametrize(
    ("column", "kind"),
    [("std_intensity", "series_std"), ("std", "unknown"), ("error", "measurement")],
)
def test_cached_preview_and_import_preserve_uncertainty_semantics(
    tmp_path, monkeypatch, column, kind
):
    path = tmp_path / "contract.csv"
    path.write_text(
        f"q_nm_inv,I,{column}\n0.1,10,0.5\n0.2,8,0.4\n0.3,6,0.3\n",
        encoding="utf-8",
    )
    source = path.read_bytes()
    calls = _count_parses(monkeypatch)
    cache = io.TableReadCache()
    preview = preview_curve_file(
        path, q_column="q_nm_inv", intensity_column="I", error_column=column,
        table_cache=cache,
    )
    curve = io.load_curve(
        path, q_column="q_nm_inv", intensity_column="I", error_column=column,
        q_unit="nm^-1", table_cache=cache,
    )
    assert preview.can_import
    assert preview.diagnostics["uncertainty_kind"] == kind
    assert curve.metadata["uncertainty_kind"] == kind
    np.testing.assert_allclose(curve.q, [0.1, 0.2, 0.3])
    if kind == "measurement":
        np.testing.assert_allclose(curve.error, [0.5, 0.4, 0.3])
    else:
        assert curve.error is None
        assert curve.metadata["non_measurement_error"]["values"] == [0.5, 0.4, 0.3]
    assert len(calls) == 1
    assert path.read_bytes() == source


def test_signature_change_reparses_and_caller_mutation_does_not_leak(tmp_path, monkeypatch):
    path = _file(tmp_path / "curve.csv")
    calls = _count_parses(monkeypatch)
    cache = io.TableReadCache()
    table = cache.read(path)
    table.loc[0, "I"] = 999
    assert cache.read(path).loc[0, "I"] == 10
    _file(path, intensity=100)
    assert cache.read(path).loc[0, "I"] == 100
    assert len(calls) == 2
    cache.clear()
    assert cache.read(path).loc[0, "I"] == 100
    assert len(calls) == 3


def test_replacement_with_same_size_and_mtime_invalidates_identity(tmp_path, monkeypatch):
    import os

    path = _file(tmp_path / "curve.csv")
    cache = io.TableReadCache()
    assert cache.read(path).loc[0, "I"] == 10
    original = path.stat()
    replacement = _file(tmp_path / "replacement.csv", intensity=20)
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    replacement.replace(path)
    assert cache.read(path).loc[0, "I"] == 20


def test_read_that_changes_source_and_parse_failure_are_not_cached(tmp_path):
    path = _file(tmp_path / "curve.csv")
    cache = io.TableReadCache()

    def changed(source):
        table = io.read_table(source)
        _file(source, intensity=100)
        return table

    assert cache.read(path, changed).loc[0, "I"] == 10
    assert cache.read(path).loc[0, "I"] == 100
    cache.clear()
    path.write_text("# comment only\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No tabular data"):
        cache.read(path)
    _file(path)
    assert cache.read(path).loc[0, "I"] == 10


def test_entry_and_byte_limits_bound_memory(tmp_path, monkeypatch):
    first, second = _file(tmp_path / "first.csv"), _file(tmp_path / "second.csv")
    calls = _count_parses(monkeypatch)
    cache = io.TableReadCache(max_entries=1)
    for path in (first, second, first):
        cache.read(path)
    assert len(calls) == 3
    cache = io.TableReadCache(max_bytes=1)
    cache.read(first)
    cache.read(first)
    assert len(calls) == 5  # Oversized tables are usable, but not retained.


def test_changed_parser_is_not_treated_as_equivalent_evidence(tmp_path):
    path = _file(tmp_path / "curve.csv")
    cache = io.TableReadCache()
    assert cache.read(path).loc[0, "I"] == 10

    def alternate(source):
        table = io.read_table(source)
        table.loc[0, "I"] = 20
        return table

    assert cache.read(path, alternate).loc[0, "I"] == 20
    assert cache.read(path).loc[0, "I"] == 10


def test_snapshot_guard_rejects_changed_bytes_even_with_unchanged_signature(tmp_path, monkeypatch):
    path = _file(tmp_path / "curve.csv")
    content = path.read_bytes()
    signature = io.TableReadCache._signature(path)
    cache = io.TableReadCache(expected_hashes={path: sha256(content).hexdigest()})
    monkeypatch.setattr(io.TableReadCache, "_signature", staticmethod(lambda _path: signature))
    _file(path, intensity=20)
    assert path.stat().st_size == len(content)
    with pytest.raises(io.SourceSnapshotError, match="source snapshot"):
        cache.read(path)
    path.write_bytes(content)
    assert cache.read(path).loc[0, "I"] == 10  # Failed parses never enter the cache.


def test_snapshot_guard_requires_known_source_and_parser_byte_provenance(tmp_path):
    path = _file(tmp_path / "curve.csv")
    cache = io.TableReadCache(expected_hashes={path: sha256(path.read_bytes()).hexdigest()})
    with pytest.raises(io.SourceSnapshotError, match="source snapshot"):
        cache.read(path, lambda _path: io.pd.DataFrame({"q": [0.01], "I": [10]}))
    unknown = _file(tmp_path / "unplanned.csv")
    with pytest.raises(io.SourceSnapshotError, match="source snapshot"):
        cache.read(unknown)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "gbk", "utf-16"])
def test_encoding_fallback_reads_source_bytes_once(tmp_path, monkeypatch, encoding):
    path = tmp_path / "curve.csv"
    content = "# 样品\r\nq,I\r\n0.01,10\r\n0.02,5\r\n".encode(encoding)
    path.write_bytes(content)
    opens = []
    original = Path.open

    def opened(source, *args, **kwargs):
        if source == path:
            opens.append(source)
        return original(source, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    cache = io.TableReadCache(expected_hashes={path: sha256(content).hexdigest()})
    curve = io.load_curve(path, table_cache=cache)
    np.testing.assert_allclose(curve.intensity, [10, 5])
    assert len(opens) == 1


def test_unsupported_encoding_keeps_diagnostic(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"\x81")
    with pytest.raises(UnicodeError, match="supported encodings"):
        io.read_table(path)


def test_cache_never_suppresses_missing_file_error(tmp_path):
    path = _file(tmp_path / "curve.csv")
    cache = io.TableReadCache()
    cache.read(path)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        cache.read(path)
