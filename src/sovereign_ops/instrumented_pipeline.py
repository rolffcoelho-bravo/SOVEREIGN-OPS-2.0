"""G6.2 Instrumented Pipeline — observability-wrapped pipeline execution.

This module wraps ``run_pipeline`` with the G6 observability layer,
producing both the standard ``PipelineResult`` and an
``ObservabilityReport`` for every run.

The instrumented pipeline:
1. Creates a ``PipelineLogger`` for the domain
2. Times each pipeline stage (split, fit, predict, evaluate, evidence)
3. Records metrics: row counts, abstention rates, F1 scores, latencies
4. Produces a finalized ``ObservabilityReport`` alongside the result

Usage::

    result, report = run_instrumented_pipeline(
        points=points,
        labels=labels,
        manifest=manifest,
        config=config,
    )
    # result is PipelineResult, report is ObservabilityReport
    print(report.canonical_json())
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import numpy as np
from pydantic import HttpUrl

from sovereign_ops.contracts import (
    AcquisitionManifest,
    DetectorConfig,
    DetectorPrediction,
    EvaluationResult,
    EvidenceCitation,
    ModelEvidence,
    SplitSpec,
    TelemetryPoint,
)
from sovereign_ops.detectors import build_detector
from sovereign_ops.evaluation import evaluate_predictions
from sovereign_ops.observability import (
    ObservabilityReport,
    PipelineLogger,
)
from sovereign_ops.splits import chronological_split, partition_points

__all__ = [
    "InstrumentedResult",
    "run_instrumented_pipeline",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class InstrumentedResult:
    """Pipeline result paired with its observability report.

    Attributes
    ----------
    dataset_id : DatasetId
        Which domain this pipeline ran on.
    split_spec : SplitSpec
        The chronological split that was applied.
    config : DetectorConfig
        The detector configuration used.
    predictions : tuple[DetectorPrediction, ...]
        Per-observation predictions on the test set.
    evaluation : EvaluationResult
        Abstention-aware metrics for this run.
    evidence : ModelEvidence
        Cryptographically pinned evidence record.
    report : ObservabilityReport
        G6 observability report with logging, metrics, and audit trail.
    """

    def __init__(
        self,
        *,
        dataset_id: str,
        split_spec: SplitSpec,
        config: DetectorConfig,
        predictions: tuple[DetectorPrediction, ...],
        evaluation: EvaluationResult,
        evidence: ModelEvidence,
        report: ObservabilityReport,
    ) -> None:
        object.__setattr__(self, "dataset_id", dataset_id)
        object.__setattr__(self, "split_spec", split_spec)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "evaluation", evaluation)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "report", report)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("InstrumentedResult is immutable")


# ---------------------------------------------------------------------------
# Evidence builder (same logic as pipeline.py, kept co-located)
# ---------------------------------------------------------------------------


def _build_evidence(
    *,
    config: DetectorConfig,
    manifest: AcquisitionManifest,
    evaluation: EvaluationResult,
    split_spec: SplitSpec,
    protocol_sha256: str,
) -> ModelEvidence:
    """Construct ``ModelEvidence`` from pipeline artefacts."""
    eval_json = evaluation.canonical_json()
    eval_sha = hashlib.sha256(eval_json.encode()).hexdigest()

    citation = EvidenceCitation(
        evidence_id=f"eval-{config.model_id}",
        source_url=HttpUrl(
            f"https://sovereign-ops.local/evaluation/{config.dataset_id}/{config.model_id}"
        ),
        source_sha256=eval_sha,
        locator=f"split={split_spec.sha256_digest()}",
    )

    return ModelEvidence(
        dataset_id=config.dataset_id,
        model_id=config.model_id,
        model_sha256=config.sha256_digest(),
        dataset_manifest_sha256=manifest.sha256_digest(),
        protocol_sha256=protocol_sha256,
        training_window=split_spec.train_window,
        calibration_version=None,
        inference_at=datetime.now(UTC),
        score=evaluation.f1 if evaluation.f1 is not None else 0.0,
        citations=(citation,),
    )


def _make_protocol_sha256() -> str:
    """Deterministic hash of the evaluation protocol specification."""
    protocol_spec = (
        "abstention-aware-evaluation:v1.2:"
        "splitting=chronological_timestamp_groups:"
        "scope=single_asset_signal_unit:iforest_scale=training:f1=count_based:"
        "metrics=precision,recall,f1,coverage,abstention_rate"
    )
    return hashlib.sha256(protocol_spec.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Instrumented pipeline runner
# ---------------------------------------------------------------------------


def run_instrumented_pipeline(
    *,
    points: list[TelemetryPoint],
    labels: list[bool],
    manifest: AcquisitionManifest,
    config: DetectorConfig,
    train_frac: float = 0.6,
    calibration_frac: float = 0.2,
    test_frac: float = 0.2,
    run_id: str | None = None,
) -> InstrumentedResult:
    """Execute a fully instrumented single-domain analysis pipeline.

    Identical to ``run_pipeline`` but wraps every stage with the G6
    observability layer, producing an ``ObservabilityReport`` alongside
    the standard pipeline result.

    Parameters
    ----------
    points:
        Telemetry observations for one asset, signal and unit.
    labels:
        Ground-truth anomaly labels (``True`` = anomalous).
    manifest:
        Acquisition manifest for the source dataset.
    config:
        Detector configuration to instantiate and run.
    train_frac:
        Fraction of distinct timestamps for training (default 0.6).
    calibration_frac:
        Fraction reserved for calibration (default 0.2).
    test_frac:
        Fraction of distinct timestamps for test (default 0.2).
    run_id:
        Optional correlation ID. Auto-generated if not provided.

    Returns
    -------
    InstrumentedResult
        Contains the full pipeline result plus the observability report.
    """
    logger = PipelineLogger(domain=config.dataset_id, run_id=run_id)

    # ── Validation stage ──────────────────────────────────────────────
    with logger.stage("validation"):
        if len(points) != len(labels):
            msg = f"points ({len(points)}) and labels ({len(labels)}) must match"
            raise ValueError(msg)
        if not points:
            raise ValueError("Pipeline requires at least one observation")

        dataset_id = config.dataset_id
        if manifest.dataset_id != dataset_id:
            msg = f"Manifest domain '{manifest.dataset_id}' != config domain '{dataset_id}'"
            raise ValueError(msg)

        source_hashes = {entry.sha256 for entry in manifest.files}
        for pt in points:
            if pt.dataset_id != dataset_id:
                msg = f"Point domain '{pt.dataset_id}' != pipeline domain '{dataset_id}'"
                raise ValueError(msg)
            if pt.source_sha256 not in source_hashes:
                raise ValueError("Point source hash is absent from the acquisition manifest")

        if len({(pt.asset_id, pt.signal_id, pt.unit) for pt in points}) != 1:
            raise ValueError("Univariate pipeline requires a single asset, signal and unit")

        logger.counter("validation.total_points", float(len(points)))
        logger.counter(
            "validation.anomaly_labels",
            float(sum(1 for lbl in labels if lbl)),
        )

    # ── Split stage ───────────────────────────────────────────────────
    with logger.stage("split"):
        split_spec = chronological_split(
            dataset_id=dataset_id,
            points=points,
            train_frac=train_frac,
            calibration_frac=calibration_frac,
            test_frac=test_frac,
        )

        train_points, _cal_points, test_points = partition_points(points, split_spec)

        point_to_label = {
            (pt.observed_at, pt.asset_id, pt.signal_id): label
            for pt, label in zip(points, labels, strict=True)
        }
        if len(point_to_label) != len(points):
            raise ValueError(
                "Duplicate observation keys require an explicit "
                "reconciliation policy before fitting"
            )
        test_labels = [
            point_to_label[(pt.observed_at, pt.asset_id, pt.signal_id)] for pt in test_points
        ]

        if not train_points:
            raise ValueError("No observations fell within the training window")
        if not test_points:
            raise ValueError("No observations fell within the test window")

        logger.counter("split.train_points", float(len(train_points)))
        logger.counter("split.test_points", float(len(test_points)))
        logger.info(
            "Split complete",
            train_size=len(train_points),
            test_size=len(test_points),
        )

    # ── Detection stage ───────────────────────────────────────────────
    with logger.stage("detection"):
        detector = build_detector(config)
        train_values = np.array(
            [p.value if p.value is not None else float("nan") for p in train_points],
            dtype=np.float64,
        )
        detector.fit(train_values)
        predictions = detector.predict(test_points, config)

        logger.counter("detection.predictions", float(len(predictions)))
        abstained = sum(1 for p in predictions if p.abstained)
        logger.gauge(
            "detection.abstention_rate",
            abstained / len(predictions) if predictions else 0.0,
            unit="ratio",
        )
        logger.info(
            "Detection complete",
            predictions=len(predictions),
            abstained=abstained,
        )

    # ── Evaluation stage ──────────────────────────────────────────────
    with logger.stage("evaluation"):
        evaluation = evaluate_predictions(
            predictions,
            test_labels,
            split_spec=split_spec,
            config=config,
        )

        if evaluation.f1 is not None:
            logger.gauge("evaluation.f1", evaluation.f1)
        if evaluation.precision is not None:
            logger.gauge("evaluation.precision", evaluation.precision)
        if evaluation.recall is not None:
            logger.gauge("evaluation.recall", evaluation.recall)
        if evaluation.coverage is not None:
            logger.gauge("evaluation.coverage", evaluation.coverage)
        if evaluation.abstention_rate is not None:
            logger.gauge("evaluation.abstention_rate", evaluation.abstention_rate)

        logger.info(
            "Evaluation complete",
            f1=evaluation.f1,
            coverage=evaluation.coverage,
        )

    # ── Evidence stage ────────────────────────────────────────────────
    with logger.stage("evidence"):
        protocol_sha = _make_protocol_sha256()
        evidence = _build_evidence(
            config=config,
            manifest=manifest,
            evaluation=evaluation,
            split_spec=split_spec,
            protocol_sha256=protocol_sha,
        )
        logger.info(
            "Evidence assembled",
            model_sha256=evidence.model_sha256[:16] + "...",
            evidence_score=evidence.score,
        )

    # ── Finalize ──────────────────────────────────────────────────────
    report = logger.finalize()

    return InstrumentedResult(
        dataset_id=dataset_id,
        split_spec=split_spec,
        config=config,
        predictions=tuple(predictions),
        evaluation=evaluation,
        evidence=evidence,
        report=report,
    )
