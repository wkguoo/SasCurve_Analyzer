"""Count real import/study work on disposable synthetic calibrated curves.

Run before and after a change with the same Python and command. No user data is
read, and the temporary study (including real PNG exports) is removed on exit.
Counts are deterministic evidence; timings also include local machine noise.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault("MPLBACKEND", "Agg")


@contextmanager
def measure(inputs: Path):
    import pandas as pd
    from app.core import study

    counts = Counter()
    opens = Counter()
    original_open = Path.open
    original_parse = pd.read_csv
    original_verify = study._verify_inventory

    def open_file(path, mode="r", *args, **kwargs):
        if "r" in mode and path.resolve().is_relative_to(inputs):
            opens[path.relative_to(inputs).as_posix()] += 1
        return original_open(path, mode, *args, **kwargs)

    def parse(source, *args, **kwargs):
        counts["curve_parses" if isinstance(source, StringIO) else "metadata_parses"] += 1
        return original_parse(source, *args, **kwargs)

    def verify(*args, **kwargs):
        counts["inventory_verifications"] += 1
        return original_verify(*args, **kwargs)

    start = perf_counter()
    with patch.object(Path, "open", open_file), patch.object(pd, "read_csv", parse), patch.object(study, "_verify_inventory", verify):
        yield counts
    counts["source_reads"] = sum(opens.values())
    counts["repeated_source_reads"] = sum(max(0, count - 1) for count in opens.values())
    counts["seconds"] = round(perf_counter() - start, 4)


def run_fixture() -> dict:
    import numpy as np
    from app.core import io, study
    from app.core.batch_import import infer_curve_columns
    from app.core.import_preview import preview_curve_file

    with TemporaryDirectory(prefix="sas-agent-benchmark-") as temporary:
        root = Path(temporary)
        inputs = root / "inputs"
        for sample in ("LD", "TD"):
            for frame in (1, 2):
                path = inputs / sample / f"frame_{frame}.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                q = np.geomspace(0.005, 0.2, 120)
                header, scale = ("q_nm_inv", 10) if frame == 2 else ("q_A_inv", 1)
                lines = [f"{header},intensity_cm_inv"]
                lines.extend(f"{x * scale:.14g},{100 * np.exp(-(x * 12) ** 2 / 3) + frame:.14g}" for x in q)
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        path = inputs / "LD/frame_1.csv"
        # Feature detection lets this same fixture run on the baseline commit.
        cache_type = getattr(io, "TableReadCache", None)
        options = {"table_cache": cache_type(max_entries=1)} if cache_type else {}
        with measure(inputs) as preview_counts:
            table = options["table_cache"].read(path, io.read_table) if options else io.read_table(path)
            columns = infer_curve_columns(table.columns)
            preview = preview_curve_file(path, **options)
            second = preview_curve_file(path, limit_q_range=True, q_min=0.01, q_max=0.1, **options)
            curve = io.load_curve(path, q_column=columns.q_column, intensity_column=columns.intensity_column, **options)
            assert preview.can_import and second.can_import and curve.q.size == 120

        large_inputs = root / "large_preview"
        large_inputs.mkdir()
        large = large_inputs / "curve.csv"
        q = np.geomspace(0.005, 0.2, 20_000)
        large.write_text("q,I\n" + "\n".join(f"{x:.14g},{100 / (1 + (x * 12) ** 2):.14g}" for x in q), encoding="utf-8")

        def large_preview(cache):
            options = {"table_cache": cache} if cache is not None else {}
            table = cache.read(large, io.read_table) if cache is not None else io.read_table(large)
            columns = infer_curve_columns(table.columns)
            assert preview_curve_file(large, **options).can_import
            assert preview_curve_file(large, limit_q_range=True, q_min=0.01, q_max=0.1, **options).can_import
            return io.load_curve(large, q_column=columns.q_column, intensity_column=columns.intensity_column, **options)

        with measure(large_inputs) as control_counts:
            control = large_preview(None)
        with measure(large_inputs) as cached_counts:
            cached = large_preview(cache_type(max_entries=1) if cache_type else None)
        np.testing.assert_array_equal(control.q, cached.q)
        np.testing.assert_array_equal(control.intensity, cached.intensity)

        from app.core.auto_batch_schema import AutoBatchConfig
        from app.core.batch_inputs import collect_batch_inputs

        selected = tuple(sorted((inputs / "LD").glob("*.csv")))
        sidecar = root / "metadata.csv"
        sidecar.write_text("source_file,frame_index,time_s\nLD/frame_1.csv,77,0\nLD/frame_2.csv,78,10\n", encoding="utf-8")
        config = AutoBatchConfig(batch_id="LD", metadata_path=sidecar)
        with measure(inputs) as metadata_control:
            full = collect_batch_inputs(inputs, replace(config, effective_q_range=(0, float(np.finfo(float).max))), input_paths=selected)
        sample = study.SampleInput("LD", selected, "directory")
        with measure(inputs) as metadata_preview:
            resolved = study._resolve_sample_config(sample, inputs, {"analysis": {"metadata_path": str(sidecar)}})
        assert resolved.effective_q_range == (max(float(c.q.min()) for c in full.curves), min(float(c.q.max()) for c in full.curves))
        formal = collect_batch_inputs(inputs, resolved, input_paths=selected)
        assert [c.metadata["frame_index"] for c in formal.curves] == [77, 78]
        assert [c.metadata["time_s"] for c in formal.curves] == [0, 10]

        settings = {"analysis": {"enable_shape_models": False, "enable_range_sensitivity": False,
                                 "allow_per_frame_range_fallback": True},
                    "figures": {"formats": ["png"], "dpi": 72}}
        output = root / "study"
        with measure(inputs) as fresh_counts:
            first = study.run_study(inputs, output, config=settings)
            assert first["status"] in {"completed", "completed_with_limitations"}, first
            assert sum(row["curve_count"] for row in first["samples"].values()) == 4
        with measure(inputs) as resume_counts:
            resumed = study.run_study(inputs, output, config=settings, resume=True)
            assert resumed["samples"] == first["samples"]
        return {"preview_then_import": dict(preview_counts), "fresh_study": dict(fresh_counts),
                "completed_resume": dict(resume_counts),
                "large_preview_control": dict(control_counts), "large_preview_cached": dict(cached_counts),
                "metadata_q_preview_control": dict(metadata_control), "metadata_q_preview": dict(metadata_preview),
                "outputs": {"status": first["status"], "curves": 4,
                            "artifacts": sum(len(row["output_inventory"]) for row in first["samples"].values()),
                            "q_ranges": {key: row["effective_q_range"] for key, row in first["samples"].items()}}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON receipt outside tracked source files")
    args = parser.parse_args()
    cold_start = []
    modules = None
    for _ in range(3):
        start = perf_counter()
        command = subprocess.run([sys.executable, "-c",
                                  "import json,sys; from app.cli import main; main(['methods']); "
                                  "print(json.dumps({'modules':len(sys.modules),'matplotlib_loaded': 'matplotlib' in sys.modules, 'qt_loaded': 'PySide6' in sys.modules}))"],
                                 cwd=REPO, capture_output=True, text=True, check=True)
        cold_start.append(round(perf_counter() - start, 4))
        modules = json.loads(command.stdout.splitlines()[-1])
        assert not modules["qt_loaded"]
    result = {"python": sys.version.split()[0], "methods": {"cold_start_seconds": cold_start, **modules}, **run_fixture()}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
