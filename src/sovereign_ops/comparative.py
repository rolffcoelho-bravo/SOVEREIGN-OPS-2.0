"""Comparative evaluation runner for the G5 confirmatory layer.

Orchestrates multiple detector × split runs, collects
``DetectorScore`` results, and feeds them into the Holm-Bonferroni
corrected comparison pipeline (``statistics.compare_detectors``).

The workflow:

    1. Receive a set of detector configs and telemetry data
    2. Generate K chronological splits (sliding window or fixed-fraction)
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


def _generate_split_fracs(
    n_splits: int,
    *,
    train_base: float = 0.6,
    test_frac: float = 0.2,
) -> list[tuple[float, float, float]]:
    """Generate split fractions for K chronological evaluations.

    For K > 1, varies the training fraction slightly to create
    different chronological boundaries while keeping the test fraction
    constant.  This simulates "how well does the detector generalize
    across different training windows?"

    Parameters
    ----------
    n_splits:
        Number of distinct chronological splits.
    train_base:
        Base training fraction (default 0.6).
    test_frac:
        Fixed test fraction (default 0.2).

    Returns
    -------
    List of (train_frac, calibration_frac, test_frac) tuples.
    """
    if n_splits < 1:
        raise ValueError(f"Need at least 1 split, got {n_splits}")

    if n_splits == 1:
        cal = 1.0 - train_base - test_frac
        return [(train_base, cal, test_frac)]

    fracs: list[tuple[float, float, float]] = []
    # Distribute training fractions between train_base ± delta
    delta = min(0.1, (1.0 - test_frac - 0.3) / (n_splits - 1))

    for i in range(n_splits):
        if n_splits == 1:
            shift = 0.0
        else:
            shift = -delta + 2 * delta * i / (n_splits - 1)
        train = train_base + shift
        cal = round(1.0 - train - test_frac, 6)
        if cal < 0.05:
            cal = 0.05
            train = round(1.0 - cal - test_frac, 6)
        fracs.append((round(train, 6), cal, test_frac))

    return fracs


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
    """Run all detectors on K chronological splits and compare.

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

    split_fracs = _generate_split_fracs(n_splits)

    all_results: list[PipelineResult] = []
    all_scores: list[DetectorScore] = []

    for split_idx, (train_f, cal_f, test_f) in enumerate(split_fracs):
        for config in configs:
            result = run_pipeline(
                points=points,
                labels=labels,
                manifest=manifest,
                config=config,
                train_frac=train_f,
                calibration_frac=cal_f,
                test_frac=test_f,
            )
            all_results.append(result)

            # Extract score for statistical comparison
            eval_result = result.evaluation
            score = DetectorScore(
                dataset_id=config.dataset_id,
                model_id=config.model_id,
                split_index=split_idx,
                f1=eval_result.f1 if eval_result.f1 is not None else 0.0,
                coverage=eval_result.coverage,
                abstention_rate=eval_result.abstention_rate,
            )
            all_scores.append(score)

    # Statistical comparison
    report = compare_detectors(all_scores, alpha=alpha, metric=metric)

    return ComparativeResult(
        pipeline_results=tuple(all_results),
        scores=tuple(all_scores),
        report=report,
    )
