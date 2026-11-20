"""Exploratory comparative evaluation on disjoint chronological blocks.

Orchestrates multiple detector × split runs, collects
``DetectorScore`` results, and feeds them into the Holm-Bonferroni
corrected comparison pipeline (``statistics.compare_detectors``).

The workflow:

    1. Receive a set of detector configs and telemetry data
    2. Partition timestamps into K disjoint chronological blocks
    3. Run each detector on each split via ``run_pipeline``
    4. Collect F1 and coverage per (detector, split) pair
    5. Feed into ``compare_detectors`` for statistical comparison
    6. Return a full ``ComparisonReport``

**Domain isolation is enforced** at every level: a single
``ComparativeRunner`` operates on exactly one domain.
"""

from __future__ import annotations

from typing import Literal

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DetectorConfig,
    TelemetryPoint,
)
from sovereign_ops.pipeline import PipelineResult, run_pipeline
from sovereign_ops.statistics import (
    ComparisonReport,
    DetectorScore,
    compare_detectors,
)

__all__ = [
    "ComparativeResult",
    "run_comparative_evaluation",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class ComparativeResult:
    """Immutable container for the full comparative evaluation.

    Holds all individual pipeline runs plus the statistical report.
    """

    pipeline_results: tuple[PipelineResult, ...]
    scores: tuple[DetectorScore, ...]
    report: ComparisonReport

    def __init__(
        self,
        *,
        pipeline_results: tuple[PipelineResult, ...],
        scores: tuple[DetectorScore, ...],
        report: ComparisonReport,
    ) -> None:
        object.__setattr__(self, "pipeline_results", pipeline_results)
        object.__setattr__(self, "scores", scores)
        object.__setattr__(self, "report", report)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("ComparativeResult is immutable")


# ---------------------------------------------------------------------------
# Split generation
# ---------------------------------------------------------------------------


def _chronological_blocks(
    points: list[TelemetryPoint], labels: list[bool], n_splits: int
) -> list[tuple[list[TelemetryPoint], list[bool]]]:
    """Divide timestamp groups into disjoint blocks, preserving label alignment."""
    if n_splits < 1:
        raise ValueError(f"Need at least 1 split, got {n_splits}")
    if len(points) != len(labels):
        raise ValueError("Points and labels must have equal length")
    pairs = sorted(zip(points, labels, strict=True), key=lambda pair: pair[0].observed_at)
    groups: list[list[tuple[TelemetryPoint, bool]]] = []
    for pair in pairs:
        if not groups or groups[-1][0][0].observed_at != pair[0].observed_at:
            groups.append([])
        groups[-1].append(pair)
    if len(groups) < n_splits:
        raise ValueError("Need at least one distinct timestamp per split")
    blocks: list[tuple[list[TelemetryPoint], list[bool]]] = []
    for i in range(n_splits):
        block_pairs = [
            pair
            for group in groups[i * len(groups) // n_splits : (i + 1) * len(groups) // n_splits]
            for pair in group
        ]
        if len(block_pairs) < 10:
            raise ValueError("Each chronological block needs at least 10 observations")
        blocks.append(([p for p, _ in block_pairs], [label for _, label in block_pairs]))
    return blocks


# ---------------------------------------------------------------------------
# Comparative runner
# ---------------------------------------------------------------------------


def run_comparative_evaluation(
    *,
    points: list[TelemetryPoint],
    labels: list[bool],
    manifest: AcquisitionManifest,
    configs: list[DetectorConfig],
    n_splits: int = 5,
    alpha: float = 0.05,
    metric: Literal["f1", "coverage"] = "f1",
) -> ComparativeResult:
    """Compare detectors on disjoint blocks of historical observations.

    These results are exploratory until the dataset and evaluation protocol
    are audited and frozen. Adjacent blocks may still be serially dependent.

    Parameters
    ----------
    points:
        Telemetry observations for a single domain.
    labels:
        Ground-truth anomaly labels.
    manifest:
        Acquisition manifest for the source dataset.
    configs:
        Detector configurations to compare (≥ 2).
    n_splits:
        Number of chronological split variations (default 5).
    alpha:
        FWER threshold for Holm-Bonferroni correction.
    metric:
        Which metric to compare ("f1" or "coverage").

    Returns
    -------
    ComparativeResult with pipeline runs, scores, and statistical
    comparison report.

    Raises
    ------
    ValueError
        If fewer than 2 configs, mixed domains, or pipeline failures.
    """
    if len(configs) < 2:
        raise ValueError(f"Need ≥ 2 detector configs, got {len(configs)}")

    # Validate single domain
    domains = {c.dataset_id for c in configs}
    if len(domains) != 1:
        raise ValueError(f"Cross-domain comparison prohibited: {domains}")

    blocks = _chronological_blocks(points, labels, n_splits)

    all_results: list[PipelineResult] = []
    all_scores: list[DetectorScore] = []

    for split_idx, (block_points, block_labels) in enumerate(blocks):
        for config in configs:
            result = run_pipeline(
                points=block_points,
                labels=block_labels,
                manifest=manifest,
                config=config,
            )
            all_results.append(result)

            # Extract score for statistical comparison
            eval_result = result.evaluation
            if metric == "f1" and eval_result.f1 is None:
                raise ValueError(
                    f"F1 is undefined for model {config.model_id} on block {split_idx}; "
                    "choose a defined metric or revise the predeclared evaluation design"
                )
            score = DetectorScore(
                dataset_id=config.dataset_id,
                model_id=config.model_id,
                split_index=split_idx,
                f1=eval_result.f1,
                coverage=eval_result.coverage,
                abstention_rate=eval_result.abstention_rate,
                split_sha256=result.split_spec.sha256_digest(),
            )
            all_scores.append(score)

    # Statistical comparison
    report = compare_detectors(all_scores, alpha=alpha, metric=metric)

    return ComparativeResult(
        pipeline_results=tuple(all_results),
        scores=tuple(all_scores),
        report=report,
    )
