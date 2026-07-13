"""Read-only batch consensus selection for automatically detected q regions."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, exp, isfinite, log, log10
from statistics import median
from typing import Any, Mapping

from app.core.auto_batch_schema import AutoBatchConfig
from app.core.auto_regions import detect_auto_regions
from app.core.data_model import CurveData


LOG_Q_CENTER_CLUSTER_THRESHOLD = 0.35

_AUTO_REGION_TYPE_TO_CONSENSUS_TYPE = {
    "guinier_candidate": "guinier",
    "power_law_candidate": "power_law",
    "porod_candidate": "porod",
    "peak_candidate": "peak",
}


@dataclass(frozen=True)
class ConsensusRegion:
    """One batch-level q range supported by a group of individual curves.

    ``q_range`` is the longest continuous interval contained by enough
    per-curve candidates to meet the configured support fraction.  It is not a
    strict intersection across every frame. ``log_median_q_range`` is retained
    only as an audit statistic for the supporting candidates' endpoints.
    """

    region_type: str
    q_range: tuple[float, float]
    coverage: float
    median_score: float
    supporting_curve_ids: tuple[str, ...]
    median_n_points: float = 0.0
    candidate_n_points_min: float = 0.0
    candidate_n_points_max: float = 0.0
    log_median_q_range: tuple[float, float] | None = None
    range_rule: str = "coverage_supported_widest_interval"
    minimum_log_span_decades: float = 0.0


@dataclass(frozen=True)
class _ReadyCandidate:
    curve_id: str
    q_start: float
    q_end: float
    score: float
    n_points: float

    @property
    def log_q_center(self) -> float:
        return (log(self.q_start) + log(self.q_end)) / 2.0


class ConsensusResolution(dict[str, ConsensusRegion]):
    """Consensus mapping with the exact scanned candidate rows attached for audit."""

    def __init__(
        self,
        *args: Any,
        candidate_rows: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.candidate_rows = list(candidate_rows or [])


def _ready_candidate(row: Mapping[str, Any]) -> _ReadyCandidate | None:
    """Return a validated, fit-ready row without changing the source candidate."""

    if row.get("fit_ready") is not True:
        return None
    raw_curve_id = row.get("curve_id")
    if not isinstance(raw_curve_id, str):
        return None
    curve_id = raw_curve_id.strip()
    if not curve_id:
        return None
    try:
        q_start = float(row["q_start"])
        q_end = float(row["q_end"])
        score = float(row["score"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        n_points = float(row.get("n_points", 0.0))
    except (TypeError, ValueError):
        n_points = 0.0
    if not isfinite(n_points) or n_points < 0.0:
        n_points = 0.0
    if not all(isfinite(value) for value in (q_start, q_end, score)):
        return None
    if q_start <= 0.0 or q_end <= q_start:
        return None
    return _ReadyCandidate(curve_id=curve_id, q_start=q_start, q_end=q_end, score=score, n_points=n_points)


def _best_candidate_per_curve(rows: list[_ReadyCandidate]) -> list[_ReadyCandidate]:
    """Keep one deterministic, highest-scoring candidate for every curve ID."""

    selected: dict[str, _ReadyCandidate] = {}
    for row in sorted(rows, key=lambda item: (-item.score, -item.n_points, item.q_start, item.q_end, item.curve_id)):
        selected.setdefault(row.curve_id, row)
    return [selected[curve_id] for curve_id in sorted(selected)]


def _region_from_cluster(
    region_type: str,
    rows: list[_ReadyCandidate],
    *,
    curve_count: int,
    min_coverage: float,
    min_log_span_decades: float,
) -> ConsensusRegion | None:
    if curve_count <= 0:
        return None
    unique_rows = _best_candidate_per_curve(rows)
    if not unique_rows or len(unique_rows) > curve_count:
        return None
    minimum_support = max(1, int(ceil(curve_count * min_coverage - 1e-12)))
    boundaries = sorted({value for row in unique_rows for value in (row.q_start, row.q_end)})
    supported: list[tuple[float, float, list[_ReadyCandidate]]] = []
    for start_index, q_start in enumerate(boundaries[:-1]):
        for q_end in boundaries[start_index + 1 :]:
            if q_start <= 0.0 or q_end <= q_start:
                continue
            log_span = log10(q_end / q_start)
            if log_span + 1e-12 < min_log_span_decades:
                continue
            supporting = [
                row
                for row in unique_rows
                if row.q_start <= q_start + 1e-12 and row.q_end >= q_end - 1e-12
            ]
            if len(supporting) >= minimum_support:
                supported.append((q_start, q_end, supporting))
    if not supported:
        return None
    q_start, q_end, supporting_rows = min(
        supported,
        key=lambda item: (
            -log10(item[1] / item[0]),
            -len(item[2]),
            -median([row.score for row in item[2]]),
            item[0],
            item[1],
        ),
    )
    coverage = len(supporting_rows) / curve_count
    log_median_q_range = (
        exp(median([log(row.q_start) for row in supporting_rows])),
        exp(median([log(row.q_end) for row in supporting_rows])),
    )
    return ConsensusRegion(
        region_type=region_type,
        q_range=(q_start, q_end),
        coverage=coverage,
        median_score=float(median([row.score for row in supporting_rows])),
        supporting_curve_ids=tuple(row.curve_id for row in supporting_rows),
        median_n_points=float(median([row.n_points for row in supporting_rows])),
        candidate_n_points_min=float(min(row.n_points for row in supporting_rows)),
        candidate_n_points_max=float(max(row.n_points for row in supporting_rows)),
        log_median_q_range=log_median_q_range,
        minimum_log_span_decades=float(min_log_span_decades),
    )


def candidate_consensus(
    region_type: str,
    candidates: list[dict[str, Any]],
    *,
    curve_count: int,
    min_coverage: float,
    min_log_span_decades: float = 0.0,
) -> ConsensusRegion | None:
    """Select the longest coverage-supported interval in a log-q cluster.

    All returned intervals already satisfy the configured support and span
    gates.  Length is therefore the primary objective; coverage, score, point
    count, and stable q ordering resolve ties.
    """

    if not 0.0 < min_coverage <= 1.0:
        return None
    ready = [_ready_candidate(row) for row in candidates if isinstance(row, Mapping)]
    ready_rows = [row for row in ready if row is not None]
    if not ready_rows:
        return None

    regions: list[ConsensusRegion] = []
    for anchor in ready_rows:
        cluster = [
            row
            for row in ready_rows
            if abs(row.log_q_center - anchor.log_q_center) <= LOG_Q_CENTER_CLUSTER_THRESHOLD + 1e-12
        ]
        region = _region_from_cluster(
            region_type,
            cluster,
            curve_count=curve_count,
            min_coverage=min_coverage,
            min_log_span_decades=min_log_span_decades,
        )
        if region is not None:
            regions.append(region)
    if not regions:
        return None

    return min(
        regions,
        key=lambda item: (
            -log10(item.q_range[1] / item.q_range[0]),
            -item.coverage,
            -item.median_score,
            -item.median_n_points,
            item.q_range[0],
            item.q_range[1],
            item.supporting_curve_ids,
        ),
    )


def resolve_consensus_regions(curves: list[CurveData], config: AutoBatchConfig) -> dict[str, ConsensusRegion]:
    """Resolve supported batch q ranges from existing per-curve candidates.

    ``detect_auto_regions`` is called only to read temporary candidate data; this
    function does not alter curves, their metadata, or their source files.
    """

    grouped: dict[str, list[dict[str, Any]]] = {
        consensus_type: [] for consensus_type in _AUTO_REGION_TYPE_TO_CONSENSUS_TYPE.values()
    }
    consensus_curves = [
        curve
        for curve in curves
        if not bool(curve.metadata.get("is_reference"))
        and curve.metadata.get("sequence_role") != "reference"
    ]
    curve_ids = {str(curve.curve_id) for curve in consensus_curves}
    candidate_audit_rows: list[dict[str, Any]] = []
    for curve in consensus_curves:
        detection = detect_auto_regions(curve, q_range=config.effective_q_range)
        candidates = detection.results.get("candidates", [])
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            audit_row = dict(candidate)
            audit_row["sequence_role"] = curve.metadata.get("sequence_role", "series")
            audit_row["is_reference"] = False
            candidate_audit_rows.append(audit_row)
            if candidate.get("curve_id") != curve.curve_id:
                continue
            consensus_type = _AUTO_REGION_TYPE_TO_CONSENSUS_TYPE.get(str(candidate.get("region_type", "")))
            if consensus_type is not None:
                grouped[consensus_type].append(candidate)

    output: dict[str, ConsensusRegion] = {}
    for consensus_type, rows in grouped.items():
        region = candidate_consensus(
            consensus_type,
            rows,
            curve_count=len(curve_ids),
            min_coverage=config.consensus_min_coverage,
            min_log_span_decades=(
                max(
                    config.common_min_log_q_span_decades,
                    config.power_law_formal_min_log_q_span_decades,
                )
                if consensus_type == "power_law"
                else max(
                    config.common_min_log_q_span_decades,
                    config.porod_formal_min_log_q_span_decades,
                )
                if consensus_type == "porod"
                else config.common_min_log_q_span_decades
            ),
        )
        if region is not None:
            output[consensus_type] = region
    return ConsensusResolution(output, candidate_rows=candidate_audit_rows)


__all__ = ["ConsensusRegion", "ConsensusResolution", "candidate_consensus", "resolve_consensus_regions"]
