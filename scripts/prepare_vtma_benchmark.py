"""Prepare a reproducible, pinned VTMA 1D-curve study input outside the repo.

The converter preserves the upstream HDF5 file and writes selected measured
arrays as 17-significant-digit CSV files. It needs ``h5py`` and ``numpy`` only
when invoked; neither is added to the application's runtime dependencies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

import numpy as np


UPSTREAM_COMMIT = "066ef088eda50056f327727e825dbb3285409097"
UPSTREAM_SHA256 = "65e9e45e71f063c4da775c3854314b4a9ad4753ed4b30faf93ecd39e8c29b86a"
UPSTREAM_URL = (
    "https://raw.githubusercontent.com/SasView/sasdata/"
    f"{UPSTREAM_COMMIT}/sasdata/example_data/1d_data/VTMA.h5"
)
SAMPLE_ID = "VTMA13b_2_870C"
FRAME_COUNT = 12
CSV_COLUMNS = ("Q", "I", "Idev", "Qdev")
CSV_HEADER = "q_A_inv,intensity_cm_inv,error,q_resolution_A_inv"
METADATA_COLUMNS = (
    "source_file", "sample_id", "frame_index", "time_s", "temperature_C",
    "hdf5_entry", "points", "sha256",
)
ENTRY_PATTERN = re.compile(
    r"^VTMA13b_2_870C_(?P<minute>\d+)min_(?P<frame>\d+)_mrg$"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_entries(names: list[str], limit: int = FRAME_COUNT) -> list[tuple[str, int, int]]:
    """Select merged 870 C entries in numeric frame order."""
    selected = []
    for name in names:
        match = ENTRY_PATTERN.fullmatch(name)
        if match:
            selected.append((name, int(match["frame"]), int(match["minute"])))
    selected.sort(key=lambda row: row[1])
    if len(selected) < limit:
        raise ValueError(f"Expected at least {limit} matching VTMA entries; found {len(selected)}")
    return selected[:limit]


def read_entry_arrays(hdf5_file, entry_name: str) -> np.ndarray:
    """Read Q, I, Idev and Qdev unchanged as binary64 columns."""
    group = hdf5_file[f"{entry_name}/{entry_name}"]
    columns = [np.asarray(group[name], dtype=np.float64) for name in CSV_COLUMNS]
    if any(column.ndim != 1 for column in columns):
        raise ValueError(f"{entry_name} has a non-vector measurement column")
    lengths = {column.size for column in columns}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError(f"{entry_name} has missing or unequal measurement columns")
    return np.column_stack(columns)


def curve_csv_text(values: np.ndarray) -> str:
    """Return CSV text and assert exact non-NaN binary64 round-trip."""
    output = io.StringIO(newline="")
    np.savetxt(output, values, delimiter=",", header=CSV_HEADER, comments="", fmt="%.17g")
    text = output.getvalue()
    restored = np.loadtxt(io.StringIO(text), delimiter=",", skiprows=1, dtype=np.float64, ndmin=2)
    _verify_binary64(values, restored)
    return text


def _verify_binary64(values: np.ndarray, restored: np.ndarray) -> None:
    """Preserve finite bits and missing positions when checking a derived file."""
    original = np.ascontiguousarray(values, dtype=np.float64)
    restored = np.ascontiguousarray(restored, dtype=np.float64)
    if original.shape != restored.shape or not np.array_equal(np.isnan(original), np.isnan(restored)):
        raise ValueError("CSV round-trip changed array shape or missing-value positions")
    finite_bits = ~np.isnan(original)
    if not np.array_equal(original.view(np.uint64)[finite_bits], restored.view(np.uint64)[finite_bits]):
        raise ValueError("CSV round-trip changed a binary64 measurement value")


def study_config(metadata_path: Path) -> dict:
    return {
        "schema_version": 1,
        "grouping": "metadata",
        "analysis": {
            "metadata_path": str(metadata_path.resolve()),
            "sample_type": "unknown",
            "enable_shape_models": False,
            "allow_per_frame_range_fallback": True,
            "enable_sequence_analysis": True,
            "sequence_axis": "time_s",
            "enable_range_sensitivity": True,
        },
        "figures": {"formats": ["png", "svg", "pdf"], "dpi": 200, "max_overlay_curves": 24},
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _download_pinned(path: Path) -> None:
    request = Request(UPSTREAM_URL, headers={"User-Agent": "SasCurve-Analyzer-benchmark/1"})
    with urlopen(request, timeout=60) as response, path.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)


def _obtain_source(root: Path, supplied_source: Path | None) -> tuple[Path, str]:
    target = root / "VTMA.h5"
    source = supplied_source.resolve(strict=True) if supplied_source else None
    if target.exists():
        if target.is_symlink():
            raise ValueError(f"Refusing to reuse a linked HDF5 source: {target}")
        if sha256_file(target) != UPSTREAM_SHA256:
            raise ValueError(f"Refusing to replace existing HDF5 source with a different file: {target}")
        if source and source != target and sha256_file(source) != UPSTREAM_SHA256:
            raise ValueError(f"Local source does not match pinned SasView/sasdata file: {source}")
        return target, "reused_verified"
    if source is None:
        with NamedTemporaryFile(prefix="sascurve-vtma-download-", suffix=".h5", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            _download_pinned(temporary_path)
            if sha256_file(temporary_path) != UPSTREAM_SHA256:
                raise ValueError("Downloaded VTMA.h5 does not match the pinned SHA-256")
            source = temporary_path
            source_action = "downloaded_pinned"
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    else:
        if sha256_file(source) != UPSTREAM_SHA256:
            raise ValueError(f"Local source does not match pinned SasView/sasdata file: {source}")
        source_action = "copied_from_local"
    temporary_copy = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(source, temporary_copy)
        if sha256_file(temporary_copy) != UPSTREAM_SHA256:
            raise ValueError("Copied VTMA.h5 failed the pinned SHA-256 check")
        os.replace(temporary_copy, target)
    finally:
        temporary_copy.unlink(missing_ok=True)
        if source == locals().get("temporary_path"):
            source.unlink(missing_ok=True)
    return target, source_action


def _expected_frame_metadata(selected: list[tuple[str, int, int]]) -> list[dict[str, object]]:
    return [
        {
            "sample_id": SAMPLE_ID,
            "frame_index": frame,
            "time_s": minute * 60,
            "temperature_C": 870,
            "hdf5_entry": entry,
        }
        for entry, frame, minute in selected
    ]


def _existing_package_matches(root: Path, rows: list[dict[str, object]]) -> dict[str, tuple[str, int]] | None:
    input_root = root / "inputs"
    sample_root = input_root / SAMPLE_ID
    expected_files = {str(row["source_file"]).split("/", 1)[1] for row in rows}
    if input_root.is_symlink() or sample_root.is_symlink():
        raise ValueError(f"Refusing to reuse a linked input directory: {sample_root}")
    if not sample_root.is_dir():
        return None
    paths = list(sample_root.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError(f"Refusing to reuse linked curve inputs: {sample_root}")
    actual_files = {path.relative_to(sample_root).as_posix() for path in paths if path.is_file()}
    if actual_files != expected_files:
        raise ValueError(f"Existing input directory has a different file set: {sample_root}")
    checked: dict[str, tuple[str, int]] = {}
    for row in rows:
        path = input_root / str(row["source_file"])
        if not path.is_file():
            raise ValueError(f"Refusing to overwrite or reuse a different input: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            header = stream.readline()
            digest.update(header)
            if header.rstrip(b"\r\n").decode("ascii", "replace") != CSV_HEADER:
                raise ValueError(f"Existing curve has an unexpected CSV header: {path}")
            points = 0
            for line in stream:
                digest.update(line)
                if line.strip():
                    if line.rstrip(b"\r\n").count(b",") != 3:
                        raise ValueError(f"Existing curve row does not have four columns: {path}")
                    points += 1
        checked[str(row["source_file"])] = (digest.hexdigest(), points)
    return checked


def _write_csv_metadata(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=METADATA_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(output_root: Path, source: Path | None = None) -> dict[str, object]:
    """Prepare or integrity-check the pinned twelve-frame input package."""
    root = output_root.resolve()
    repository = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repository):
        raise ValueError("Choose an artifact output root outside the repository")
    root.mkdir(parents=True, exist_ok=True)
    hdf5_path, source_action = _obtain_source(root, source)

    import h5py

    with h5py.File(hdf5_path, "r") as hdf5_file:
        selected = select_entries(list(hdf5_file.keys()))
        metadata = _expected_frame_metadata(selected)
        input_root = root / "inputs"
        sample_root = input_root / SAMPLE_ID
        metadata_path = root / "metadata.csv"
        config_path = root / "config.json"
        receipt_path = root / "input_receipt.json"

        inputs_exist = sample_root.exists()
        if inputs_exist:
            expected_rows = [
                dict(row, source_file=f"{SAMPLE_ID}/{entry}.csv")
                for row, (entry, _, _) in zip(metadata, selected)
            ]
            existing_hashes = _existing_package_matches(root, expected_rows)
            if (
                existing_hashes is None
                or not metadata_path.is_file()
                or not config_path.is_file()
                or not receipt_path.is_file()
            ):
                raise ValueError(f"Existing VTMA input package is incomplete; refusing to replace it: {root}")
            csv_rows = []
            for row, (entry, _, _) in zip(metadata, selected):
                file_name = f"{SAMPLE_ID}/{entry}.csv"
                digest, points = existing_hashes[file_name]
                # A self-consistent CSV/receipt is not proof of its HDF5 origin.
                _verify_binary64(read_entry_arrays(hdf5_file, entry),
                                 np.loadtxt(input_root / file_name, delimiter=",", skiprows=1, ndmin=2))
                csv_rows.append({
                    "source_file": file_name,
                    **row,
                    "points": points,
                    "sha256": digest,
                })
            expected_config = study_config(metadata_path)
            if json.loads(config_path.read_text(encoding="utf-8")) != expected_config:
                raise ValueError(f"Existing study config differs from the requested VTMA config: {config_path}")
            prior_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if prior_receipt.get("upstream_commit") != UPSTREAM_COMMIT or prior_receipt.get("upstream_sha256") != UPSTREAM_SHA256 or prior_receipt.get("frames") != csv_rows:
                raise ValueError(f"Existing input receipt differs from the pinned source: {receipt_path}")
            with metadata_path.open("r", encoding="utf-8", newline="") as stream:
                existing_rows = list(csv.DictReader(stream))
            if existing_rows != [{name: str(value) for name, value in row.items()} for row in csv_rows]:
                raise ValueError(f"Existing metadata differs from the pinned VTMA inputs: {metadata_path}")
            if sha256_file(hdf5_path) != UPSTREAM_SHA256:
                raise ValueError("VTMA.h5 changed while its prepared input package was being checked")
            return {"status": "reused", "output_root": str(root), "hdf5": str(hdf5_path), "source_action": source_action, "frames": len(csv_rows)}

        if any(path.exists() for path in (metadata_path, config_path, receipt_path)):
            raise ValueError(f"Preparation metadata already exists without its input directory: {root}")
        sample_root.mkdir(parents=True, exist_ok=False)
        csv_rows = []
        try:
            for row, (entry, _, _) in zip(metadata, selected):
                values = read_entry_arrays(hdf5_file, entry)
                text = curve_csv_text(values)
                file_name = f"{SAMPLE_ID}/{entry}.csv"
                path = input_root / file_name
                path.write_text(text, encoding="utf-8", newline="")
                csv_rows.append({
                    "source_file": file_name,
                    **row,
                    "points": int(values.shape[0]),
                    "sha256": sha256_file(path),
                })
            if sha256_file(hdf5_path) != UPSTREAM_SHA256:
                raise ValueError("VTMA.h5 changed during extraction; generated inputs were discarded")
            _write_csv_metadata(metadata_path, csv_rows)
            _write_json(config_path, study_config(metadata_path))
            _write_json(receipt_path, {
                "upstream_commit": UPSTREAM_COMMIT,
                "upstream_sha256": UPSTREAM_SHA256,
                "frames": csv_rows,
            })
        except Exception:
            # Do not leave a partial input set that a later run could mistake for complete.
            if not sample_root.resolve().is_relative_to(root) or sample_root.is_symlink():
                raise ValueError("Refusing cleanup outside the benchmark output root")
            shutil.rmtree(sample_root)
            for path in (metadata_path, config_path, receipt_path):
                path.unlink(missing_ok=True)
            raise
    return {"status": "prepared", "output_root": str(root), "hdf5": str(hdf5_path), "source_action": source_action, "frames": len(csv_rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True, help="Artifact directory outside the repository")
    parser.add_argument("--source", type=Path, help="Optional local copy of the pinned VTMA.h5")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.output_root, args.source)
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
