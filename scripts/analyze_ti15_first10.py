"""Analyze Ti15 300 C SAXS frames 1-10 without modifying source data.

Input files are copied to a temporary directory only to constrain the existing
automatic batch engine to an exact, auditable set of ten curves. All persistent
outputs are written to a new timestamped directory under ``results``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.core.auto_batch import run_auto_batch
from app.core.auto_batch_schema import AnalysisStatus, AutoBatchConfig
from app.core.result_package import export_result_package


DEFAULT_INPUT = Path(
    r"D:\桌面\PostFile\6_sys\SAXS-学习2\17_Ti15_300_2_iso\17_Ti15_300_2_iso\spectra_csv"
)
FRAME_NAMES = [f"ti15_{index:05d}_abs2d_cm-1.csv" for index in range(1, 11)]
ACCEPTED_STATUSES = {AnalysisStatus.SUCCESS.value, AnalysisStatus.ASSUMPTION_DEPENDENT.value}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_snapshot(paths: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for frame, path in enumerate(paths, start=1):
        stat = path.stat()
        rows.append(
            {
                "frame": frame,
                "source_file": path.name,
                "source_path": str(path.resolve()),
                "size_bytes": stat.st_size,
                "modified_time_ns": stat.st_mtime_ns,
                "sha256": sha256_file(path),
            }
        )
    return rows


def native(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def frame_number(name: str) -> int:
    for index, filename in enumerate(FRAME_NAMES, start=1):
        if name == Path(filename).stem or filename in name:
            return index
    return -1


def parameter_rows(run) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for envelope in run.analyses:
        for parameter in envelope.parameters:
            value = native(parameter.value)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            rows.append(
                {
                    "frame": frame_number(envelope.curve_name),
                    "curve_name": envelope.curve_name,
                    "analysis_type": envelope.analysis_type,
                    "analysis_status": envelope.status.value,
                    "parameter": parameter.name,
                    "value": value,
                    "unit_role": parameter.unit,
                    "parameter_status": parameter.status.value,
                    "q_start_A^-1": None if envelope.q_range is None else envelope.q_range[0],
                    "q_end_A^-1": None if envelope.q_range is None else envelope.q_range[1],
                    "reliability_label": envelope.reliability_label,
                    "reliability_score": envelope.reliability_score,
                    "invalid_reason": parameter.invalid_reason or envelope.invalid_reason,
                    "warnings": " | ".join(envelope.warnings),
                }
            )
    return rows


def quality_rows(run) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for curve in run.curves:
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        finite = np.isfinite(q) & np.isfinite(intensity)
        positive = finite & (q > 0) & (intensity > 0)
        rows.append(
            {
                "frame": frame_number(curve.name),
                "curve_name": curve.name,
                "source_file": Path(curve.source_file or "").name,
                "q_unit": curve.q_unit,
                "intensity_unit": curve.intensity_unit,
                "point_count": len(q),
                "finite_pair_count": int(finite.sum()),
                "nan_or_inf_pair_count": int((~finite).sum()),
                "negative_intensity_count": int((finite & (intensity < 0)).sum()),
                "zero_intensity_count": int((finite & (intensity == 0)).sum()),
                "duplicate_q_count": int(pd.Series(q[finite]).duplicated().sum()),
                "strictly_increasing_q": bool(np.all(np.diff(q[finite]) > 0)),
                "log_usable_count": int(positive.sum()),
                "q_min_A^-1": float(np.min(q[finite])) if finite.any() else None,
                "q_max_A^-1": float(np.max(q[finite])) if finite.any() else None,
                "I_min_cm^-1": float(np.min(intensity[finite])) if finite.any() else None,
                "I_max_cm^-1": float(np.max(intensity[finite])) if finite.any() else None,
            }
        )
    return rows


def scalar_parameter_table(rows: list[dict[str, object]]) -> pd.DataFrame:
    table = pd.DataFrame(rows)
    table["numeric_value"] = pd.to_numeric(table["value"], errors="coerce")
    table["accepted"] = (
        table["analysis_status"].isin(ACCEPTED_STATUSES)
        & table["parameter_status"].isin(ACCEPTED_STATUSES)
        & table["numeric_value"].notna()
    )
    table["reliable_for_reporting"] = (
        table["accepted"]
        & table["reliability_label"].isin({"high", "medium"})
        & (pd.to_numeric(table["reliability_score"], errors="coerce") >= 0.5)
    )
    return table


def save_figure(fig: plt.Figure, figures_dir: Path, stem: str) -> None:
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(figures_dir / f"{stem}.png", dpi=600, bbox_inches="tight")
    fig.savefig(figures_dir / f"{stem}.svg", bbox_inches="tight")
    fig.savefig(figures_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def plot_overlays(run, figures_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    colors = plt.cm.viridis(np.linspace(0.05, 0.95, len(run.curves)))
    for curve, color in zip(run.curves, colors):
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        mask = np.isfinite(q) & np.isfinite(intensity) & (q > 0) & (intensity > 0)
        ax.loglog(q[mask], intensity[mask], color=color, lw=1.2, label=f"Frame {frame_number(curve.name)}")
    ax.set_xlabel(r"$q$ ($\mathrm{\AA}^{-1}$)")
    ax.set_ylabel(r"$I(q)$ ($\mathrm{cm}^{-1}$)")
    ax.set_title("Ti15 300 C SAXS: frames 1-10")
    ax.legend(ncol=2, fontsize=8, frameon=False)
    ax.grid(alpha=0.18, which="both")
    save_figure(fig, figures_dir, "first10_saxs_overlay")


def selected_metric(table: pd.DataFrame, method: str, parameter: str) -> pd.DataFrame:
    output = table[
        (table["analysis_type"] == method)
        & (table["parameter"] == parameter)
        & table["reliable_for_reporting"]
    ].copy()
    return output.sort_values("frame")


def plot_parameter_trends(table: pd.DataFrame, figures_dir: Path) -> None:
    requested = [
        ("guinier", "Rg", r"$R_g$ (reported q-length unit$^{-1}$)"),
        ("power_law", "alpha", r"Power-law exponent $\alpha$"),
        ("peaks", "q_star", r"$q^*$ ($\mathrm{\AA}^{-1}$)"),
        ("peaks", "d_star", r"$d=2\pi/q^*$ ($\mathrm{\AA}$)"),
        ("porod", "alpha", r"Porod exponent $\alpha$"),
        ("invariant", "Q_measured", r"Measured invariant $Q$"),
    ]
    available = [(m, p, label, selected_metric(table, m, p)) for m, p, label in requested]
    available = [item for item in available if not item[3].empty]
    if not available:
        return
    fig, axes = plt.subplots(len(available), 1, figsize=(7.2, 2.6 * len(available)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, (_, _, label, values) in zip(axes, available):
        ax.plot(values["frame"], values["numeric_value"], "o-", lw=1.3, ms=4)
        ax.set_ylabel(label)
        ax.grid(alpha=0.25)
    axes[-1].set_xlabel("Frame")
    axes[-1].set_xticks(range(1, 11))
    fig.suptitle("Accepted SAXS parameter trajectories", y=1.002)
    save_figure(fig, figures_dir, "first10_parameter_trends")


def plot_guinier_diagnostics(run, parameter_table: pd.DataFrame, figures_dir: Path) -> None:
    fig, axes = plt.subplots(2, 5, figsize=(15, 6.4))
    plotted = 0
    for curve, ax in zip(run.curves, axes.ravel()):
        frame = frame_number(curve.name)
        fit = parameter_table[
            (parameter_table["frame"] == frame)
            & (parameter_table["analysis_type"] == "guinier")
            & parameter_table["accepted"]
        ]
        q_start = pd.to_numeric(fit["q_start_A^-1"], errors="coerce").dropna()
        q_end = pd.to_numeric(fit["q_end_A^-1"], errors="coerce").dropna()
        slope = fit.loc[fit["parameter"] == "slope", "numeric_value"].dropna()
        intercept = fit.loc[fit["parameter"] == "intercept", "numeric_value"].dropna()
        q = np.asarray(curve.q, dtype=float)
        intensity = np.asarray(curve.intensity, dtype=float)
        if q_start.empty or q_end.empty or slope.empty or intercept.empty:
            ax.text(0.5, 0.5, "No accepted Guinier fit", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(f"Frame {frame}")
            continue
        mask = (
            np.isfinite(q)
            & np.isfinite(intensity)
            & (intensity > 0)
            & (q >= q_start.iloc[0])
            & (q <= q_end.iloc[0])
        )
        x = q[mask] ** 2
        y = np.log(intensity[mask])
        ax.scatter(x, y, s=8, alpha=0.65, label="data")
        if x.size:
            order = np.argsort(x)
            ax.plot(x[order], slope.iloc[0] * x[order] + intercept.iloc[0], color="crimson", lw=1.3, label="fit")
            plotted += 1
        ax.set_title(f"Frame {frame}")
        ax.set_xlabel(r"$q^2$ ($\mathrm{\AA}^{-2}$)")
        ax.set_ylabel(r"$\ln I(q)$")
        ax.grid(alpha=0.2)
    if plotted:
        axes.ravel()[0].legend(fontsize=8, frameon=False)
    fig.suptitle("Guinier fit diagnostics", y=1.01)
    save_figure(fig, figures_dir, "first10_guinier_diagnostics")


def write_report(
    output_dir: Path,
    run,
    quality: pd.DataFrame,
    parameters: pd.DataFrame,
    integrity_ok: bool,
) -> None:
    accepted = parameters[parameters["accepted"]]
    status_counts = parameters.drop_duplicates(["frame", "analysis_type"])["analysis_status"].value_counts()
    reliable_lines: list[str] = []
    for method, parameter, label in [
        ("guinier", "Rg", "Rg"),
        ("power_law", "alpha", "幂律指数 alpha"),
        ("peaks", "q_star", "峰位 q*"),
        ("peaks", "d_star", "特征尺度 d=2π/q*"),
        ("porod", "alpha", "Porod 指数 alpha"),
    ]:
        values = selected_metric(parameters, method, parameter)
        if values.empty:
            reliable_lines.append(f"- {label}：没有通过状态筛选的数值，不能作为定量结论。")
        else:
            nums = values["numeric_value"].astype(float)
            reliable_lines.append(
                f"- {label}：{len(nums)}/10 帧获得可用值；范围 {nums.min():.6g}–{nums.max():.6g}。"
            )
    warning_count = sum(bool(str(item).strip()) for item in parameters["warnings"].fillna(""))
    lines = [
        "# Ti15 300 ℃ SAXS 前十帧分析报告",
        "",
        "## 分析范围",
        "",
        "主分析严格使用 `ti15_00001_abs2d_cm-1.csv` 至 `ti15_00010_abs2d_cm-1.csv`。",
        "室温参考 `TI15-rt_00001_abs2d_cm-1.csv` 未进入计算。横轴使用 frame 1–10；未假定采集时间。",
        "",
        "## 数据质量",
        "",
        f"- 曲线数：{len(quality)}；每帧点数范围：{quality['point_count'].min()}–{quality['point_count'].max()}。",
        f"- q 范围：{quality['q_min_A^-1'].min():.6g}–{quality['q_max_A^-1'].max():.6g} Å⁻¹。",
        f"- NaN/inf 点总数：{int(quality['nan_or_inf_pair_count'].sum())}。",
        f"- 负强度点总数：{int(quality['negative_intensity_count'].sum())}；零强度点总数：{int(quality['zero_intensity_count'].sum())}。",
        f"- 原始文件分析前后完整性校验：{'通过' if integrity_ok else '未通过'}。",
        "",
        "## 可用定量结果概览",
        "",
        *reliable_lines,
        "",
        "逐帧数值、q 拟合区间、状态和可靠性评分见 `accepted_parameters.csv` 与 `all_parameters_audit.csv`。",
        "",
        "## 方法状态与警告",
        "",
        *[f"- {status}: {count} 个逐帧方法结果" for status, count in status_counts.items()],
        f"- 参数记录中包含 warning 的条目数：{warning_count}。",
        f"- 批处理整体状态：`{run.status}`；该状态允许部分方法因不适用或缺少可靠区间而失败。",
        "",
        "## 科研解释边界",
        "",
        "- 自动选区与拟合用于探索和筛选，不能单独证明颗粒形貌、相变或形成机理。",
        "- `d=2π/q*` 是特征相关尺度，不自动等于颗粒直径。",
        "- 负强度未被截断或平移；涉及对数的方法只使用正强度点。",
        "- 未提供形貌先验、contrast、体积分数及采集时间，因此不报告相应绝对结构量或动力学参数。",
        "- `assumption_dependent` 数值保留在审计表中，引用前仍需结合样品背景与其他表征复核。",
        "",
        "## 输出索引",
        "",
        "- `input_manifest_original.csv`：原始输入路径、时间戳与 SHA-256。",
        "- `data_quality.csv`：逐帧数据质量统计。",
        "- `accepted_parameters.csv`：状态筛选后的可用标量参数。",
        "- `all_parameters_audit.csv`：所有方法、参数、状态、q 区间、warning 和无效原因。",
        "- `fit_quality.csv`、`sequence_*.csv`：软件原生拟合质量与序列结果。",
        "- `figures/`：600 dpi PNG、SVG 和 PDF 图件。",
        "- `run_summary.json`：完整配置与软件结果。",
    ]
    (output_dir / "final_report_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Ti15 SAXS frames 1-10 reproducibly.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--results-root", type=Path, default=PROJECT_DIR.parent / "results")
    args = parser.parse_args()

    source_paths = [args.input_dir / name for name in FRAME_NAMES]
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing))
    before = source_snapshot(source_paths)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.results_root / f"17_Ti15_300_2_iso_first10_{stamp}"
    config = AutoBatchConfig(
        batch_id="17_Ti15_300_2_iso_first10",
        sample_type="unknown",
        q_unit_override="A^-1",
        intensity_unit_override="cm^-1",
        enable_pr=False,
        enable_correlation=False,
        enable_bootstrap=False,
        enable_range_sensitivity=True,
        enable_sequence_analysis=True,
        sequence_axis="frame",
        reference_mode="first",
        enable_kinetics=False,
        enable_exploratory_statistics=False,
    )

    with tempfile.TemporaryDirectory(prefix="sas_first10_") as temp_name:
        temp_dir = Path(temp_name)
        for source in source_paths:
            shutil.copy2(source, temp_dir / source.name)
        run = run_auto_batch(temp_dir, config)

    original_by_name = {row["source_file"]: row for row in before}
    for curve in run.curves:
        original = original_by_name[Path(curve.source_file or "").name]
        curve.source_file = str(original["source_path"])
        curve.metadata["analysis_frame"] = frame_number(curve.name)
        curve.metadata["source_sha256"] = original["sha256"]
    run.input_manifest = [dict(row, manifest_status="success", manifest_error=None) for row in before]
    run.config_snapshot["selected_source_files"] = FRAME_NAMES
    run.config_snapshot["excluded_room_temperature_reference"] = "TI15-rt_00001_abs2d_cm-1.csv"
    run.config_snapshot["scientific_scope"] = "frames 1-10; sequence axis is frame, not time"

    exported = export_result_package(run, output_dir)
    pd.DataFrame(before).to_csv(exported / "input_manifest_original.csv", index=False, encoding="utf-8-sig")

    quality = pd.DataFrame(quality_rows(run)).sort_values("frame")
    quality.to_csv(exported / "data_quality.csv", index=False, encoding="utf-8-sig")
    rows = parameter_rows(run)
    parameters = scalar_parameter_table(rows).sort_values(["frame", "analysis_type", "parameter"])
    parameters.to_csv(exported / "all_parameters_audit.csv", index=False, encoding="utf-8-sig")
    parameters[parameters["accepted"]].to_csv(
        exported / "accepted_parameters.csv", index=False, encoding="utf-8-sig"
    )
    parameters[parameters["reliable_for_reporting"]].to_csv(
        exported / "reliable_parameters.csv", index=False, encoding="utf-8-sig"
    )

    figures_dir = exported / "figures"
    plot_overlays(run, figures_dir)
    plot_parameter_trends(parameters, figures_dir)
    plot_guinier_diagnostics(run, parameters, figures_dir)

    after = source_snapshot(source_paths)
    integrity_rows = []
    for old, new in zip(before, after):
        unchanged = all(old[key] == new[key] for key in ("size_bytes", "modified_time_ns", "sha256"))
        integrity_rows.append({**new, "unchanged_after_analysis": unchanged})
    integrity_ok = all(row["unchanged_after_analysis"] for row in integrity_rows)
    pd.DataFrame(integrity_rows).to_csv(
        exported / "source_integrity_after_analysis.csv", index=False, encoding="utf-8-sig"
    )
    (exported / "run_config.json").write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2, default=native), encoding="utf-8"
    )
    write_report(exported, run, quality, parameters, integrity_ok)

    print(f"RESULT_DIR={exported}")
    print(f"RUN_STATUS={run.status}")
    print(f"CURVES={len(run.curves)}")
    print(f"ANALYSES={len(run.analyses)}")
    print(f"SOURCE_INTEGRITY={'PASS' if integrity_ok else 'FAIL'}")
    return 0 if integrity_ok and len(run.curves) == 10 else 2


if __name__ == "__main__":
    raise SystemExit(main())
